# FFmpeg "Flush of Closed File" Error Fix

## Problem
When using "Blend All Videos" in the Merging UI with RTX A6000 and output format as full SBS, the encoding would fail with the error:
```
Error during FFmpeg finalization: flush of closed file
Deleted incomplete temp file: Illu_V1-0002_3840_merged_full_sbs.temp.mp4
```

The issue occurred when FFmpeg crashed between processing chunks (e.g., after writing 24 frames in the first chunk, during processing of the second chunk with 19 frames).

## Root Cause
The original code had a flaw in the FFmpeg finalization logic:

1. When closing FFmpeg's stdin pipe, if FFmpeg had already crashed/exited, it would raise an `OSError: flush of closed file`
2. The code caught this error and logged it as a warning, but **continued execution**
3. It then tried to call `ffmpeg_process.communicate()`, which would either:
   - Try to interact with an already-dead process
   - Return incorrect data
   - Raise another exception

4. The exception handlers weren't properly structured to handle this crash scenario, leading to incomplete error handling and temp file deletion without clear error reporting.

## Solution
The fix improves FFmpeg crash detection and handling:

### Key Changes in `stereocrafter_ui/merging/merging_ui.py`:

1. **Added `handle_ffmpeg_crash()` helper function**: Consolidates all crash cleanup logic (logging stderr, deleting temp files, reporting errors)

2. **Detect FFmpeg crash before stdin close**: When `stdin.close()` raises an OSError, check if FFmpeg is still running using `poll()`:
   - If `poll() is not None`: FFmpeg has already exited → treat as crash
   - If FFmpeg is still running: proceed to `communicate()` normally

3. **Proper flow control with `continue`**: When a crash is detected, immediately `continue` to the next video after cleanup, preventing fall-through to success path

4. **Track finalization state**: Use `ffmpeg_finalized` flag to prevent calling `communicate()` on an already-crashed process

5. **Better error reporting**: Log FFmpeg's return code, frames written, encoding parameters, and captured stderr to help diagnose the actual FFmpeg error

### Error Handling Flow:
```
Try to close stdin
  ↓
OSError raised? → Check if FFmpeg still running
  ↓                    ↓
  Yes              No (crashed)
  ↓                    ↓
communicate()     handle_ffmpeg_crash()
  ↓                    ↓
check returncode  yield error + continue
  ↓
returncode != 0?
  ↓
  Yes → yield error + continue
  No  → success → rename temp file
```

## Benefits
- **Clearer error messages**: Users see "FFmpeg crashed during encoding" instead of generic "finalization failed"
- **Complete error logging**: Captures FFmpeg's actual error output before it crashed
- **Proper cleanup**: Temp files are deleted on failure
- **No false successes**: Prevents continuing when FFmpeg has crashed
- **Better debugging**: Logs frame count, dimensions, and codec info for crash analysis

## Testing
To verify the fix works:
1. Run a merge operation that previously triggered the error
2. Check that if FFmpeg crashes, you now see:
   - Clear "FFmpeg crashed during encoding" error message
   - FFmpeg's actual error output in the logs
   - Return code and frame count information
   - Incomplete temp file properly deleted

## Files Modified
- `stereocrafter_ui/merging/merging_ui.py` (lines ~1584-1685)
