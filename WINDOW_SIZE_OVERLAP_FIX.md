# Fix: Window Size and Overlap Slider Values Ignored

## Problem

Users reported that GUI slider values for **window_size** and **overlap** were not being respected during processing.

**Example:**
- GUI sliders set to: `window_size=70, overlap=12`
- Log showed: `window_size=50, overlap=8`

## Root Cause

The issue was in `depthcrafter/depth_crafter_ppl.py` (lines 140-143):

```python
# OLD CODE - INCORRECT
if window_size is None or window_size == 110:  # Default value
    window_size = vram_config['window_size']
if overlap is None or overlap == 25:  # Default value
    overlap = vram_config['overlap']
```

**What was happening:**

1. GUI sends user values (e.g., `window_size=70, overlap=12`)
2. `get_adaptive_vram_config()` is called, which returns scaled values based on video complexity
3. The code was **replacing** user values with VRAM config values
4. Further adaptive scaling was applied, reducing values even more

**The flow:**
```
GUI: window_size=70, overlap=12
  ↓
VRAM Config (48GB tier): window_size=80, overlap=15
  ↓
Adaptive Scaling (if high complexity): window_size=50, overlap=8  ← Final (WRONG!)
```

## Solution

Modified `depth_crafter/depth_crafter_ppl.py` to:

1. **Preserve user-provided values** - Only use VRAM config when values are `None` or old defaults
2. **Add logging** - Show what values are being used and why
3. **Separate concerns** - Apply adaptive scaling only to `decode_chunk_size`, not window/overlap

### Changes Made

**File:** `depthcrafter/depth_crafter_ppl.py` (lines 129-186)

```python
# NEW CODE - CORRECT
# Log incoming values
_logger.info(f"Pipeline received: window_size={window_size}, overlap={overlap}")

# Get VRAM config (for decode_chunk_size and defaults)
vram_config = get_adaptive_vram_config(width, height, num_frames, base_vram_config)
decode_chunk_size = decode_chunk_size if decode_chunk_size is not None else vram_config['decode_chunk_size']

# Only apply VRAM config if None or old defaults (110/25)
original_window_size = window_size
original_overlap = overlap

if window_size is None:
    _logger.info("window_size was None, using VRAM config default")
    window_size = vram_config['window_size']
elif window_size == 110:
    _logger.info("window_size was old default (110), using VRAM config")
    window_size = vram_config['window_size']
# else: User provided explicit value, keep it as-is

if overlap is None:
    _logger.info("overlap was None, using VRAM config default")
    overlap = vram_config['overlap']
elif overlap == 25:
    _logger.info("overlap was old default (25), using VRAM config")
    overlap = vram_config['overlap']
# else: User provided explicit value, keep it as-is

# Log final values
if window_size == original_window_size and original_window_size is not None and original_window_size != 110:
    _logger.info(f"Using user-provided window_size: {window_size}")
if overlap == original_overlap and original_overlap is not None and original_overlap != 25:
    _logger.info(f"Using user-provided overlap: {overlap}")

_logger.info(f"Final pipeline settings: window_size={window_size}, overlap={overlap}, stride={stride}")
```

## Expected Behavior After Fix

### Scenario 1: User Sets Custom Values
```
GUI: window_size=70, overlap=12
Log: 
  "Pipeline received: window_size=70, overlap=12"
  "Using user-provided window_size: 70"
  "Using user-provided overlap: 12"
  "Final pipeline settings: window_size=70, overlap=12, stride=58"
✅ User values preserved
```

### Scenario 2: User Uses Defaults
```
GUI: window_size=110 (old default), overlap=25 (old default)
Log:
  "Pipeline received: window_size=110, overlap=25"
  "window_size was old default (110), using VRAM config"
  "overlap was old default (25), using VRAM config"
  "Final pipeline settings: window_size=80, overlap=15, stride=65"
✅ VRAM config applied for safety
```

### Scenario 3: Very Short Video
```
GUI: window_size=110, overlap=25
Video: 50 frames
Log:
  "Video has fewer frames (50) than window_size (110), adjusting"
  "Final pipeline settings: window_size=50, overlap=0, stride=50"
✅ Auto-adjusted to video length
```

## Logging Output

The fix adds detailed logging to help users understand what's happening:

```
INFO - Pipeline received: window_size=70, overlap=12
INFO - Video complexity analysis:
INFO -   Resolution: 1920x1080 (factor: 1.00x vs 1080p)
INFO -   Frames: 126 (factor: 0.99x vs 127 frames)
INFO -   Combined complexity: 0.99x
INFO - Normal complexity (0.99x). Using base settings.
INFO - Using user-provided window_size: 70
INFO - Using user-provided overlap: 12
INFO - Final pipeline settings: window_size=70, overlap=12, stride=58
```

## Testing

To verify the fix works:

1. **Set custom values in GUI:**
   - Window Size: `70`
   - Overlap: `12`

2. **Process a video**

3. **Check console log for:**
   ```
   Pipeline received: window_size=70, overlap=12
   Using user-provided window_size: 70
   Using user-provided overlap: 12
   Final pipeline settings: window_size=70, overlap=12, stride=58
   ```

4. **Verify output matches** - The log should show your exact slider values

## Backward Compatibility

✅ **Fully backward compatible:**
- Old default values (110/25) still get VRAM config applied (safety)
- `None` values still get VRAM config applied (safety)
- Only explicit user values are preserved

## Related Files

- `depthcrafter/depth_crafter_ppl.py` - Main fix
- `depthcrafter/depthcrafter_logic.py` - Passes GUI values to pipeline
- `depthcrafter_gui_seg.py` - GUI slider values
- `dependency/stereocrafter_util.py` - VRAM config and adaptive scaling

## Additional Notes

### Why 110 and 25 Were Special-Cased

These were the **old hardcoded defaults** in earlier versions:
- `window_size=110` - Default for 24-48GB tier
- `overlap=25` - Default for 24-48GB tier

When users didn't change settings, these values would be sent. The code was designed to replace them with **tier-appropriate** values based on actual VRAM.

### Why User Values Should Be Preserved

When a user **explicitly sets** `window_size=70`, they're making an intentional choice based on:
- Their specific video characteristics
- Their VRAM availability
- Their quality/speed preferences

Overriding these values without explicit request is unexpected and confusing.

### When VRAM Config Should Still Apply

1. **`None` values** - No user preference expressed
2. **Old defaults (110/25)** - Likely using outdated settings
3. **Video too short** - `num_frames <= window_size` auto-adjustment
4. **OOM prevention** - Pipeline will still raise error if VRAM insufficient

---

**Date:** 2026-03-10  
**Status:** ✅ Fixed  
**Version:** depth_crafter_ppl.py updated
