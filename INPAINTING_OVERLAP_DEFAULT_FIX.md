# Inpainting Overlap Default Value Fix

## Problem

The Inpainting tab was using a hardcoded default overlap value of **3**, which didn't match the VRAM tier configuration used by DepthCrafter (which uses overlap: 8 for ULTRA-CONSERVATIVE tier).

**Before:**
- Inpainting default overlap: **3** (hardcoded)
- DepthCrafter default overlap: **8** (ULTRA-CONSERVATIVE tier)
- **Result:** Inconsistent settings between tabs

---

## Root Cause

**File:** `inpainting_gui.py` (Line 59)

```python
# OLD CODE
self.overlap_var = tk.StringVar(value=str(self.app_config.get("frame_overlap", 3)))
```

The value `3` was hardcoded and didn't consider the GPU's VRAM tier configuration.

---

## Solution

Updated the Inpainting GUI to use `get_vram_config()` to determine the appropriate overlap value based on the GPU's VRAM tier.

### Changes Made

**File:** `inpainting_gui.py`

#### 1. Added Import (Line ~26)

```python
from dependency.stereocrafter_util import (
    Tooltip, logger, get_video_stream_info, draw_progress_bar,
    release_cuda_memory, set_util_logger_level,
    encode_frames_to_mp4, read_video_frames_decord,
    get_vram_config  # ← NEW
)
```

---

#### 2. Updated Overlap Initialization (Line ~60)

**Before:**
```python
self.overlap_var = tk.StringVar(value=str(self.app_config.get("frame_overlap", 3)))
```

**After:**
```python
# Get overlap from VRAM config if not in app_config, otherwise use default
try:
    vram_config = get_vram_config()
    default_overlap = vram_config.get('overlap', 8)  # Default to 8 (ULTRA-CONSERVATIVE tier)
except Exception:
    default_overlap = 8  # Fallback if VRAM detection fails

self.overlap_var = tk.StringVar(value=str(self.app_config.get("frame_overlap", default_overlap)))
```

---

## Expected Behavior

### VRAM Tier Overlap Values

| VRAM Tier | Overlap Value | GPU Examples |
|-----------|---------------|--------------|
| **ULTRA-CONSERVATIVE (< 8GB)** | 8 | RTX 3060 (constrained) |
| **CONSERVATIVE (8-12GB)** | 12 | RTX 3060, RTX 3070 |
| **12GB Tier** | 20 | RTX 3080 (12GB) |
| **24GB Tier** | 28 | RTX 3090, RTX 4090 |
| **48GB Tier** | 15 | RTX 6000 Ada |

---

### Startup Behavior

**First Launch (No Config File):**
```
1. GUI starts
2. get_vram_config() detects GPU VRAM
3. Overlap set to tier-appropriate value (e.g., 8 for ULTRA-CONSERVATIVE)
4. User sees: Overlap = 8 (instead of 3)
```

---

**Subsequent Launches (With Config File):**
```
1. GUI starts
2. Reads frame_overlap from config file
3. Overlap set to saved value
4. User sees: Overlap = [previously saved value]
```

---

**User Override:**
```
1. User manually changes overlap to 15
2. Saves config (auto-saved on close)
3. Next launch: Overlap = 15 (user preference preserved)
```

---

## Benefits

### ✅ Consistency
- Inpainting and DepthCrafter tabs now use same VRAM-aware defaults
- No more confusion about different default values

### ✅ VRAM-Optimized
- Overlap value matches GPU capabilities
- Prevents OOM errors from inappropriate defaults

### ✅ User Preference Preserved
- If user has saved overlap in config, that value is used
- VRAM config only applies to first-time users or reset settings

---

## Technical Details

### VRAM Detection Flow

```
GUI Startup
    ↓
get_vram_config() called
    ↓
Checks GPU:
  - Total VRAM
  - Currently allocated VRAM
  - Cloud vs Local environment
    ↓
Selects tier:
  - ULTRA-CONSERVATIVE (< 8GB)
  - CONSERVATIVE (8-12GB)
  - 12GB Tier
  - 24GB Tier
  - 48GB Tier
    ↓
Returns config dict:
  {
    'overlap': 8,
    'window_size': 50,
    'decode_chunk_size': 2,
    ...
  }
    ↓
GUI uses overlap value
```

---

### Error Handling

If VRAM detection fails:
```python
try:
    vram_config = get_vram_config()
    default_overlap = vram_config.get('overlap', 8)
except Exception:
    default_overlap = 8  # Fallback
```

**Fallback value:** 8 (ULTRA-CONSERVATIVE tier)
- Safe for all GPUs
- Prevents OOM errors
- Can be manually increased by user

---

## Testing

### Test Case 1: First Launch

1. Delete/rename config file: `config_inpainting.json`
2. Launch Inpainting GUI
3. **Expected:** Overlap shows tier-appropriate value (e.g., 8, 12, 15, 20, or 28)
4. **Check console:** Should see VRAM detection logs

---

### Test Case 2: Config File Exists

1. Set overlap to custom value (e.g., 15)
2. Close GUI (config auto-saves)
3. Reopen GUI
4. **Expected:** Overlap shows 15 (saved value)

---

### Test Case 3: VRAM Detection Failure

1. Simulate VRAM detection failure (modify code temporarily)
2. Launch GUI
3. **Expected:** Overlap shows 8 (fallback value)
4. **Check console:** Should see error log

---

## Comparison

### Before Fix

| Tab | Default Overlap | Source |
|-----|-----------------|--------|
| **DepthCrafter** | 8 (ULTRA-CONSERVATIVE) | VRAM config |
| **Inpainting** | 3 (hardcoded) | Hardcoded |
| **Splatting** | Varies | Task-specific |

**Result:** ❌ Inconsistent defaults

---

### After Fix

| Tab | Default Overlap | Source |
|-----|-----------------|--------|
| **DepthCrafter** | 8 (ULTRA-CONSERVATIVE) | VRAM config |
| **Inpainting** | 8 (ULTRA-CONSERVATIVE) | VRAM config ✅ |
| **Splatting** | Varies | Task-specific |

**Result:** ✅ Consistent defaults

---

## Related Files

- `inpainting_gui.py` - Main fix location
- `dependency/stereocrafter_util.py` - VRAM config function
- `depthcrafter_gui_seg.py` - DepthCrafter GUI (already uses VRAM config)

---

## Future Enhancements

Potential improvements:

1. **Sync All Tabs**
   - Add VRAM config to Splatting tab
   - Single source of truth for all defaults

2. **VRAM Config Display**
   - Show detected VRAM tier in GUI
   - Display recommended settings

3. **One-Click Presets**
   - "Conservative", "Balanced", "Aggressive" buttons
   - Adjusts all settings at once

4. **Real-Time VRAM Monitor**
   - Show current VRAM usage
   - Warn if approaching limit

---

**Date:** 2026-03-10  
**Status:** ✅ Fixed  
**Issue:** Inpainting overlap default (3) didn't match VRAM tier  
**Resolution:** Now uses `get_vram_config()` for tier-appropriate defaults
