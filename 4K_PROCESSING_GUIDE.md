# 4K Video Processing Guidelines for RTX 6000 Ada

## Confirmed Working Settings (Tested)

**Video:** 3840×2160 (4K), 43 frames  
**GPU:** RTX 6000 Ada (48GB) on Runpod  
**Result:** ✅ Successful

| Parameter | Value |
|-----------|-------|
| Target Height | 2160 |
| Target Width | 3840 |
| Decode Chunk Size | **2** (minimum) |
| Window Size | **30** |
| Overlap | **5** |
| CPU Offload | `model` |
| Disable xFormers | ❌ Unchecked (keep enabled) |

---

## Guidelines by Frame Count

### Short 4K Videos (1-100 frames)

| Frame Count | Decode Chunk | Window Size | Overlap | CPU Offload | Est. Time |
|-------------|--------------|-------------|---------|-------------|-----------|
| 1-50 | 2 | 30 | 5 | model | 2-5 min |
| 51-100 | 2 | 30 | 5 | model | 5-10 min |

**Mode:** Full Video (Process as Segments: ❌)

**Notes:**
- Safe to process in single pass
- Memory has time to stabilize
- Minimal fragmentation risk

---

### Medium 4K Videos (101-500 frames)

| Frame Count | Decode Chunk | Window Size | Overlap | CPU Offload | Est. Time |
|-------------|--------------|-------------|---------|-------------|-----------|
| 101-200 | 2 | 25-30 | 5-8 | model | 10-25 min |
| 201-300 | 2 | 25 | 8 | model | 25-40 min |
| 301-500 | 2 | 20-25 | 8-10 | **sequential** | 40-90 min |

**Mode:** Consider **Process as Segments** for 300+ frames

**Recommended Settings:**
```
Target Height: 2160
Target Width: 3840
Decode Chunk Size: 2
Window Size: 25
Overlap: 8
CPU Offload: sequential (for 300+ frames)
Process as Segments: ✓ (for 300+ frames)
Segment Window Size: 60-80
Segment Overlap: 15-20
```

**Notes:**
- Memory fragmentation becomes a concern
- Sequential offload prevents accumulation
- Segment mode allows recovery from failures

---

### Long 4K Videos (501-1000 frames)

| Frame Count | Decode Chunk | Window Size | Overlap | CPU Offload | Est. Time |
|-------------|--------------|-------------|---------|-------------|-----------|
| 501-700 | 2 | 20 | 10 | sequential | 1.5-2.5 hrs |
| 701-1000 | 2 | 20 | 10 | sequential | 2.5-4 hrs |

**Mode:** **Process as Segments** ✓ (Required)

**Recommended Settings:**
```
Target Height: 2160
Target Width: 3840
Decode Chunk Size: 2
Window Size: 20
Overlap: 10
CPU Offload: sequential
Process as Segments: ✓
Segment Window Size: 60
Segment Overlap: 15
Keep Intermediate NPZ: ✓ (for recovery)
```

**Notes:**
- **Must use segment mode** to avoid memory accumulation
- Process in 60-frame segments with 15-frame overlap
- Keep NPZ files for recovery if merge fails
- Expected: 8-12 segments for 1000 frames

---

### Very Long 4K Videos (1001+ frames)

| Frame Count | Segments | Est. Time | Risk Level |
|-------------|----------|-----------|------------|
| 1001-1500 | 15-25 | 4-7 hrs | Medium |
| 1501-2000 | 25-35 | 7-10 hrs | Medium-High |
| 2001+ | 35+ | 10+ hrs | High |

**Mode:** **Process as Segments** ✓ (Mandatory)

**Recommended Settings:**
```
Target Height: 2160
Target Width: 3840
Decode Chunk Size: 2
Window Size: 20
Overlap: 10
CPU Offload: sequential
Process as Segments: ✓
Segment Window Size: 50-60
Segment Overlap: 15
Keep Intermediate NPZ: ✓
Min Frames to Keep NPZ: 0
```

**Notes:**
- Consider downscaling to 1440p for videos > 2000 frames
- Process in batches if possible (e.g., 1000 frames per batch)
- Monitor VRAM with `watch -n 1 nvidia-smi`
- Expected cost on Runpod: $4-10 @ $1/hr

---

## Alternative: Downscale for Faster Processing

If 4K processing is too slow, consider downscaling:

### 1440p (2560×1440) - 60% Faster

| Frame Count | Decode Chunk | Window Size | Est. Time |
|-------------|--------------|-------------|-----------|
| 100 | 6-8 | 60-80 | 5-8 min |
| 500 | 4-6 | 50-60 | 30-45 min |
| 1000 | 4 | 40-50 | 1-1.5 hrs |

### 1080p (1920×1080) - 75% Faster

| Frame Count | Decode Chunk | Window Size | Est. Time |
|-------------|--------------|-------------|-----------|
| 100 | 10-12 | 100-120 | 3-5 min |
| 500 | 8-10 | 80-100 | 15-25 min |
| 1000 | 6-8 | 60-80 | 30-50 min |

---

## Memory Management Tips

### Before Processing

1. **Clear VRAM:**
   ```bash
   python -c "import torch; torch.cuda.empty_cache()"
   ```

2. **Restart WebUI** if processing multiple videos (prevents memory leaks)

3. **Monitor VRAM:**
   ```bash
   watch -n 1 nvidia-smi
   ```

### During Processing

Watch for these warning signs:

| VRAM Usage | Status | Action |
|------------|--------|--------|
| < 40 GB | ✅ Safe | Continue |
| 40-44 GB | ⚠️ Warning | Monitor closely |
| 44-46 GB | ⚠️ Critical | Consider stopping |
| > 46 GB | ❌ Danger | OOM imminent |

### After Processing

1. **Clear memory:**
   ```python
   import torch
   import gc
   torch.cuda.empty_cache()
   gc.collect()
   ```

2. **Delete intermediate files** if not needed:
   - Remove `_seg` subfolders after successful merge
   - Keep only final merged output

---

## Troubleshooting

### OOM Error During VAE Encoding

**Symptom:** `torch.OutOfMemoryError: Tried to allocate X GiB`

**Solutions:**
1. Reduce `decode_chunk_size` to **2** (minimum)
2. Reduce `window_size` to **20-25**
3. Change CPU Offload to **sequential**
4. Enable **Disable xFormers** (VRAM save mode)
5. Downscale resolution to 1440p or 1080p

### OOM Error During UNet Inference

**Symptom:** OOM in `unet` or `transformer` layers

**Solutions:**
1. Reduce `window_size` further (try **15-20**)
2. Increase `overlap` slightly (helps with smaller windows)
3. Use **Process as Segments** mode
4. Reduce segment window size to **40-50**

### Processing Slowdown Over Time

**Symptom:** First segments fast, later segments much slower

**Cause:** Memory fragmentation

**Solutions:**
1. Use **sequential** CPU offload
2. Reduce segment window size
3. Process in smaller batches
4. Restart between batches

### Merge Failure

**Symptom:** Segments process successfully but merge fails

**Solutions:**
1. Keep intermediate NPZ files enabled
2. Use **Shift & Scale** alignment method
3. Increase segment overlap to **20**
4. Re-merge with adjusted settings

---

## Cost Estimates (Runpod RTX 6000 Ada @ ~$1/hr)

| Video Length | Resolution | Est. Time | Est. Cost |
|--------------|------------|-----------|-----------|
| 100 frames | 4K | 10-15 min | $0.17-0.25 |
| 500 frames | 4K | 1-1.5 hrs | $1.00-1.50 |
| 1000 frames | 4K | 2.5-4 hrs | $2.50-4.00 |
| 100 frames | 1440p | 5-8 min | $0.08-0.13 |
| 500 frames | 1440p | 30-45 min | $0.50-0.75 |
| 1000 frames | 1440p | 1-1.5 hrs | $1.00-1.50 |
| 100 frames | 1080p | 3-5 min | $0.05-0.08 |
| 500 frames | 1080p | 15-25 min | $0.25-0.42 |
| 1000 frames | 1080p | 30-50 min | $0.50-0.83 |

---

## Quick Reference Card

### For 4K Videos:

```
┌─────────────────────────────────────────────────────────┐
│  Frames    │  Mode      │  Decode  │  Window  │  Overlap│
├─────────────────────────────────────────────────────────┤
│  1-100     │  Full      │    2     │    30    │    5    │
│  101-300   │  Full      │    2     │    25    │    8    │
│  301-500   │  Segment*  │    2     │    20    │   10    │
│  501-1000  │  Segment   │    2     │    20    │   10    │
│  1000+     │  Segment   │    2     │    20    │   10    │
└─────────────────────────────────────────────────────────┘
* = Use sequential CPU offload for 300+ frames
```

### For 1440p Videos:

```
┌─────────────────────────────────────────────────────────┐
│  Frames    │  Mode      │  Decode  │  Window  │  Overlap│
├─────────────────────────────────────────────────────────┤
│  1-200     │  Full      │    6     │    60    │   12    │
│  201-500   │  Full      │    4     │    50    │   12    │
│  501-1000  │  Segment   │    4     │    40    │   10    │
│  1000+     │  Segment   │    4     │    40    │   10    │
└─────────────────────────────────────────────────────────┘
```

### For 1080p Videos:

```
┌─────────────────────────────────────────────────────────┐
│  Frames    │  Mode      │  Decode  │  Window  │  Overlap│
├─────────────────────────────────────────────────────────┤
│  1-500     │  Full      │   10     │   100    │   15    │
│  501-1000  │  Full      │    8     │    80    │   15    │
│  1001-2000 │  Segment   │    6     │    60    │   12    │
│  2000+     │  Segment   │    6     │    60    │   12    │
└─────────────────────────────────────────────────────────┘
```

---

## Summary

**Golden Rules for 4K on RTX 6000 Ada:**

1. **Always use `decode_chunk_size = 2`** for native 4K
2. **Keep `window_size ≤ 30`** for full video mode
3. **Use segment mode for 300+ frames**
4. **Switch to sequential offload for 500+ frames**
5. **Consider 1440p/1080p for very long videos** (1000+ frames)
6. **Monitor VRAM** during first segment to gauge headroom
7. **Keep intermediate NPZ** for long videos (recovery option)

**Tested & Verified:** ✅ 4K @ 43 frames with settings above
