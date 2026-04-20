# Complete NVENC Crash & Fallback Fix

## Problem Summary
When using RTX A6000 for merging with full SBS output format, FFmpeg was crashing (return code -9, SIGKILL/OOM) during NVENC encoding, and **no files were written** due to multiple bugs in crash detection and fallback logic.

## Root Causes Found & Fixed

### Bug 1: Duplicate FFmpeg Process Creation
**Problem**: FFmpeg was started TWICE for each video:
1. First at line ~1220 (before the retry while loop)
2. Second inside the retry while loop (line ~1350)

The first FFmpeg was orphaned and never used, wasting resources.

**Fix**: Removed the first FFmpeg start. Now only the retry while loop creates FFmpeg processes.

### Bug 2: RuntimeError Crashed Processing
**Problem**: When FFmpeg crashed during frame writing, code raised `RuntimeError` which crashed the entire video processing instead of triggering NVENC→CPU fallback.

```python
# BEFORE (WRONG):
raise RuntimeError(f"FFmpeg process finished early with code {ffmpeg_process.returncode}.")

# AFTER (CORRECT):
break  # Let fallback handle it
```

**Fix**: Changed all `raise` statements to `break` in frame writing error handlers.

### Bug 3: Missing Crash Detection After Frame Writing
**Problem**: If FFmpeg crashed AFTER all chunks were processed but BEFORE finalization, the crash went undetected. The code would incorrectly assume processing completed successfully.

**Fix**: Added comprehensive crash detection at the end of the chunk loop:
```python
# COMPREHENSIVE CRASH DETECTION: Check if FFmpeg crashed at ANY point
if ffmpeg_process.poll() is not None:
    logger.error(f"FFmpeg crashed after processing chunks. Return code: {ffmpeg_process.returncode}, frames written: {frame_count}/{num_frames}")
    # Mark this attempt as failed
    nvenc_failed_this_attempt = True
    nvenc_failed = True
    nvenc_failed_at_frame = frame_count
```

### Bug 4: BrokenPipeError Crashed Processing
**Problem**: Pipe failures raised `BrokenPipeError` which crashed the process.

**Fix**: Changed to `break` for graceful fallback.

### Bug 5: stdin.close() OSError ("flush of closed file")
**Problem**: When FFmpeg already exited, closing stdin raised unhandled OSError.

**Fix**: Added try-except wrappers around all `stdin.close()` calls with proper error handling.

### Bug 6: Incorrect Indentation in Crash Detection
**Problem**: NVENC fallback logic was NOT inside the `if ffmpeg_process.poll() is not None:` block, causing it to execute unconditionally and break flow control.

**Fix**: Corrected indentation so fallback logic only runs when FFmpeg has actually crashed.

## Complete Crash Recovery Flow

```
Video Processing Start
    ↓
While Loop (max 2 attempts: NVENC + 1 CPU retry)
    ↓
Start FFmpeg with NVENC (attempt 0)
    ↓
Process chunks (read frames → blend → write to FFmpeg)
    ↓
[FFmpeg crashes with return code -9 / OOM kill]
    ↓
Crash detected via poll() check
    ↓
Set nvenc_failed_this_attempt = True
    ↓
Break out of chunk loop
    ↓
Comprehensive crash detection at end of loop
    ↓
Cleanup: kill FFmpeg, delete temp file
    ↓
Increment cpu_retry_attempt to 1
    ↓
Continue while loop (retry attempt)
    ↓
Start FFmpeg with CPU encoding (libx264)
    ↓
Re-process ALL frames from beginning with CPU
    ↓
Success! Video completes ✓
```

## Files Modified

### `stereocrafter_ui/merging/merging_ui.py`

**Changes:**
1. **Line ~1219**: Removed duplicate FFmpeg process start
2. **Line ~1576**: Changed `raise RuntimeError` to `break` in frame writing crash detection
3. **Line ~1609**: Changed `raise` to `break` in BrokenPipeError handler
4. **Line ~1613**: Changed `raise` to `break` in generic Exception handler
5. **Line ~1599**: Added comprehensive crash detection after chunk loop
6. **Line ~1383-1426**: Fixed indentation of NVENC fallback logic
7. **All stdin.close() calls**: Added try-except wrappers for OSError handling

## Expected Behavior After Fix

### Before Fix
```
10:39:29 - FFmpeg pipe started
10:39:54 - First frame written: 7680x2160
10:40:00 - Error during FFmpeg finalization: flush of closed file
10:40:00 - Deleted incomplete temp file
10:40:00 - Video incomplete: 19/43 frames
[NO OUTPUT FILE]
```

### After Fix
```
10:39:29 - FFmpeg pipe started (attempt 0): 7680x2160 @ 23.976 fps
10:39:54 - First frame written: 7680x2160
10:40:00 - FFmpeg crashed after processing chunks. Return code: -9, frames written: 19/43
10:40:00 - FFmpeg error log (last 15 messages):
10:40:00 -   [hevc_nvenc @ 0x...] Failed to encode frame: Out of memory
10:40:00 - NVENC failed, retrying with CPU encoding (attempt 1/1)...
10:40:01 - CPU encoding retry attempt 1/1...
10:40:01 - Forcing CPU encoding for retry attempt...
10:40:01 - FFmpeg pipe started (attempt 1): 7680x2160 @ 23.976 fps
10:40:01 - Processing frames with libx264...
[PROCESSING CONTINUES]
10:45:30 - Successfully encoded video to Illu_V1-0002_3840_merged_full_sbs.mp4
[OUTPUT FILE CREATED ✓]
```

## Key Improvements

✅ **No more orphaned FFmpeg processes** - Single process lifecycle  
✅ **Automatic crash recovery** - All FFmpeg crashes trigger CPU fallback  
✅ **No more "flush of closed file" errors** - Proper stdin.close() handling  
✅ **No more RuntimeError crashes** - Graceful break instead of raise  
✅ **Comprehensive crash detection** - Catches crashes at ANY point in processing  
✅ **Better error logging** - Captures FFmpeg stderr, return codes, frame counts  
✅ **Complete videos only** - No partial/incomplete output files  
✅ **Handles OOM kills** - Return code -9 (SIGKILL) properly handled  
✅ **Handles segfaults** - Return code -11 (SIGSEGV) properly handled  
✅ **Handles pipe failures** - BrokenPipeError properly handled  

## Testing Checklist

- [x] NVENC encoding succeeds → Video completes with GPU encoding
- [x] NVENC crashes at frame 0 → CPU fallback triggers, video completes
- [x] NVENC crashes mid-video → CPU fallback triggers, video completes
- [x] NVENC crashes between chunks → Comprehensive detection catches it, CPU fallback triggers
- [x] CPU retry also fails → Error reported, moves to next video
- [x] User clicks stop during NVENC → Processing stops cleanly
- [x] User clicks stop during CPU retry → Processing stops cleanly
- [x] stdin.close() on dead FFmpeg → Warning logged, no crash
- [x] BrokenPipeError during frame write → Fallback triggers, no crash

## Performance Impact

| Scenario | Time Impact |
|----------|-------------|
| NVENC succeeds | No impact (fast GPU encoding) |
| NVENC fails → CPU retry | +10-30s restart + slower CPU encoding |
| Both fail | Error reported (no infinite loops) |

**Note**: CPU encoding is significantly slower than NVENC for 8K video, but **the video still completes** instead of failing.

## Limitations

1. **Single CPU retry** - Only one retry attempt to avoid infinite loops
2. **Full re-encode** - Must restart from frame 0 (no checkpoint resume)
3. **No adaptive quality** - CPU retry uses default libx264 settings
4. **Memory intensive** - 8K CPU encoding requires significant system RAM

## Future Enhancements

1. **Checkpoint resume**: Save encoded frames to avoid full re-encode
2. **Adaptive retry**: Detect failure type and choose best recovery strategy
3. **Global NVENC disable**: If NVENC fails X times, disable for entire batch
4. **OOM detection**: Reduce resolution/quality before CPU retry if OOM
5. **Progress preservation**: Only re-encode failed chunks instead of full video

## Related Fixes

- `FFMPEG_FLUSH_FIX.md` - Original stdin.close() fix
- `FFMPEG_STDIN_CLOSE_FIX_COMPLETE.md` - All stdin.close() locations fixed
- `NVENC_CPU_FALLBACK_FIX.md` - NVENC retry loop architecture
- `FFMPEG_CRASH_FALLBACK_FIX.md` - RuntimeError→break fixes
