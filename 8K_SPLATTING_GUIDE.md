# 8K Splatting Output Guide

**Date:** 2026-03-18  
**Topic:** 4-Panel Tiling at 4K Input Resolution

---

## Output Dimensions

For **4K input (3840×2160)** with 4-panel splatting:

```
┌─────────────────────┬─────────────────────┐
│   Original Video    │   Depth Map (vis)   │
│   3840 × 2160       │   3840 × 2160       │
├─────────────────────┼─────────────────────┤
│  Occlusion Mask     │   Final Warped      │
│  3840 × 2160        │   3840 × 2160       │
└─────────────────────┴─────────────────────┘

Output Resolution: 7680 × 4320 (8K UHD)
Total Pixels: 33.2 megapixels per frame
```

---

## Can FFmpeg Handle 8K?

### ✅ **Yes, with the right codec:**

| Codec | 8K Support | Speed (RTX 6000 Ada) | File Size (per hour) | Quality |
|-------|------------|----------------------|----------------------|---------|
| **libx264** (CPU) | ✅ Yes | ~1-3 fps ❌ | 50-100 GB | Excellent |
| **h264_nvenc** (GPU) | ⚠️ Limited | ~30-60 fps ✅ | 30-60 GB | Good |
| **libx265** (CPU) | ✅ Yes | ~0.5-2 fps ❌ | 25-50 GB | Excellent |
| **hevc_nvenc** (GPU) | ✅ **Best** | ~15-30 fps ✅ | 20-40 GB | **Best** |

---

## RTX 6000 Ada NVENC Capabilities

Your **RTX 6000 Ada** (8th Gen NVENC):

```
┌─────────────────────────────────────────────────────────┐
│  Encoder Specifications:                                │
│  - Max Encode Resolution: 8192×8192                    │
│  - 8K@30fps: ✅ Full support                            │
│  - 8K@60fps: ⚠️ May be limited (depends on codec)      │
│  - H.264 8K: ⚠️ Some limitations                        │
│  - HEVC 8K: ✅ Full support                             │
│  - AV1 8K: ✅ Supported (FFmpeg ≥ 6.0)                 │
└─────────────────────────────────────────────────────────┘
```

---

## Current Code Analysis

### Codec Selection Logic

The code in `stereocrafter_util.py` selects codec based on:

```python
if is_hdr_source:
    output_codec = "libx265"
    if CUDA_AVAILABLE:
        output_codec = "hevc_nvenc"  # ✅ Best for 8K
elif original_codec_name == "hevc" and is_original_10bit_or_higher:
    output_codec = "libx265"
    if CUDA_AVAILABLE:
        output_codec = "hevc_nvenc"  # ✅ Best for 8K
else:
    output_codec = "libx264"
    if CUDA_AVAILABLE:
        output_codec = "h264_nvenc"  # ⚠️ May struggle at 8K
```

### Issue: Default is H.264 for SDR Content

For standard 4K videos (SDR, 8-bit), the code uses **`h264_nvenc`**, which:
- ✅ Works at 8K resolution
- ⚠️ **Larger file sizes** than HEVC
- ⚠️ **Less efficient** compression at 8K

---

## Recommended Settings for 8K Splatting

### Option 1: Force HEVC for 8K Output (Recommended)

**Modify:** `stereocrafter_util.py` Line 2048

**Add:**
```python
# Force HEVC for 8K output (better compression and NVENC support)
if content_width >= 7680 and content_height >= 4320:
    output_codec = "hevc_nvenc" if CUDA_AVAILABLE else "libx265"
    output_pix_fmt = "yuv420p10le"
    output_profile = "main10"
    logger.info(f"8K output detected: Using HEVC for better compression")
else:
    output_codec = "libx264"
    if CUDA_AVAILABLE:
        output_codec = "h264_nvenc"
```

**Benefits:**
- 40-50% smaller file sizes
- Better quality at same bitrate
- NVENC optimized for HEVC 8K

---

### Option 2: Add User Setting for 8K Codec

**Add to UI:** `splatting_ui.py`

```python
self.output_codec_var = gr.Dropdown(
    ["auto", "h264_nvenc", "hevc_nvenc", "libx264", "libx265"],
    value="auto",
    label="Output Codec",
    info="Auto: H.264 for <4K, HEVC for 8K. HEVC recommended for 8K output."
)
```

---

## Expected Performance (RTX 6000 Ada)

### 4K Input → 8K Output (7680×4320)

| Codec | FPS | Time (43 frames) | File Size |
|-------|-----|------------------|-----------|
| **hevc_nvenc** | 20-30 fps | ~2 seconds | ~500 MB |
| **h264_nvenc** | 30-50 fps | ~1 second | ~800 MB |
| **libx265** (CPU) | 1-2 fps | ~30 seconds | ~400 MB |
| **libx264** (CPU) | 2-4 fps | ~15 seconds | ~700 MB |

**Recommendation:** Use **`hevc_nvenc`** for best balance of speed and quality.

---

## FFmpeg Command Examples

### Current (H.264 NVENC)
```bash
ffmpeg -f rawvideo -vcodec rawvideo -s 7680x4320 -pix_fmt bgr48le -r 30 -i - \
  -c:v h264_nvenc -preset medium -qp 23 -pix_fmt yuv420p \
  output_8k.mp4
```

### Recommended (HEVC NVENC)
```bash
ffmpeg -f rawvideo -vcodec rawvideo -s 7680x4320 -pix_fmt bgr48le -r 30 -i - \
  -c:v hevc_nvenc -preset medium -qp 23 -pix_fmt yuv420p10le -profile:v main10 \
  output_8k.mp4
```

**Benefits of HEVC:**
- Same quality at ~50% bitrate
- Better 8K encoder support
- 10-bit output (smoother gradients)

---

## Potential Issues at 8K

### Issue 1: FFmpeg Version Requirements

**Minimum FFmpeg Version:** 4.4+

```bash
ffmpeg -version
# Should show version ≥ 4.4 for best 8K support
```

**Check NVENC 8K support:**
```bash
ffmpeg -h encoder=hevc_nvenc | grep -i "max.*width\|max.*height"
# Should show: max_width: 8192, max_height: 8192
```

---

### Issue 2: Memory Requirements

**8K Encoding Memory:**

| Component | RAM Required |
|-----------|--------------|
| Input Buffer (16-bit) | ~256 MB per frame |
| NVENC Encoder | ~2-4 GB VRAM |
| Output Buffer | ~128 MB |
| **Total** | **~3-5 GB** |

Your **RTX 6000 Ada (48GB)** has plenty of VRAM ✅

---

### Issue 3: Playback Compatibility

**8K Video Playback:**

| Player | 8K Support |
|--------|------------|
| VLC 3.0+ | ✅ Yes (hardware accelerated) |
| MPC-HC + madVR | ✅ Yes |
| Windows Media Player | ❌ No |
| QuickTime | ❌ No |
| YouTube (upload) | ✅ Yes (processes to VP9) |

**Recommendation:** Use **VLC 3.0+** or **MPC-HC** for 8K playback testing.

---

### Issue 4: Disk Space

**8K File Sizes (per minute):**

| Codec | CRF/QP | Size/minute | Size/hour |
|-------|--------|-------------|-----------|
| h264_nvenc | 23 | ~800 MB | ~48 GB |
| hevc_nvenc | 23 | ~500 MB | ~30 GB |
| libx264 | 18 | ~1.2 GB | ~72 GB |
| libx265 | 24 | ~600 MB | ~36 GB |

**For 43 frames @ 30fps (1.4 seconds):**
- h264_nvenc: ~18 MB
- hevc_nvenc: ~12 MB

---

## Testing 8K Encoding

### Test Command (Manual FFmpeg)

```bash
# Generate test 8K video
ffmpeg -f lavfi -i testsrc2=size=7680x4320:rate=30 -frames 100 \
  -c:v hevc_nvenc -qp 23 -pix_fmt yuv420p10le \
  test_8k.mp4

# Check if successful
ffprobe test_8k.mp4
```

### Test in Splatter UI

1. Use a **short 4K video** (5-10 seconds)
2. Enable **4-panel output** (dual_output = False)
3. Check logs for:
   ```
   FFmpeg pipe started: 7680x4320 @ 30 fps
   Using codec: hevc_nvenc (or h264_nvenc)
   ```
4. Verify output file plays correctly

---

## Recommended Settings Summary

### For 4K Input → 8K Output

```
┌─────────────────────────────────────────────────────────┐
│  Video Settings:                                        │
│  - Target Width: 3840                                   │
│  - Target Height: 2160                                  │
│  - Dual Output (4-panel): False (unchecked)            │
│                                                         │
│  Output Grid: 7680×4320 (8K)                           │
│                                                         │
│  Codec: hevc_nvenc (recommended) or h264_nvenc         │
│  - CRF/QP: 23 (balanced)                               │
│  - Preset: medium (or slow for better quality)         │
│  - Pixel Format: yuv420p10le (10-bit)                  │
│                                                         │
│  Expected Performance (RTX 6000 Ada):                  │
│  - Encode Speed: 20-30 fps                             │
│  - File Size: ~500 MB per minute                       │
└─────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

### Error: "Invalid dimensions" or "Codec not supported"

**Symptom:**
```
FFmpeg encoding FAILED
Return code: 1
Error: [hevc_nvenc @ 0x...] Invalid dimensions
```

**Solution:**
- Ensure dimensions are **even numbers** (7680×4320 ✅)
- Update FFmpeg to latest version
- Check NVENC 8K support: `ffmpeg -h encoder=hevc_nvenc`

---

### Error: "Out of memory" or "CUDA out of memory"

**Symptom:**
```
torch.cuda.OutOfMemoryError: CUDA out of memory
```

**Solution:**
- Reduce batch size in splatting settings
- Close other GPU applications
- Use `hevc_nvenc` (more efficient than `h264_nvenc` at 8K)

---

### Error: "No output file created"

**Symptom:**
```
FFmpeg encoding FAILED
Deleted incomplete temp file: video.mp4.tmp
```

**Solution:**
- Check FFmpeg error output in logs
- Verify NVENC encoder is available: `ffmpeg -encoders | grep nvenc`
- Try CPU encoding as fallback: `libx265`

---

## Summary

| Question | Answer |
|----------|--------|
| **Can FFmpeg handle 8K?** | ✅ Yes, with proper codec |
| **Best codec for 8K?** | `hevc_nvenc` (HEVC on GPU) |
| **RTX 6000 Ada support?** | ✅ Full 8K@30fps support |
| **File size?** | ~500 MB/minute (HEVC) |
| **Encoding speed?** | 20-30 fps (RTX 6000 Ada) |
| **Playback?** | VLC 3.0+, MPC-HC |
| **Recommended settings?** | HEVC, QP 23, 10-bit |

---

## Code Changes Needed

**Optional but recommended:** Force HEVC for 8K output in `stereocrafter_util.py`:

```python
# Line 2048: Add 8K detection
if content_width >= 7680 and content_height >= 4320:
    output_codec = "hevc_nvenc" if CUDA_AVAILABLE else "libx265"
    output_pix_fmt = "yuv420p10le"
    logger.info(f"8K output detected: Using HEVC for better compression")
```

This ensures optimal codec selection for 8K splatting output.
