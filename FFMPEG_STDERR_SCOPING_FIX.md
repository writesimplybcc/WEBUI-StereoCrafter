# Fix: FFmpeg stderr Scoping Error

## Problem
```
06:51:55 - Error reading FFmpeg stderr: cannot access free variable 'ffmpeg_process' where it is not associated with a value in enclosing scope
```

This error occurred because the `read_ffmpeg_stderr()` function was being executed **BEFORE** `ffmpeg_process` was initialized.

## Root Cause

### Code Structure Before Fix:
```python
# Line ~1230: Function defined (references ffmpeg_process)
def read_ffmpeg_stderr():
    if ffmpeg_process.stderr:  # ❌ ffmpeg_process doesn't exist yet!
        ...

# Line ~1280: Thread started (executes function immediately)
stderr_thread = threading.Thread(target=read_ffmpeg_stderr, daemon=True)
stderr_thread.start()  # ❌ Tries to access undefined variable

# Line ~1370: Inside while loop, ffmpeg_process is finally created
while ...:
    ffmpeg_process = start_ffmpeg_pipe_process(...)  # Too late!
```

### Why It Failed:
1. `read_ffmpeg_stderr()` function was defined before `ffmpeg_process` existed
2. The stderr thread was started immediately, trying to access `ffmpeg_process`
3. Python raised `NameError: free variable 'ffmpeg_process' not associated with a value`
4. This caused the stderr reader to fail silently, losing critical FFmpeg error output

## Solution

### Code Structure After Fix:
```python
# Initialize error tracking variables ONCE (outside while loop)
ffmpeg_errors = []
ffmpeg_error_lock = threading.Lock()

# Define helper function ONCE (outside while loop)
def read_ffmpeg_stderr():
    """Read FFmpeg stderr continuously"""
    if ffmpeg_process.stderr:  # ✅ Will be defined when called
        ...

# Initialize counters
frame_count = 0

# Inside the retry while loop:
while not processing_completed and cpu_retry_attempt <= max_cpu_retries:
    # Create FFmpeg process FIRST
    ffmpeg_process = start_ffmpeg_pipe_process(...)
    
    # THEN start stderr thread (ffmpeg_process now exists)
    stderr_thread = threading.Thread(target=read_ffmpeg_stderr, daemon=True)
    stderr_thread.start()  # ✅ Works correctly now
```

### Changes Made:

1. **Moved function definition outside while loop** (line ~1231)
   - Defined once, used multiple times (for each retry attempt)
   - Function captures `ffmpeg_process` by closure when actually called (not when defined)

2. **Moved `ffmpeg_errors` and `ffmpeg_error_lock` outside while loop** (line ~1225)
   - Initialized once, cleared on each retry
   - Prevents duplicate initialization

3. **Removed duplicate function definition** (was at line ~1285)
   - Only ONE `read_ffmpeg_stderr()` function now
   - Eliminates confusion and scoping issues

4. **Kept stderr thread start inside while loop** (line ~1344)
   - Thread starts AFTER `ffmpeg_process` is assigned
   - Fresh thread for each retry attempt

## Why This Works

### Python Closures:
```python
# Function definition (closure captures variables, not values)
def read_ffmpeg_stderr():
    if ffmpeg_process.stderr:  # Looks up ffmpeg_process at CALL time
        ...

# Variable assigned later
ffmpeg_process = some_value  # Now exists

# Function called - closure resolves ffmpeg_process correctly
read_ffmpeg_stderr()  # ✅ Works!
```

### Key Insight:
Python closures capture **variables by reference**, not by value. The function doesn't need `ffmpeg_process` to exist when **defined**—only when **called**.

## Files Modified

- `stereocrafter_ui/merging/merging_ui.py`
  - Line ~1225: Moved `ffmpeg_errors` and `ffmpeg_error_lock` initialization
  - Line ~1231: Defined `read_ffmpeg_stderr()` function once
  - Line ~1280: **Removed** duplicate function definition
  - Line ~1344: Kept stderr thread start inside while loop (after `ffmpeg_process` creation)

## Expected Behavior After Fix

### Before Fix:
```
06:51:55 - Error reading FFmpeg stderr: cannot access free variable 'ffmpeg_process'...
[No FFmpeg error output captured - debugging impossible]
```

### After Fix:
```
06:51:55 - FFmpeg pipe started (attempt 0): 7680x2160 @ 23.976 fps
06:51:55 - FFmpeg: [hevc_nvenc @ 0x55a8c40d8f00] ...
06:52:41 - First frame written: 7680x2160
06:52:52 - FFmpeg crashed after processing chunks. Return code: -9
06:52:52 - FFmpeg error log (last 15 messages):
06:52:52 -   [hevc_nvenc @ 0x55a8c40d8f00] Failed to encode frame: Out of memory
06:52:52 - NVENC failed, retrying with CPU encoding (attempt 1/1)...
[Full error output captured - debugging easy]
```

## Benefits

✅ **No more scoping errors** - `ffmpeg_process` exists before thread starts  
✅ **Complete error logging** - All FFmpeg stderr output captured  
✅ **Better debugging** - Can see exact NVENC error messages  
✅ **Retry support** - Stderr thread works for each retry attempt  
✅ **Clean architecture** - Single function definition, proper scoping  

## Verification

After applying the fix, you should NOT see:
```
❌ Error reading FFmpeg stderr: cannot access free variable 'ffmpeg_process'
```

Instead, you SHOULD see:
```
✅ FFmpeg: [codec info] ...
✅ FFmpeg error log (last X messages):
✅   [actual error details from FFmpeg]
```
