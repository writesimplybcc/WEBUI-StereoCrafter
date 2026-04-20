# Progress Tracking Fix for Gradio WebUI

**Date:** 2026-03-11  
**Issue:** Progress not properly showing when each file is finished processing

---

## Summary

Fixed progress tracking issues in Gradio WebUI components where the UI would not properly show completion status for each file processed.

---

## Issues Found

### 1. ✅ **inpainting_ui.py** - FIXED
**Problem:** 5-minute timeout caused premature exit for long videos

```python
# BEFORE (BROKEN)
max_wait_time = 300  # Maximum 5 minutes wait
start_time = time.time()

if time.time() - start_time > max_wait_time:
    break  # Exit even if processing continues!

# AFTER (FIXED)
# No timeout - wait for processing to complete naturally
# For very long videos, timeout would cause premature exit

while self.processing_thread.is_alive():
    if self.stop_event.is_set():
        self.processing_thread.join(timeout=2.0)
        last_status = "⏹️ Processing stopped by user"
        break
```

**Impact:** Videos longer than 5 minutes would show as "stopped" even though processing continued in background.

---

### 2. ✅ **splatting_ui.py** - FIXED
**Problem:** No progress tracking at all - thread started and forgotten

```python
# BEFORE (BROKEN)
def start_processing(self, ...):
    # Just starts thread and returns immediately
    self.processing_thread = threading.Thread(target=self._run_batch_process, args=(settings,))
    self.processing_thread.start()
    # No progress updates!

# AFTER (FIXED)
def start_processing(self, ..., progress=gr.Progress()):
    """Starts the video processing with progress tracking."""
    self.stop_event.clear()
    
    # ... setup code ...
    
    for idx, video_path in enumerate(input_videos):
        # Update progress for each video
        video_name = os.path.basename(video_path)
        progress((idx / len(input_videos)), desc=f"Processing {idx+1}/{len(input_videos)}: {video_name}")
        
        # Process video
        tasks_processed, any_success = self._process_single_video_tasks(...)
        
        # Log completion
        if any_success:
            logger.info(f"✅ Completed: {video_name}")
        else:
            logger.warning(f"⚠️ Failed or skipped: {video_name}")
    
    # Final progress update
    progress(1.0, desc="✅ Processing completed!")
```

**Impact:** Users had no visibility into processing progress, just terminal logs.

---

### 3. ✅ **depthcrafter_ui.py** - ALREADY CORRECT
Uses `progress=gr.Progress()` correctly with proper updates throughout processing.

---

### 4. ✅ **merging_ui.py** - ALREADY CORRECT
Uses `yield` generator pattern for progress updates.

---

## Files Modified

| File | Issue | Status |
|------|-------|--------|
| `stereocrafter_ui/inpainting/inpainting_ui.py` | 5-minute timeout | ✅ Fixed |
| `stereocrafter_ui/splatting/splatting_ui.py` | No progress tracking | ✅ Fixed |
| `stereocrafter_ui/depthcrafter/depthcrafter_ui.py` | - | ✅ Already correct |
| `stereocrafter_ui/merging/merging_ui.py` | - | ✅ Already correct |

---

## What Changed

### inpainting_ui.py

**Line ~744:** Removed timeout logic
- Removed `max_wait_time = 300`
- Removed `start_time = time.time()`
- Removed timeout check condition
- Now waits naturally for processing thread to complete

### splatting_ui.py

**Line ~3411:** Added `progress=gr.Progress()` parameter
**Line ~2533-2555:** Added progress updates in main loop
- Shows current video name and number
- Shows completion percentage
- Logs success/failure for each video
- Shows final completion message

---

## Expected Behavior Now

### Before Fix

```
User clicks START
→ UI shows "Processing..." 
→ 5 minutes later: "Processing stopped" (even though still running!)
→ No indication which video is being processed
→ No completion notification
```

### After Fix

```
User clicks START
→ Progress bar shows: "Processing 1/5: video1.mp4" [20%]
→ Progress bar shows: "Processing 2/5: video2.mp4" [40%]
→ Progress bar shows: "Processing 3/5: video3.mp4" [60%]
→ Progress bar shows: "Processing 4/5: video4.mp4" [80%]
→ Progress bar shows: "Processing 5/5: video5.mp4" [100%]
→ Final: "✅ Processing completed!"
→ Terminal logs show: "✅ Completed: video1.mp4"
```

---

## Testing

### Test Case 1: Short Videos (< 1 min each)
**Expected:** Progress updates quickly through each video

### Test Case 2: Long Videos (> 5 min each)
**Expected:** Progress continues past 5-minute mark (no timeout)

### Test Case 3: Multiple Videos
**Expected:** Shows "Processing X/Y: filename" for each

### Test Case 4: Stop Button
**Expected:** Shows "⏹️ Processing stopped by user"

### Test Case 5: Error During Processing
**Expected:** Shows error message, stops gracefully

---

## Technical Details

### Gradio Progress Tracking

Gradio provides two patterns for progress:

**1. Direct progress() calls (used in splatting):**
```python
def process(..., progress=gr.Progress()):
    for i, item in enumerate(items):
        progress(i / len(items), desc=f"Processing {i+1}/{len(items)}")
        # Do work
```

**2. Generator yield pattern (used in merging):**
```python
def process(...):
    for i, item in enumerate(items):
        yield f"Processing {i+1}/{len(items)}", (i / len(items) * 100)
        # Do work
```

### Why Timeout Was Bad

The 5-minute timeout in `inpainting_ui.py` was likely added to prevent UI freezing, but:
- Processing continues in background thread anyway
- UI just stops showing updates
- User thinks processing failed
- No way to know when it actually completes

**Better approach:** Let it run naturally, user can always click STOP if needed.

---

## Recommendations

### For Users

1. **Watch the progress bar** - shows current video and percentage
2. **Check terminal logs** - shows detailed completion status
3. **Use STOP button** if you need to cancel - shows "stopped" message
4. **Long videos are OK** - no more 5-minute timeout

### For Developers

1. **Always use `progress=gr.Progress()`** for long operations
2. **Update progress in loops** - shows which item is being processed
3. **Log completion** - helps debugging and user confidence
4. **Don't use timeouts** - let operations complete naturally
5. **Provide STOP functionality** - users can cancel if needed

---

## Related Files

- `stereocrafter_ui/inpainting/inpainting_ui.py` - Line 744-755
- `stereocrafter_ui/splatting/splatting_ui.py` - Line 2533-2555, 3411
- `stereocrafter_ui/depthcrafter/depthcrafter_ui.py` - Already correct
- `stereocrafter_ui/merging/merging_ui.py` - Already correct

---

**Status:** ✅ Complete  
**Tested:** Syntax verified  
**Next Steps:** Test with actual video processing
