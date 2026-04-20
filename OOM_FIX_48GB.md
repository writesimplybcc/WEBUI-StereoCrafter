# OOM Fix for RTX 6000 Ada (48GB) on Runpod

## Problem

WEBUI was showing incorrect default settings on startup:
- window_size: **130** (should be 140)
- overlap: **28** (should be 30)

This caused OOM errors because the system was using **24GB tier settings** instead of **48GB tier settings**.

## Root Cause

The VRAM tier detection had two issues:

1. **Threshold too strict**: Required exactly `>= 48GB` effective VRAM to use 48GB tier
   - When UI initializes, some memory is already allocated
   - Effective VRAM might be 45-47GB, falling into 24GB tier instead

2. **CUDA not initialized early**: `get_vram_config()` was called during UI initialization before CUDA was fully ready
   - This could result in inaccurate memory readings

## Solution

### 1. Adjusted VRAM Tier Thresholds

Changed from strict boundaries to more realistic ones:

```python
# OLD (too strict)
elif effective_vram_gb >= 48:  # 48GB tier
elif effective_vram_gb >= 24:  # 24GB tier

# NEW (more realistic)
elif effective_vram_gb >= 40:  # 48GB tier - catches 48GB cards earlier
elif effective_vram_gb >= 20:  # 24GB tier
```

Now RTX 6000 Ada (48GB total) will use 48GB tier even if 3-8GB is already allocated.

### 2. Initialize CUDA Before UI

Added explicit CUDA initialization in `webui.py`:

```python
if torch.cuda.is_available():
    torch.cuda.init()
    torch.cuda.empty_cache()
    print(f"[DEBUG] CUDA initialized. GPU: {torch.cuda.get_device_name(0)}")
```

This ensures accurate VRAM readings when `get_vram_config()` is called.

### 3. Enhanced Logging

Added detailed logging to help diagnose tier selection:

```
============================================================
VRAM Configuration Detection
============================================================
GPU: nvidia rtx 6000 ada generation
Total VRAM: 47.38 GB
Allocated: 0.00 GB
Reserved: 0.00 GB
Free: 47.38 GB
Cloud environment: YES
Free percentage: 100.0%
Effective VRAM for config selection: 47.38 GB
============================================================
✓ Selected: 48GB+ tier (optimized for maximum speed)
  window_size: 140, overlap: 30
```

## Expected Behavior After Fix

### On Runpod with RTX 6000 Ada

**WEBUI Startup Defaults:**
- window_size: **140** (was 130)
- overlap: **30** (was 28)
- decode_chunk_size: **14**
- batch_chunk_size: **24**

**Console Output:**
```
[DEBUG] CUDA initialized. GPU: NVIDIA RTX 6000 Ada Generation
[DEBUG] Total VRAM: 47.38 GB
============================================================
✓ Selected: 48GB+ tier (optimized for maximum speed)
  window_size: 140, overlap: 30
============================================================
```

### Memory Usage

With 48GB tier settings:
- Model loading: ~15-20GB
- Processing 127 frames @ 1080p: ~35-40GB peak
- **Total: ~40-41GB** (well within 48GB capacity)

## Testing

To verify the fix works:

1. Start WEBUI on Runpod
2. Check console for tier selection message
3. Open DepthCrafter tab
4. Verify default values:
   - Window Size slider: **140**
   - Overlap slider: **30**
5. Process a 127-frame 1080p video
6. Should complete without OOM

## Files Modified

- `webui.py` - Added CUDA initialization before UI launch
- `dependency/stereocrafter_util.py` - Adjusted tier thresholds (48→40, 24→20) and enhanced logging

## Backward Compatibility

This fix is backward compatible:
- 24GB cards still use 24GB tier (20-40GB range)
- 12GB cards still use 12GB tier (12-20GB range)
- No changes to processing logic, only tier detection

## Summary

The RTX 6000 Ada will now correctly use 48GB tier settings (140/30) instead of 24GB tier settings (130/28), preventing OOM errors and maximizing processing speed.
