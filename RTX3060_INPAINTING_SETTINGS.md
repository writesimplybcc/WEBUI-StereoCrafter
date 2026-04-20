# RTX 3060 Inpainting Settings Guide
## For 854×480 (480p) Video

**Created:** 2026-03-11  
**GPU:** RTX 3060 12GB  
**Resolution:** 854×480 (480p)  
**Estimated VRAM Usage:** 7-9 GB

---

## Quick Start

### Load Preset Config

1. Open Inpainting WebUI
2. Click **"Load Settings"** button
3. Select: `config_inpainting_rtx3060_480p.json`
4. Settings will be applied automatically

---

## Recommended Settings (Balanced)

| Setting | Value | Description |
|---------|-------|-------------|
| **Inference Steps** | `6` | Quality vs speed balance |
| **Decode Chunk Size** | `6` | Frames decoded at once |
| **Tile Number** | `1` | Disabled (480p is small) |
| **Frames Chunk** | `14` | Frames processed per batch |
| **Frame Overlap** | `3` | Temporal consistency |
| **Input Blend** | `0.0` | No original input influence |
| **Output CRF** | `18` | High quality encoding |
| **CPU Offload** | `model` | Save VRAM |

---

## Performance Presets

### ⚡ Fast Testing (3-5 min per 100 frames)

```
Inference Steps:     5
Decode Chunk Size:   4
Frames Chunk:        8
Tile Number:         1
Frame Overlap:       3
```

**Use for:** Quick iterations, testing masks, preview results

---

### ⚖️ Balanced (5-8 min per 100 frames) ⭐ RECOMMENDED

```
Inference Steps:     6
Decode Chunk Size:   6
Frames Chunk:        14
Tile Number:         1
Frame Overlap:       3
```

**Use for:** Final renders, good quality/speed balance

---

### 🎨 Maximum Quality (10-15 min per 100 frames)

```
Inference Steps:     10
Decode Chunk Size:   6
Frames Chunk:        12
Tile Number:         1
Frame Overlap:       5
```

**Use for:** Critical scenes, best possible quality

---

## VRAM Usage by Settings

| Resolution | Frames Chunk | Decode Chunk | Est. VRAM | Safe for RTX 3060? |
|------------|-------------|--------------|-----------|-------------------|
| 854×480 | 8 | 4 | ~6 GB | ✅ Very Safe |
| 854×480 | 14 | 6 | ~8 GB | ✅ Safe |
| 854×480 | 23 | 8 | ~11 GB | ⚠️ Risky |
| 1920×1080 | 8 | 4 | ~10 GB | ⚠️ Borderline |
| 1920×1080 | 12 | 6 | ~12 GB | ❌ OOM Likely |

---

## Troubleshooting

### If You Get OOM (Out of Memory) Errors

**Reduce settings in this order:**

1. **Frames Chunk**: `14 → 12 → 8`
   - Biggest VRAM savings
   - Linear speed reduction

2. **Decode Chunk Size**: `6 → 4 → 2`
   - Moderate VRAM savings
   - Slower decoding

3. **Tile Number**: `1 → 2`
   - Adds processing overhead
   - Saves VRAM by processing in tiles

4. **Resolution**: Consider `640×360` for very long videos

---

### If You Have VRAM Headroom

**Increase settings in this order:**

1. **Decode Chunk Size**: `6 → 8 → 10`
   - Biggest speed improvement
   - Linear VRAM increase

2. **Frames Chunk**: `14 → 18 → 23`
   - Better batch efficiency
   - Moderate VRAM increase

3. **Inference Steps**: `6 → 8 → 10`
   - Quality improvement only
   - Linear time increase

---

## Setting Explanations

### Inference Steps
**Range:** 1-50  
**Default:** 6

Number of denoising iterations. Higher = better quality but slower.
- **5**: Minimum viable, fast testing
- **6-8**: Sweet spot for quality/speed
- **10+**: Maximum quality, diminishing returns

### Decode Chunk Size
**Range:** 1-23  
**Default:** 6 (RTX 3060)

Frames decoded simultaneously by VAE.
- **2-4**: Conservative, safe for any GPU
- **6-8**: Balanced for 12GB cards
- **10+**: Aggressive, requires 16GB+

### Tile Number
**Range:** 1-10  
**Default:** 1

Spatial tiling (1 = disabled, 2 = 2×2 grid, etc.)
- **1**: Best for 480p/720p (no overhead)
- **2**: Use for 1080p on 12GB cards
- **4+**: Only for 4K or very low VRAM

### Frames Chunk
**Range:** 1-50  
**Default:** 14 (RTX 3060 @ 480p)

Frames processed in each batch.
- **8-12**: Conservative, long videos
- **14-18**: Balanced, most scenarios
- **20+**: Short videos, high VRAM

### Frame Overlap
**Range:** 0-20  
**Default:** 3

Frames that overlap between chunks for temporal blending.
- **0-2**: Fast, potential flicker
- **3-5**: Smooth, recommended
- **6+**: Very smooth, diminishing returns

### Original Input Blend
**Range:** 0.0-1.0  
**Default:** 0.0

How much original warped input influences output.
- **0.0**: Pure inpainted result
- **0.2-0.3**: Subtle consistency boost
- **0.5+**: Heavy original influence

---

## Monitoring VRAM

### Using nvidia-smi

```bash
# Watch VRAM in real-time (updates every 1 second)
nvidia-smi -l 1

# Or in a separate terminal
watch -n 1 nvidia-smi
```

### Healthy Pattern

```
Idle:           1-2 GB allocated
Loading model:  4-6 GB allocated
Processing:     7-9 GB allocated (peaks)
Between chunks: 6-7 GB allocated
Finished:       4-6 GB allocated
```

### Warning Signs

```
❌ Processing exceeds 11 GB → Reduce settings
❌ Consistent 11.5GB+ → Risk of OOM
❌ Spikes to 12GB → Will likely crash
```

---

## File Locations

### Preset Config
```
E:\WEBUI-StereoCrafter\config_inpainting_rtx3060_480p.json
```

### Auto-Saved Settings
```
E:\WEBUI-StereoCrafter\config_inpainting.json
```

### Sidecar Files (per video)
```
<output_folder>/<video_name>_sidecar.json
```

---

## Tips for Best Results

1. **Start with Balanced preset** - adjust based on results
2. **Monitor first 100 frames** - check VRAM stability
3. **Use Frame Overlap = 3** - prevents temporal flicker
4. **Keep Tile Number = 1** for 480p - no benefit from tiling
5. **Test with short clips** before processing full videos
6. **Save sidecar files** - preserves settings for re-renders

---

## Comparison with Other GPUs

| GPU | VRAM | Frames Chunk | Decode Chunk | Relative Speed |
|-----|------|-------------|--------------|----------------|
| RTX 3060 | 12GB | 14 | 6 | 1.0x (baseline) |
| RTX 4070 | 12GB | 16 | 8 | 1.3x faster |
| RTX 4080 | 16GB | 20 | 10 | 1.8x faster |
| RTX 4090 | 24GB | 23 | 12 | 2.5x faster |
| RTX 6000 Ada | 48GB | 35 | 16 | 3.5x faster |

---

## Support

If you continue experiencing issues:

1. **Share your log output** showing:
   - GPU model and total VRAM
   - Allocated/Free VRAM at start
   - Video specs (frames, resolution)
   - Error messages

2. **Try most conservative settings**:
   ```
   Frames Chunk: 8
   Decode Chunk: 2
   Tile Number: 2
   ```

3. **Consider cloud GPU** (Runpod, Vast.ai) for very long videos

---

**Last Updated:** 2026-03-11  
**Version:** 1.0  
**Tested On:** RTX 3060 12GB, 854×480 video
