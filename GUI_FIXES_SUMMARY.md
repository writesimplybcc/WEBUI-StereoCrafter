# GUI Fixes: Clear VRAM Button & Cancel State Reset

## Summary

Two critical issues have been fixed in the DepthCrafter GUI (`depthcrafter_gui_seg.py`):

1. ✅ **Added "Clear VRAM" button** - Manual memory clearing without restarting
2. ✅ **Fixed Cancel button state** - Prevents "stuck cancel" issue

---

## Issue 1: No Option to Clear PyTorch Memory

### Problem
When the WEBUI runs out of memory, users had no way to clear PyTorch CUDA cache without completely restarting the application.

### Solution
Added a **"Clear VRAM"** button that:
- Runs `gc.collect()` to clean up Python objects
- Executes `torch.cuda.empty_cache()` to clear CUDA cache
- Displays a dialog showing how much VRAM was freed
- Shows before/after memory statistics in the log

### Implementation Details

**File Modified:** `depthcrafter_gui_seg.py`

**Changes:**
1. Added new button in the control panel (line ~1839-1841):
   ```python
   clear_vram_frame = ttk.Frame(button_container_frame)
   self.clear_vram_button = ttk.Button(clear_vram_frame, text="Clear VRAM", 
                                        command=self.clear_vram_memory, width=10)
   ```

2. Added new method `clear_vram_memory()` (line ~2387-2419):
   - Checks CUDA availability
   - Measures memory before/after clearing
   - Shows user-friendly dialog with VRAM freed
   - Logs detailed memory statistics

3. Added help tooltip text in `help_content.json`

### Usage
Click the **"Clear VRAM"** button anytime to free memory. A dialog will show:
```
Successfully freed 12.45 GB of VRAM.

Before: 38.50 GB reserved
After:  26.05 GB reserved
```

---

## Issue 2: Cancel Button Keeps Cancelling Subsequent Starts

### Problem
After pressing Cancel once, the system would immediately cancel all subsequent Start presses. The Cancel state was "stuck" and wouldn't reset.

### Root Cause
The `stop_event` (a `threading.Event`) was being set to `True` when Cancel was pressed, but was **not being cleared** when starting a new processing job. This caused the new job to immediately see the stop signal and abort.

### Solution
Added explicit `stop_event.clear()` calls at the beginning of all processing start methods:

**Files Modified:** 
- `depthcrafter_gui_seg.py`
- `depthcrafter/help_content.json` (for button tooltip)

**Changes:**

1. **`start_thread()` method** (line ~2014-2023):
   ```python
   def start_thread(self):
       # Check if processing is already running
       if self.processing_thread and self.processing_thread.is_alive():
           _logger.warning("Processing is already running.")
           return

       # CRITICAL FIX: Always clear the stop event when starting new processing
       self.stop_event.clear()
       _logger.debug("stop_event cleared for new processing job")
       
       # ... rest of method
   ```

2. **`re_merge_from_gui()` method** (line ~2009-2011):
   ```python
   # CRITICAL FIX: Clear stop event for re-merge operations
   self.stop_event.clear()
   _logger.debug("stop_event cleared for re-merge job")
   ```

3. **`generate_segment_visuals_from_gui()` method** (line ~1865-1867):
   ```python
   # CRITICAL FIX: Clear stop event for generate visuals operations
   self.stop_event.clear()
   _logger.debug("stop_event cleared for generate visuals job")
   ```

### Testing
To verify the fix works:
1. Start a processing job
2. Press Cancel to stop it
3. Press Start again - the job should now start normally (not immediately cancel)

---

## Button Layout (Updated)

The control panel now has the following buttons (left to right):

```
[Start] [Cancel] [Clear VRAM] [Re-Merge Segments] [Generate Seg Visuals]
```

---

## Benefits

### Clear VRAM Button
- ✅ No need to restart the GUI to free memory
- ✅ Useful between processing jobs
- ✅ Helps diagnose memory issues
- ✅ Shows exact VRAM amounts (before/after)

### Cancel State Fix
- ✅ Cancel works as expected
- ✅ Can restart after cancelling
- ✅ Applies to all processing types (main, re-merge, visuals)
- ✅ Proper logging for debugging

---

## Technical Notes

### Memory Management
The Clear VRAM function uses two approaches:
1. **`gc.collect()`** - Python's garbage collector cleans up unreferenced objects
2. **`torch.cuda.empty_cache()`** - PyTorch releases cached CUDA memory back to the system

**Important:** This clears the *cache*, not allocated memory. Active tensors remain in use.

### Threading
The `stop_event` is a `threading.Event` object used for thread-safe communication:
- `set()` - Signals threads to stop
- `clear()` - Resets the signal
- `is_set()` - Checks if stop was requested

The fix ensures the event is always cleared before starting new work.

---

## Files Changed

1. `depthcrafter_gui_seg.py` - Main GUI code
2. `depthcrafter/help_content.json` - Help tooltip text

---

## Backward Compatibility

✅ Both changes are fully backward compatible:
- Existing functionality unchanged
- New button is additive (doesn't replace anything)
- Cancel fix restores expected behavior
- No configuration changes required

---

## Future Enhancements

Potential improvements:
- Auto-clear VRAM option after each job
- Memory usage indicator in status bar
- Configurable hotkey for Clear VRAM
- Warning when VRAM usage exceeds threshold

---

## Related Documentation

- `VRAM_USAGE_GUIDE.md` - Understanding VRAM tiers
- `MEMORY_OPTIMIZATION_CHANGES.md` - Memory optimization history
- `depthcrafter/help_content.json` - All GUI tooltips

---

**Date:** 2026-03-10  
**Version:** GUI 25-11-01.0+  
**Status:** ✅ Implemented and Ready for Testing
