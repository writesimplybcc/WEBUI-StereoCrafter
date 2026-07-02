# StereoCrafter WEBUI - Complete User Guide

This guide covers the complete pipeline: **Depth Map → Splatting → Inpainting → Merging**, with optimized settings for different resolutions and video lengths.

---

## Quick Navigation

1. [Step 1: Depth Map Generation](#step-1-depth-map-generation)
2. [Step 2: Splatting (View Synthesis)](#step-2-splatting-view-synthesis)
3. [Step 3: Inpainting](#step-3-inpainting)
4. [Step 4: Merging](#step-4-merging)
5. [Optimized Settings Reference](#optimized-settings-reference)

---

## Prerequisites

### Hardware Requirements

| GPU Tier | Max Resolution | Video Length | Examples |
|----------|---------------|--------------|----------|
| **Entry (8-12 GB)** | 1080p | 1-3 min (127 frames) | RTX 3060 12GB, RTX 4060 |
| **Mid (24 GB)** | 1440p | 3-5 min | RTX 3090, RTX 4090 |
| **High (48 GB)** | 4K+ | 5-10 min | RTX 6000 Ada, A6000 |

### File Naming Convention (Important!)

The pipeline relies on specific naming patterns to match files across steps:

```
{VideoName}_{Resolution}_{Step}.mp4

Example: MyClip_3840_splatted4.mp4
```

### Folder Structure

```
WEBUI-StereoCrafter/
├── input_source_clips/          # Raw source videos
├── output_depthmaps/            # Step 1 output
│   ├── hires/                   # Hi-res depth maps (if applicable)
│   └── lowres/                  # Low-res depth maps
├── output_splatted/             # Step 2 output
│   ├── hires/                   # Hi-res splatted (4-panel)
│   └── lowres/                  # Low-res splatted (4-panel)
├── output_inpainted/            # Step 3 output (inpainted)
├── final_videos/                # Step 4 output (merged)
└── input_source_clips/
    └── finished/                # Originals (scanned for Hi-Res blending)
```

---

## Step 1: Depth Map Generation

### What It Does
Generates a per-frame depth map using the **DepthCrafter** AI model. This creates a grayscale representation of scene geometry that drives all subsequent steps.

### Launch
```bash
# Tkinter Desktop App (Default)
python depthcrafter_gui_seg.py

# Web UI (Gradio)
python webui.py  →  DepthCrafter tab
```

### Workflow
1. Select **Input Folder** (your raw video files)
2. Select **Output Folder** (defaults to `./output_depthmaps`)
3. Adjust settings (see below)
4. Click **Generate Depth Maps**

### Output Files
- `MyClip_1920_depth.mp4` — Depth map video
- `MyClip_1920_depth_meta.json` — Metadata sidecar

---

### Optimized Settings

#### 1080p (1920×1080)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Batch Size** | `10-15` | Default for 24GB+ GPUs |
| **Window Size** | `80-130` | Temporal context window |
| **Overlap** | `6` | Frames between batches |
| **Num Inference Steps** | `5` | Higher = better quality, slower |
| **Decode Chunk Size** | `14` | Frames decoded at once |
| **Processing Chunk Size** | `80-130` | Frames processed per batch |
| **Output Width** | `1920` | Match source |
| **Output Height** | `1080` | Match source |

**Expected:** ~15-30 fps on RTX 4090

#### 4K (3840×2160)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Batch Size** | `6-10` | Reduced for VRAM safety |
| **Window Size** | `70-100` | Reduced temporal context |
| **Overlap** | `6` | Keep as-is |
| **Num Inference Steps** | `5` | Keep as-is |
| **Decode Chunk Size** | `10-14` | Reduce to 10 if OOM |
| **Processing Chunk Size** | `50-80` | Reduce to 50 if OOM |
| **Output Width** | `3840` | Match source |
| **Output Height** | `2160` | Match source |

**Expected:** ~5-10 fps on RTX 6000 Ada

#### 8K (7680×4320) — Experimental

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Batch Size** | `3-5` | Very conservative |
| **Window Size** | `50-70` | Minimal temporal context |
| **Overlap** | `6` | Keep as-is |
| **Num Inference Steps** | `5` | Keep as-is |
| **Decode Chunk Size** | `6-8` | Very conservative |
| **Processing Chunk Size** | `30-50` | Small batches |

**Expected:** ~1-3 fps on RTX 6000 Ada

---

## Step 2: Splatting (View Synthesis)

### What It Does
Uses the depth map to warp the original video into a **stereo 4-panel layout**:
- **Top-Left:** Original source frame
- **Top-Right:** Depth map visualization
- **Bottom-Left:** Occlusion mask
- **Bottom-Right:** Warped right-eye view

### Launch
```bash
# Tkinter Desktop App
python splatting_gui.py

# Web UI (Gradio)
python webui.py  →  Splatting tab
```

### Workflow
1. Select **Source Video** (original)
2. Select **Depth Map Video** (output from Step 1)
3. Select **Output Folder** (defaults to `./output_splatted`)
4. Adjust settings (see below)
5. Click **Start Splatting**

### Output Files
- `MyClip_1920_splatted4.mp4` — 4-panel stereo output
- `MyClip_1920_splatted2.mp4` — 2-panel (dual) output (if enabled)

---

### Optimized Settings

#### 1080p (1920×1080)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Blur X/Y** | `17` | Softens depth boundaries |
| **Dilate X/Y** | `10` | Expands occlusion masks |
| **Disparity** | `20` | Stereo separation strength (1%) |
| **Convergence** | `0.6` | Eye convergence point |
| **Output CRF** | `23` | Quality (lower = better, 18-28 range) |
| **Dual Output** | ☐ Unchecked | Use 4-panel (splatted4) |
| **Color Tags Mode** | `auto` | Metadata tagging |
| **Skip Low-Res Preproc** | ☐ Unchecked | Full processing pipeline |

**Output Resolution:** 3840×2160 (4-panel from 1080p source)
**Expected:** ~30-60 fps on RTX 4090

#### 4K (3840×2160)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Blur X/Y** | `37` | Highly softened for 4K boundaries |
| **Dilate X/Y** | `22` | Significantly expanded for 4K |
| **Disparity** | `20` | Keep at 1% for natural viewing |
| **Convergence** | `0.6` | Keep as-is |
| **Output CRF** | `23` | Quality (lower = better) |
| **Dual Output** | ☐ Unchecked | 4-panel = 7680×4320 |
| **Batch Size** | `10` | Frames per GPU batch |
| **Color Tags Mode** | `auto` | Metadata tagging |

**Output Resolution:** 7680×4320 (4-panel from 4K source)
**Expected:** ~10-20 fps on RTX 6000 Ada

#### 720p (1280×720)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Blur X/Y** | `16` | Standard softening |
| **Dilate X/Y** | `9` | Standard expansion |
| **Disparity** | `20` | Stereo separation strength (1%) |
| **Convergence** | `0.6` | Keep as-is |
| **Output CRF** | `23` | Quality (lower = better) |
| **Dual Output** | ☐ Unchecked | Use 4-panel |
| **Batch Size** | `15` | Higher batch size for speed |
| **Color Tags Mode** | `auto` | Metadata tagging |

**Output Resolution:** 2560×1440 (4-panel from 720p source)
**Expected:** ~60+ fps on most modern GPUs

---

## Step 3: Inpainting

### What It Does
Fills occlusion holes in the warped right-eye view using a diffusion model. This is the **most VRAM-intensive** step.

### Launch
```bash
# Tkinter Desktop App
python inpainting_gui.py

# Web UI (Gradio)
python webui.py  →  Inpainting tab
```

### Workflow
1. Select **Input Folder** (`./output_splatted/lowres` or `./output_splatted/hires`)
2. Select **Output Folder** (defaults to `./output_inpainted`)
3. Select **Hi-Res Blend Folder** (optional, for upscaling)
4. Adjust settings (see below)
5. Click **Start Processing**

### Output Files
- `MyClip_1920_inpainted_right_eye.mp4` — Inpainted stereo video

---

### Optimized Settings

#### 1080p (1920×1080)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Tile Number** | `2` | Spatial tiling grid |
| **Frames Chunk** | `15-23` | Frames per batch |
| **Overlap** | `3` | Must be < Frames Chunk |
| **Num Inference Steps** | `5` | Quality vs speed |
| **Decode Chunk Size** | `2` | VAE decode batch size |
| **Offload Type** | `model` | CPU offloading mode |
| **Enable Color Transfer** | ☑ Checked | Color consistency |
| **Enable Post-Inpainting Blend** | ☐ Unchecked | Optional refinement |
| **Mask Initial Threshold** | `0.3` | Occlusion detection |
| **Mask Dilate Kernel** | `5` | Expand mask boundaries |
| **Mask Blur Kernel** | `10` | Smooth mask edges |

**Expected VRAM Usage:** ~12-18 GB
**Expected Speed:** ~30-60 fps on RTX 4090

#### 4K (3840×2160)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Tile Number** | `4` | Critical! Reduces per-tile VRAM |
| **Frames Chunk** | `5-10` | Must be > Overlap |
| **Overlap** | `3` | Auto-corrected if ≥ Frames Chunk |
| **Num Inference Steps** | `5` | Keep as-is |
| **Decode Chunk Size** | Any | **Auto-clamped to 1 at 4K** |
| **Offload Type** | `model` | Use `sequential` if still OOM |
| **Enable Color Transfer** | ☑ Checked | Critical for 4K quality |
| **Enable Post-Inpainting Blend** | ☐ Unchecked | Optional |
| **Mask Initial Threshold** | `0.3` | Keep as-is |
| **Mask Dilate Kernel** | `5` | Keep as-is |
| **Mask Blur Kernel** | `10` | Keep as-is |

**Expected VRAM Usage:** ~25-32 GB
**Expected Speed:** ~10-20 fps on RTX 6000 Ada

#### 8K (7680×4320) — Experimental

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Tile Number** | `6` | Maximum tiling for VRAM |
| **Frames Chunk** | `3-5` | Very small batches |
| **Overlap** | `3` | Keep as-is |
| **Num Inference Steps** | `5` | Keep as-is |
| **Decode Chunk Size** | Any | **Auto-clamped to 1** |
| **Offload Type** | `sequential` | Required for VRAM safety |
| **Enable Color Transfer** | ☑ Checked | Critical |

**Expected VRAM Usage:** ~35-42 GB
**Expected Speed:** ~3-7 fps on RTX 6000 Ada

---

## Step 4: Merging

### What It Does
Takes the inpainted right-eye view and combines it with the original left-eye view to create the final **Side-by-Side (SBS)** stereo video. Also supports anaglyph (red-cyan) output.

### Launch
```bash
# Tkinter Desktop App
python merging_gui.py

# Web UI (Gradio)
python webui.py  →  Merging tab
```

### Workflow
1. Select **Left Eye Video** (original source or splatted left panel)
2. Select **Right Eye Video** (inpainted output from Step 3)
3. Select **Output Folder** (defaults to `./final_videos`)
4. Choose output mode (SBS or Anaglyph)
5. Click **Start Merging**

### Output Files
- `MyClip_1920_merged.mp4` — Side-by-Side stereo video
- `MyClip_1920_merged_anaglyph.mp4` — Red-Cyan anaglyph (if enabled)

---

### Optimized Settings

#### 1080p (1920×1080)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Output Width** | `3840` | 2×1080 = SBS 1080p per eye |
| **Output Height** | `1080` | Match source |
| **Output CRF** | `23` | Quality (lower = better) |
| **Output Mode** | `SBS` | Side-by-Side |
| **Anaglyph Output** | ☐ Unchecked | Enable if needed |
| **Padding** | `0` | No extra borders |

**Expected Speed:** ~30-60 fps (FFmpeg encode)

#### 4K (3840×2160)

| Parameter | Setting | Notes |
|-----------|---------|-------|
| **Output Width** | `7680` | 2×3840 = SBS 4K per eye |
| **Output Height** | `2160` | Match source |
| **Output CRF** | `23` | Quality (lower = better) |
| **Output Mode** | `SBS` | Side-by-Side |
| **Anaglyph Output** | ☐ Unchecked | Enable if needed |
| **Padding** | `0` | No extra borders |

**Expected Speed:** ~10-30 fps on RTX 6000 Ada

---

## Optimized Settings Reference

### Quick Settings Table

| Resolution | GPU Tier | DepthCrafter | Splatting | Inpainting | Merging |
|-----------|----------|--------------|-----------|------------|---------|
| **720p** | 8-12GB| Batch 15, Window 100| Dilate 9, Blur 16, Disp 20 | Tiles 1, Chunk 20 | 2560×720 |
| **1080p** | 12GB | Batch 10, Window 80 | Dilate 10, Blur 17, Disp 20 | Tiles 2, Chunk 15 | 3840×1080 |
| **1080p** | 24GB | Batch 15, Window 130 | Dilate 10, Blur 17, Disp 20 | Tiles 2, Chunk 23 | 3840×1080 |
| **1440p** | 24GB | Batch 10, Window 100 | Dilate 10, Blur 17, Disp 20 | Tiles 2, Chunk 15 | 5120×1440 |
| **4K** | 48GB | Batch 8, Window 80 | Dilate 22, Blur 37, Disp 20 | Tiles 4, Chunk 8 | 7680×2160 |
| **4K** | 24GB | Batch 5, Window 60 | Dilate 22, Blur 37, Disp 20 | Tiles 4, Chunk 3 | 7680×2160 |

### Video Length Optimization (Max Clip Lengths)

Memory fragmentation in PyTorch builds up over time. Even though the system processes video in small chunks, **you must split long videos into smaller clips** to prevent Out-of-Memory (OOM) crashes, especially at 4K.

#### 1080p Limits (Any GPU)
* **DepthCrafter:** ~3 minutes (4320 frames)
* **Splatting:** ~5 to 10 minutes
* **Inpainting:** ~1 to 3 minutes
* **Merging:** Infinite

#### 4K Limits (24GB VRAM)
When moving from 1080p to 4K, the PyTorch tensors are 4x larger. Your 24GB VRAM will fill up and choke much faster.
* **DepthCrafter:** ~1 to 2 minutes (1440 - 2880 frames)
* **Splatting:** ~3 to 5 minutes (4320 - 7200 frames)
* **Inpainting (The Bottleneck):** **~30 to 60 seconds (720 - 1440 frames)**
* **Merging:** Infinite

> [!WARNING]
> **The Golden Rule for 4K / 24GB:** Your entire workflow is bottlenecked by the Inpainting step. You **must** chop your 4K video into 30-second to 1-minute clips maximum. Run all the clips through the pipeline as a batch, and stitch the final 3D outputs back together at the very end.
---

## Troubleshooting

### OOM (Out of Memory) Errors

**Inpainting is the most common culprit.** Fix in this order:
1. Increase **Tile Number** (2 → 4 → 6)
2. Reduce **Frames Chunk** (23 → 10 → 5 → 3)
3. Change **Offload Type** to `sequential`
4. Reduce **Decode Chunk Size** to 1

### "No capable devices found" (FFmpeg/NVENC)

The code automatically falls back to CPU encoding (`libx264` or `libx265`). It will be slower but will complete the job. To fix permanently, rebuild your Docker image with NVENC support (see `NVENC_DOCKER_SETUP.md`).

### "start (0) + length (X) exceeds dimension size (1)"

This means `Frames Chunk` ≤ `Overlap`. The code auto-corrects this by reducing overlap to `Frames Chunk - 1`. Ensure **Frames Chunk > Overlap**.

### "FFmpeg pipe broken"

FFmpeg crashed during encoding. Common causes:
- Odd resolution dimensions (must be even numbers)
- NVENC not available (auto-fallback to CPU)
- GPU ran out of VRAM during encode

Check the log for the actual FFmpeg error message.

---

## Full Pipeline Example (1080p, 1-minute video)

```
Step 1: Depth Map (15 min on RTX 4090)
  Input:  input_source_clips/MyClip_1080.mp4
  Output: output_depthmaps/lowres/MyClip_1080_depth.mp4

Step 2: Splatting (2 min on RTX 4090)
  Input:  input_source_clips/MyClip_1080.mp4
          output_depthmaps/lowres/MyClip_1080_depth.mp4
  Output: output_splatted/lowres/MyClip_1080_splatted4.mp4

Step 3: Inpainting (5 min on RTX 4090)
  Input:  output_splatted/lowres/MyClip_1080_splatted4.mp4
  Output: output_inpainted/MyClip_1080_inpainted_right_eye.mp4

Step 4: Merging (1 min on RTX 4090)
  Input:  output_splatted/lowres/MyClip_1080_splatted4.mp4 (left eye)
          output_inpainted/MyClip_1080_inpainted_right_eye.mp4 (right eye)
  Output: final_videos/MyClip_1080_merged.mp4

Total Time: ~23 minutes
```

---

## Full Pipeline Example (4K, 1-minute video, RTX 6000 Ada)

```
Step 1: Depth Map (20 min)
  Input:  input_source_clips/MyClip_4K.mp4
  Output: output_depthmaps/lowres/MyClip_4K_depth.mp4

Step 2: Splatting (5 min)
  Input:  input_source_clips/MyClip_4K.mp4
          output_depthmaps/lowres/MyClip_4K_depth.mp4
  Output: output_splatted/lowres/MyClip_4K_splatted4.mp4

Step 3: Inpainting (10 min)
  Input:  output_splatted/lowres/MyClip_4K_splatted4.mp4
  Settings: Tiles 4, Chunk 8, Overlap 3
  Output: output_inpainted/MyClip_4K_inpainted_right_eye.mp4

Step 4: Merging (2 min)
  Input:  output_splatted/lowres/MyClip_4K_splatted4.mp4 (left eye)
          output_inpainted/MyClip_4K_inpainted_right_eye.mp4 (right eye)
  Output: final_videos/MyClip_4K_merged.mp4

Total Time: ~37 minutes
```

---

## Advanced VRAM & Performance Guide

### GPU VRAM Tiers & Auto-Detection
The system dynamically checks your GPU's available memory and adjusts settings automatically.

**How It Works:**
1. Checks total VRAM capacity and currently allocated memory.
2. Calculates free VRAM with a 20% safety margin.
3. Selects the appropriate tier based on effective VRAM.

**Settings by Tier (DepthCrafter):**
| Effective VRAM | decode_chunk | window_size | overlap | Typical Use Case |
|----------------|--------------|-------------|---------|------------------|
| **< 8GB**      | 2            | 50          | 8       | Very low memory / heavy GPU load |
| **8-12GB**     | 3            | 60          | 10      | Low memory / moderate GPU load |
| **12-24GB**    | 6            | 80          | 15      | RTX 3090, RTX 4080, or busy 48GB GPU |
| **24-48GB**    | 10           | 110         | 25      | RTX 4090, A5000 |
| **48GB+**      | 8            | 110         | 25      | RTX 6000 Ada (mostly idle) |

**Performance vs Memory Trade-offs:**
*   **decode_chunk_size (High Memory Impact):** Reduce first if OOM.
*   **window_size (Very High Memory Impact):** Reduce if still OOM.
*   **overlap (Medium Memory Impact):** Affects quality, reduce carefully.
*   **resolution (Very High Memory Impact):** Last resort, affects output quality.

### Hardware Presets Reference

**RTX 3060 12GB (Low VRAM)**
*   **DepthCrafter:** CPU Offload: "model", Max Res: 1024x1024.
*   **Splatting:** CPU Offload: "model". Enable downscaling.
*   **Inpainting:** Max Res: 1024x1024. Guidance Scale: 7.5-12.5.
*   **Merging:** Unlimited (CPU-bound).

**RTX 5090 32GB (High CUDA Mid VRAM)**
*   **DepthCrafter:** CPU Offload: "none", Max Res: 1024x1024-1536x1536.
*   **Splatting:** 8K hires / 4K lowres.
*   **Inpainting:** Resolution up to 7680x2160.
*   **Merging:** Enable dithering and gamma.

**RTX 6000 Ada 48GB (Mid VRAM Workstation)**
*   **DepthCrafter:** CPU Offload: "none", Max Res: 1536x1536-2048x2048.
*   **Splatting:** 8K hires / 4K lowres.
*   **Inpainting:** Resolution up to 7680x2160.
*   **Merging:** Enable percentile normalization.

**RTX 6000 Pro 96GB (High CUDA High VRAM)**
*   **DepthCrafter:** CPU Offload: "none", Max Res: 2048x2048-4096x4096.
*   **Splatting:** Up to 8192x4608+.
*   **Inpainting:** Up to 8192x4320+.
*   **Merging:** All quality options enabled.

---

## 4K Processing Segment Guidelines (RTX 6000 Ada)

When processing 4K videos, you must use **Decode Chunk Size = 2**. Depending on the length of your 4K video, use the following segmenting strategies to prevent memory leaks:

*   **Short (1-100 frames):** Full Video Mode. Window 30, Overlap 5.
*   **Medium (101-300 frames):** Full Video Mode. Window 25, Overlap 8.
*   **Long (301-500 frames):** Process as Segments. Window 20, Overlap 10. Switch CPU Offload to `sequential`.
*   **Very Long (501+ frames):** Process as Segments. Window 20, Overlap 10. Keep intermediate NPZ files for recovery.

**OOM Error During VAE Encoding:**
*   Reduce `decode_chunk_size` to 2.
*   Reduce `window_size` to 20-25.
*   Change CPU Offload to `sequential`.
*   Downscale resolution to 1440p or 1080p.

**Processing Slowdown Over Time:**
*   This is caused by memory fragmentation. Use `sequential` CPU offload, reduce the segment window size, and process in smaller batches.
