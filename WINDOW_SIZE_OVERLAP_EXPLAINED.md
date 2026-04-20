# Window Size & Overlap in DepthCrafter

## Quick Answer

| Parameter | What It Does | Typical Values | Impact |
|-----------|-------------|----------------|--------|
| **Window Size** | Number of frames processed together | 60-140 frames | ↑ Quality & VRAM |
| **Overlap** | Frames shared between windows | 10-30 frames | ↑ Smoothness & VRAM |

---

## What is Window Size?

### Definition
**Window Size** determines how many consecutive frames the model processes **together as a single batch**.

### How It Works

```
Video Timeline (126 frames total)
├─────────────────────────────────────────┤

Window Size = 110
┌─────────────────────────────────────┐
│  Frames 0-109 processed together    │
└─────────────────────────────────────┘
                                      ┌─────────────────────────────────────┐
                                      │  Frames 85-125 processed together   │
                                      └─────────────────────────────────────┘
                                      
Overlap = 25 frames
```

### Two Modes of Operation

#### 1. **Full Video Mode** (Process as Segments = OFF)
Window Size defines the **sliding window** that moves across your video:

```
Step 1: Process frames 0-109   (110 frames)
        ┌──────────────┐
        ↓
Step 2: Process frames 85-125  (110 frames, but only 25 new frames)
                 ┌──────────────┐
                 ↓
```

- The window **slides** by `stride = window_size - overlap` frames
- Each step processes `overlap` frames from previous window + new frames
- Ensures **temporal consistency** across the entire video

#### 2. **Segment Mode** (Process as Segments = ON)
Window Size defines the **output length of each segment**:

```
Video: 500 frames
Window Size: 110, Overlap: 25

Segment 1: Frames 0-109   (110 output frames)
Segment 2: Frames 85-194  (110 output frames, 25 overlap with Seg 1)
Segment 3: Frames 170-279 (110 output frames, 25 overlap with Seg 2)
Segment 4: Frames 255-364 (110 output frames, 25 overlap with Seg 3)
Segment 5: Frames 340-449 (110 output frames, 25 overlap with Seg 4)
```

Each segment is:
1. Processed independently
2. Saved as NPZ file
3. Later merged with neighboring segments using the overlap region

---

## What is Overlap?

### Definition
**Overlap** is the number of frames that **consecutive windows/segments share**.

### Purpose

#### 1. **Temporal Consistency** (Full Video Mode)
- Overlapping frames help maintain smooth transitions
- Prevents "jumps" or flickering between windows
- Uses weighted blending for seamless results

```python
# From depth_crafter_ppl.py (line 249-251)
if overlap > 0:
    weights = torch.linspace(0, 1, overlap, device=device)
    weights = weights.view(1, overlap, 1, 1, 1)
```

The blending works like this:
```
Previous Window Output    Current Window Output
     └─────────┘               ┌─────────┘
          ↓                    ↓
    Frames 85-109    +    Frames 85-109
         ↓                      ↓
    Weight: 0.0→1.0        Weight: 1.0→0.0
              ↓              ↓
        Blended Result (smooth transition)
```

#### 2. **Segment Alignment** (Segment Mode)
Overlap enables two critical merging operations:

**A. Shift & Scale Alignment**
```python
# From merge_depth_segments.py (line 266-283)
if N_overlap > 0:
    target_raw_for_align = prev_aligned[-N_overlap:]
    pred_raw_for_align = current_raw[:N_overlap]
    
    # Compute scale (s) and shift (t) to match previous segment
    s, t = util.compute_scale_and_shift_full(...)
    aligned_current = s * current_raw + t
```

This adjusts brightness/contrast to match neighboring segments.

**B. Linear Blending**
```python
# From merge_depth_segments.py (line 326-350)
blend_pre_raw = prev_segment_aligned[-N_overlap:]
blend_post_raw = current_segment_aligned[:N_overlap]

# Alpha blend in overlap region
for i in range(N_overlap):
    alpha = i / N_overlap
    blended = (1 - alpha) * blend_pre_raw[i] + alpha * blend_post_raw[i]
```

Creates smooth cross-fade between segments.

---

## How They Work Together

### Key Formula
```
stride = window_size - overlap
```

The **stride** is how many **new frames** are processed in each step.

### Example Calculation

**Settings:** Window Size = 110, Overlap = 25
```
stride = 110 - 25 = 85

Processing 500 frames:
┌─────────────────────────────────────────────────────┐
│ Step | Window Range | New Frames | Overlap Frames  │
├─────────────────────────────────────────────────────┤
│  1   | 0-109        | 0-109      | None (first)    │
│  2   | 85-194       | 110-194    | 85-109 (25)     │
│  3   | 170-279      | 195-279    | 170-194 (25)    │
│  4   | 255-364      | 280-364    | 255-279 (25)    │
│  5   | 340-449      | 365-449    | 340-364 (25)    │
│  6   | 425-500      | 450-500    | 425-449 (25)    │
└─────────────────────────────────────────────────────┘
```

### Memory Flush Strategy

The code flushes memory periodically to prevent OOM:

```python
# From depth_crafter_ppl.py (line 262)
flush_frequency = max(1, overlap + 1)

# With overlap=25, flush every 26 segments
# This clears CUDA cache while keeping continuity
```

---

## Impact on Resources

### VRAM Usage

| Setting | VRAM Impact | Why |
|---------|-------------|-----|
| **Larger Window** | ⬆️⬆️ High | More frames in GPU memory simultaneously |
| **Larger Overlap** | ⬆️ Medium | Extra frames stored for blending |

**Approximate VRAM Formula:**
```
VRAM ∝ (window_size × resolution) + (overlap × resolution)
```

### Processing Speed

| Setting | Speed Impact | Why |
|---------|--------------|-----|
| **Larger Window** | ⬆️ Faster (fewer steps) | Fewer window transitions needed |
| **Larger Overlap** | ⬇️ Slower (more computation) | More frames processed multiple times |

**Example: Processing 500 frames**
```
Window=110, Overlap=25:  6 steps (stride=85)
Window=110, Overlap=10:  5 steps (stride=100) ← Fewer steps but less smooth
Window=60,  Overlap=25:  14 steps (stride=35) ← More steps, slower
```

### Quality Impact

| Setting | Quality Impact | Trade-off |
|---------|---------------|-----------|
| **Larger Window** | ✅ Better temporal consistency | More VRAM |
| **Larger Overlap** | ✅ Smoother transitions | Slower processing |
| **Too Small Window** | ❌ Potential flickering | Less VRAM |
| **Too Small Overlap** | ❌ Visible seams | Faster |

---

## Recommended Settings by GPU

Based on the codebase VRAM tiers:

| GPU Tier | Window Size | Overlap | Use Case |
|----------|-------------|---------|----------|
| **< 8GB** | 50 | 8 | Very low memory |
| **8-12GB** | 70 | 12 | RTX 3060, constrained |
| **12-24GB** | 80 | 15 | RTX 3090/4080 |
| **24-48GB** | 110 | 25 | RTX 4090, A5000 |
| **48GB+** | 80 | 15 | RTX 6000 Ada (conservative) |

### For Your RTX 6000 Ada (48GB)

**Default (Conservative for Stability):**
- Window Size: **80**
- Overlap: **15**

**Aggressive (If you have free VRAM):**
- Window Size: **110-140**
- Overlap: **25-30**

⚠️ **Note:** The 48GB tier uses conservative settings (80/15) because the code detects available VRAM after model loading (~41GB), not just total capacity.

---

## Adaptive Scaling for Large Videos

For very large videos, the system **automatically reduces** window size and overlap:

```python
# From stereocrafter_util.py (line 1547-1568)
complexity_score = resolution_factor × frame_factor

if complexity_score > 40:  # e.g., 4K + 1440 frames
    scale_factor = 0.25
    window_size = max(30, int(base_window × 0.25))
    overlap = max(5, int(base_overlap × 0.25))
```

**Example: 4K 1440-frame video**
```
Base settings:     window=80, overlap=15
Complexity: 45.4x (EXTREME)
Scale factor: 0.25
Final settings:  window=20, overlap=4
```

This prevents OOM errors on even the largest videos.

---

## Troubleshooting

### Problem: Out of Memory (OOM)

**Solutions (in order):**
1. Reduce **Window Size** first (biggest impact)
2. Reduce **Overlap** second
3. Reduce **resolution** (last resort)

```
Current: window=110, overlap=25 → OOM
Try:     window=80,  overlap=15  ← Better
Try:     window=60,  overlap=10  ← Even safer
```

### Problem: Flickering/Banding Between Segments

**Solutions:**
1. **Increase Overlap** (more blending frames)
2. Use **Shift & Scale** alignment method
3. Enable **Percentile Normalization** during merge

```
Current: window=110, overlap=10 → Visible seams
Try:     window=110, overlap=25  ← Smoother
```

### Problem: Processing Too Slow

**Solutions:**
1. **Increase Window Size** (fewer steps)
2. Slightly reduce Overlap (less redundant computation)
3. Process in **Segment Mode** (parallelizable)

```
Current: window=60, overlap=25 → 14 steps for 500 frames
Try:     window=110, overlap=15 → 6 steps for 500 frames
```

---

## Visual Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    WINDOW SIZE & OVERLAP                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Window Size ↑    →  Better consistency, More VRAM          │
│  Window Size ↓    →  Less VRAM, Risk of flickering          │
│                                                              │
│  Overlap ↑        →  Smoother transitions, Slower           │
│  Overlap ↓        →  Faster, Risk of visible seams          │
│                                                              │
│  Sweet Spot: Window 80-110, Overlap 15-25                   │
│  (for 1080p on 24-48GB GPU)                                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Code References

- **Sliding Window Logic:** `depthcrafter/depth_crafter_ppl.py` (lines 265-365)
- **Segment Merging:** `depthcrafter/merge_depth_segments.py` (lines 249-350)
- **VRAM Configuration:** `dependency/stereocrafter_util.py` (lines 1380-1520)
- **Adaptive Scaling:** `dependency/stereocrafter_util.py` (lines 1515-1580)
- **Help Tooltips:** `depthcrafter/help_content.json`

---

**Related Documentation:**
- `VRAM_USAGE_GUIDE.md` - GPU tier settings
- `MEMORY_OPTIMIZATION_CHANGES.md` - Memory optimization history
- `LARGE_VIDEO_GUIDE.md` - Processing large videos
- `RUNPOD_OPTIMIZATION_GUIDE.md` - Cloud optimization
