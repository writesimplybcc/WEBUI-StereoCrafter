# FFmpeg Finalization Fix - "flush of closed file" Error

## Problem

When using **Blend All Videos** with RTX A6000 and output format as **Full SBS**, the merging process failed with:

```
05:59:51 - Error during FFmpeg finalization: flush of closed file
05:59:51 - Deleted incomplete temp file: Illu_V1-0002_3840_merged_full_sbs.temp.mp4
05:59:51 - Video Illu_V1-0002_1920_inpainted.mp4 incomplete: 19/43 frames
```

Only 19 out of 43 frames were processed, and the video was not saved.

## Root Cause

The bug was in the **NVENC-to-CPU fallback retry logic** in `stereocrafter_ui/merging/merging_ui.py`.

When FFmpeg crashed during NVENC encoding (common with 8K Full SBS output), the code was supposed to:
1. Detect the crash
2. Clean up the failed process
3. **Retry with CPU encoding**

However, there were **two critical bugs**:

### Bug 1: Incorrect `break` instead of `continue`
When FFmpeg crashed during stdin close (line ~1772), the code:
- Set `processing_completed = False` to signal a retry
- Incremented `cpu_retry_attempt`
- Called `break` to exit the finalization block

**The problem**: The `break` statement exited the **while loop** entirely, preventing the retry logic from executing. After the while loop, the code checked `if processing_completed:` and since it was `False`, it logged the incomplete message and **didn't retry**.

### Bug 2: Missing stdin error handling
When stdin close failed but FFmpeg was still running (race condition), the code continued to call `communicate()`, which could raise another exception that wasn't properly handled for retry.

## Fix Applied

### Change 1: Replace `break` with `continue` (lines ~1812, ~1834)
Changed from:
```python
break  # Break out of finalization block, while loop will detect processing_completed=False
```

To:
```python
continue  # Continue the while loop for CPU retry
```

This allows the while loop to re-check its condition and retry with CPU encoding since `processing_completed=False` and `cpu_retry_attempt` was incremented.

### Change 2: Handle race condition (line ~1814)
Added handling for when stdin close fails but FFmpeg is still running:
```python
else:
    # FFmpeg is still running but stdin close failed - this is unusual
    # Mark as failure anyway since stdin is broken
    logger.warning(f"FFmpeg stdin closed but process still running. Marking as failure.")
    nvenc_failed_this_attempt = True
    nvenc_failed = True
    nvenc_failed_at_frame = frame_count
    processing_completed = False
    cpu_retry_attempt += 1
    handle_ffmpeg_crash()
    ffmpeg_finalized = True
    # ... cleanup ...
    continue  # Continue the while loop for CPU retry
```

### Change 3: Enhanced outer exception handler (lines 1919-1962)
Added detection of stdin-related errors in the outer exception handler to trigger CPU retry:
```python
except Exception as finalize_err:
    error_str = str(finalize_err).lower()
    is_stdin_error = any(keyword in error_str for keyword in [
        'flush', 'closed file', 'broken pipe', 'invalid argument',
        'i/o operation'
    ])
    
    if is_stdin_error and frame_count < num_frames:
        # FFmpeg crashed during finalization - trigger retry with CPU
        nvenc_failed_this_attempt = True
        processing_completed = False
        cpu_retry_attempt += 1
        # ... cleanup ...
        continue  # Continue the while loop for CPU retry
```

## Expected Behavior After Fix

1. **First attempt**: Try NVENC encoding (fast GPU encoding)
2. **If FFmpeg crashes** (during frame writing OR finalization):
   - Detect the crash
   - Clean up the failed process
   - **Automatically retry with CPU encoding** (libx264/libx265)
3. **Second attempt**: Complete the merge with CPU encoding (slower but more reliable)
4. **Success**: Video is saved to `./final_videos/`

## Testing

To test the fix:
1. Use RTX A6000 (or any NVIDIA GPU)
2. Process a video with **Full SBS** output format
3. Use **Blend All Videos** or **Blend Current Video**
4. If NVENC fails (which is common with 8K Full SBS), the code should automatically retry with CPU encoding
5. The video should complete successfully and be saved

## Files Modified

- `stereocrafter_ui/merging/merging_ui.py` (lines 1770-1962)
  - Fixed retry logic in FFmpeg finalization
  - Added better error detection and logging
  - Enhanced stdin close error handling

## Additional Notes

- The fix maintains backward compatibility - if NVENC succeeds, no retry is needed
- CPU encoding fallback is slower but more reliable for high-resolution merges
- The fix also applies to single video blending (Blend Current Video)
- Debug logging added to help diagnose future issues
