# Splatting Settings Guide

## Overview

This guide explains the **Blur** and **Dilate** functions used in the Splatting UI for depth map post-processing. These settings are critical for fixing artifacts and improving stereo 3D quality.

---

## Depth Map Post-Processing Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│  1. Load depth map from DepthCrafter                        │
│  2. Apply Gamma correction (depth_gamma)                    │
│  3. Apply Dilation (depth_dilate_size_x/y)                  │
│  4. Apply Blur (depth_blur_size_x/y)                        │
│  5. Apply Left-edge fixes (depth_dilate_left, blur_left)    │
│  6. Generate stereo pair via forward warping (splatting)    │
│  7. Encode to video (MP4/PNG sequence)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. Depth Dilate (X/Y)

### Function: `custom_dilate()`

**Purpose:** Expands or shrinks depth values to fix edge artifacts and occlusion boundaries.

### Parameters

| Parameter | Type | Range | Default |
|-----------|------|-------|---------|
| `depth_dilate_size_x` | float | -10 to +10 | 0.0 |
| `depth_dilate_size_y` | float | -10 to +10 | 0.0 |

### How It Works

```
┌─────────────────────────────────────────────────────────┐
│  1. Convert depth to 16-bit (0-65535) for precision    │
│  2. Apply morphological operation:                      │
│     - Dilate (positive):  Makes bright areas larger     │
│     - Erode (negative):   Makes bright areas smaller    │
│  3. Supports fractional values (e.g., 2.5)              │
│  4. Convert back to float32                             │
└─────────────────────────────────────────────────────────┘
```

### Positive vs Negative Values

| Value | Effect | Visual Result |
|-------|--------|---------------|
| **Positive (2-5)** | **Dilation** (expand) | Depth edges grow outward |
| **Negative (-2 to -5)** | **Erosion** (shrink) | Depth edges contract inward |
| **Zero (0)** | Disabled | No change |

### Fractional Kernel Support

For smooth control, it blends between two integer kernel sizes:

```python
# Example: depth_dilate_size_x = 2.5
# Blends 50% between kernel size 2 and kernel size 3

kernel_size = 2.5
  ↓
kx_low = 3, kx_high = 5, tx = 0.5  # 50% blend
result = 0.5 × dilate_3x3 + 0.5 × dilate_5x5
```

### Visual Example

```
Before (dilate_x = 0):          After (dilate_x = 3):
    ████                            ██████
    ████  ← Object edge             ██████  ← Expanded edge
    ████                            ██████
```

### Use Cases

| Problem | Solution | Settings |
|---------|----------|----------|
| Thin occlusion artifacts | Expand depth edges | `dilate_x = 2-5` |
| Halo effects around objects | Shrink depth edges | `dilate_x = -2 to -5` |
| Vertical streaks | Vertical dilation | `dilate_y = 2-4` |
| No issues | Disabled | `dilate_x = 0, dilate_y = 0` |

---

## 2. Depth Blur (X/Y)

### Function: `custom_blur()`

**Purpose:** Smooths depth gradients to prevent banding artifacts and reduce noise.

### Parameters

| Parameter | Type | Range | Default |
|-----------|------|-------|---------|
| `depth_blur_size_x` | int | 0 to 21 | 0 |
| `depth_blur_size_y` | int | 0 to 21 | 0 |

### How It Works

```
┌─────────────────────────────────────────────────────────┐
│  1. Normalize depth to 0-1 range                        │
│  2. Scale to 16-bit (0-65535) for precision            │
│  3. Apply Gaussian Blur (OpenCV)                        │
│  4. Scale back to original range                        │
│  5. Return as float32 tensor                            │
└─────────────────────────────────────────────────────────┘
```

### Kernel Size Guide

| Kernel Size | Blur Amount | Use Case |
|-------------|-------------|----------|
| **0** (disabled) | None | No blur, sharpest depth |
| **3×3** | Light | Minor noise reduction |
| **5×5** | Medium | Smooth gradients, recommended |
| **7×7** | Heavy | Strong banding removal |
| **9×9+** | Very Heavy | Extreme smoothing (rarely needed) |

### Visual Example

```
Before (blur = 0):            After (blur = 5×5):
    ▓▓▓▓▓▓▓▓                      ░░░░░░░░
    ▓▓▓▓▓▓▓▓  ← Sharp steps       ░░░░░░░░  ← Smooth gradient
    ▓▓▓▓▓▓▓▓                      ░░░░░░░░
    (banding visible)             (smooth transition)
```

### Use Cases

| Problem | Solution | Settings |
|---------|----------|----------|
| Visible banding in smooth areas | Light blur | `blur_x = 3, blur_y = 3` |
| Noisy depth maps | Medium blur | `blur_x = 5, blur_y = 5` |
| Severe banding artifacts | Heavy blur | `blur_x = 7, blur_y = 7` |
| Want maximum sharpness | Disabled | `blur_x = 0, blur_y = 0` |

---

## 3. Depth Dilate Left

### Function: `custom_dilate_left()`

**Purpose:** Expands depth values **only on the left edge** to fix vertical streaking artifacts.

### Parameters

| Parameter | Type | Range | Default |
|-----------|------|-------|---------|
| `depth_dilate_left` | float | 0 to 10 | 0.0 |

### How It Works

```
┌─────────────────────────────────────────────────────────┐
│  Propagates pixel values from RIGHT to LEFT            │
│  Only affects the left edge of depth objects           │
│  Useful for fixing vertical streaking artifacts        │
└─────────────────────────────────────────────────────────┘
```

### Visual Example

```
Before:                         After (dilate_left = 3):
    ████                            ████
    ████  ← Vertical streak         ██████  ← Streak filled
    ████                            ████
       ↑
    Gap filled by right pixels
```

### Use Cases

| Problem | Solution | Settings |
|---------|----------|----------|
| Vertical streaks on left edges | Fill gaps | `dilate_left = 2-4` |
| Left-edge occlusion artifacts | Smooth edges | `dilate_left = 1-3` |
| No left-edge issues | Disabled | `dilate_left = 0` |

---

## 4. Depth Blur Left Mix

### Function: `custom_blur_left_masked()`

**Purpose:** Blurs only the left edge with masking to reduce artifacts, blended with original.

### Parameters

| Parameter | Type | Range | Default |
|-----------|------|-------|---------|
| `depth_blur_left` | int | 0 to 21 | 0 |
| `depth_blur_left_mix` | float | 0.0 to 1.0 | 0.5 |

### How It Works

```
┌─────────────────────────────────────────────────────────┐
│  1. Apply directional blur to left edge                │
│  2. Blend with original using mix weight               │
│  3. Can apply horizontal and vertical blur separately  │
└─────────────────────────────────────────────────────────┘
```

### Mix Weight Guide

| Mix Value | Blend | Result |
|-----------|-------|--------|
| **0.0** | 0% blurred | Original only (no effect) |
| **0.3** | 30% blurred | Subtle smoothing |
| **0.5** | 50% blurred | Balanced (recommended) |
| **0.7** | 70% blurred | Strong smoothing |
| **1.0** | 100% blurred | Full blur effect |

---

## 5. Depth Gamma

### Purpose

Adjusts the brightness/contrast curve of the depth map before processing.

### Parameters

| Parameter | Type | Range | Default |
|-----------|------|-------|---------|
| `depth_gamma` | float | 0.1 to 3.0 | 1.0 |

### Gamma Values

| Gamma | Effect | Use Case |
|-------|--------|----------|
| **< 1.0** (e.g., 0.5) | Brighten mid-tones | Bring out background detail |
| **1.0** | Linear (no change) | Default, accurate depth |
| **> 1.0** (e.g., 1.5-2.0) | Darken mid-tones | Push background to black |

### Visual Example

```
Gamma = 0.5 (brighter):       Gamma = 1.0 (linear):     Gamma = 2.0 (darker):
    ░░░░░░░░                      ▓▓▓▓▓▓▓▓                  ████
    ▓▓▓▓▓▓▓▓                      ▒▒▒▒▒▒▒▒                  ▓▓▓▓
    ▒▒▒▒▒▒▒▒                      ░░░░░░░░                  ░░░░
    (background visible)          (accurate depth)          (background crushed)
```

---

## Why 16-bit Processing?

All blur and dilate functions convert to **uint16 (0-65535)** instead of **uint8 (0-255)**:

```python
# 8-bit processing (loses precision):
normalized × 255 → uint8 → operation → /255
                      ↑
                Only 256 levels!

# 16-bit processing (preserves precision):
normalized × 65535 → uint16 → operation → /65535
                        ↑
                  65,536 levels (256× more precision!)
```

### Benefits

- ✅ Prevents **banding artifacts** in smooth gradients
- ✅ Essential for **10-bit video output** (HDR/MP4)
- ✅ Preserves **subtle depth variations**
- ✅ Professional **stereo 3D quality**

---

## Recommended Settings by Resolution

### For 4K (3840×2160)

| Parameter | Conservative | Balanced | Aggressive |
|-----------|--------------|----------|------------|
| `depth_dilate_size_x` | 0-2 | 2-3 | 4-5 |
| `depth_dilate_size_y` | 0 | 0-2 | 2-4 |
| `depth_blur_size_x` | 3-5 | 5-7 | 7-9 |
| `depth_blur_size_y` | 3-5 | 5-7 | 7-9 |
| `depth_dilate_left` | 0-2 | 2-3 | 3-5 |
| `depth_blur_left_mix` | 0.3 | 0.5 | 0.7 |
| `depth_gamma` | 1.0 | 1.2 | 1.5 |

### For 1440p (2560×1440)

| Parameter | Conservative | Balanced | Aggressive |
|-----------|--------------|----------|------------|
| `depth_dilate_size_x` | 0-2 | 2-4 | 4-6 |
| `depth_dilate_size_y` | 0 | 0-2 | 2-4 |
| `depth_blur_size_x` | 3-5 | 5-7 | 7-9 |
| `depth_blur_size_y` | 3-5 | 5-7 | 7-9 |
| `depth_dilate_left` | 0-2 | 2-4 | 4-6 |
| `depth_blur_left_mix` | 0.3 | 0.5 | 0.7 |
| `depth_gamma` | 1.0 | 1.2 | 1.5 |

### For 1080p (1920×1080)

| Parameter | Conservative | Balanced | Aggressive |
|-----------|--------------|----------|------------|
| `depth_dilate_size_x` | 0-3 | 3-5 | 5-7 |
| `depth_dilate_size_y` | 0 | 0-3 | 3-5 |
| `depth_blur_size_x` | 3-5 | 5-7 | 7-9 |
| `depth_blur_size_y` | 3-5 | 5-7 | 7-9 |
| `depth_dilate_left` | 0-3 | 3-5 | 5-7 |
| `depth_blur_left_mix` | 0.3 | 0.5 | 0.7 |
| `depth_gamma` | 1.0 | 1.2 | 1.5 |

---

## Troubleshooting Common Issues

### Issue: Visible Banding in Smooth Areas

**Symptoms:** Step-like artifacts in gradients (sky, walls, etc.)

**Solution:**
```
depth_blur_size_x: 5 → 7
depth_blur_size_y: 5 → 7
depth_gamma: 1.0 → 1.2 (optional)
```

---

### Issue: Halo Effects Around Objects

**Symptoms:** Bright/dark outlines around foreground objects

**Solution:**
```
depth_dilate_size_x: 0 → -2 to -3 (erosion)
depth_blur_size_x: 3 → 5
depth_blur_size_y: 3 → 5
```

---

### Issue: Vertical Streaks

**Symptoms:** Vertical lines in depth map, especially on edges

**Solution:**
```
depth_dilate_left: 0 → 2-4
depth_blur_left: 5-7
depth_blur_left_mix: 0.5
depth_dilate_size_y: 0 → 2-3
```

---

### Issue: Occlusion Artifacts (Black Holes)

**Symptoms:** Black regions where background should be visible

**Solution:**
```
depth_dilate_size_x: 0 → 3-5 (expand depth)
depth_gamma: 1.0 → 0.8 (brighten)
```

---

### Issue: Background Too Dark/Crushed

**Symptoms:** Far background is pure black, no detail

**Solution:**
```
depth_gamma: 1.5 → 1.0 or 0.8
depth_dilate_size_x: reduce if positive
```

---

### Issue: Depth Edges Too Sharp

**Symptoms:** Object edges look cut out, unnatural

**Solution:**
```
depth_blur_size_x: 3 → 5-7
depth_blur_size_y: 3 → 5-7
depth_dilate_size_x: reduce if high
```

---

## Quick Reference Card

### Conservative (Minimal Processing)

```
depth_dilate_size_x:    0
depth_dilate_size_y:    0
depth_blur_size_x:      3
depth_blur_size_y:      3
depth_dilate_left:      0
depth_blur_left_mix:    0.3
depth_gamma:            1.0
```

**Use when:** Depth map is already clean, minor touch-ups only

---

### Balanced (Recommended Starting Point)

```
depth_dilate_size_x:    2-3
depth_dilate_size_y:    0-2
depth_blur_size_x:      5-7
depth_blur_size_y:      5-7
depth_dilate_left:      2-3
depth_blur_left_mix:    0.5
depth_gamma:            1.2
```

**Use when:** Standard processing for most videos

---

### Aggressive (Heavy Artifact Removal)

```
depth_dilate_size_x:    4-6
depth_dilate_size_y:    2-4
depth_blur_size_x:      7-9
depth_blur_size_y:      7-9
depth_dilate_left:      4-6
depth_blur_left_mix:    0.7
depth_gamma:            1.5
```

**Use when:** Severe artifacts, noisy depth maps, challenging scenes

---

## Testing Workflow

### Step 1: Start with Balanced Settings

```
depth_dilate_size_x:    3
depth_dilate_size_y:    0
depth_blur_size_x:      5
depth_blur_size_y:      5
depth_dilate_left:      3
depth_blur_left_mix:    0.5
depth_gamma:            1.2
```

### Step 2: Preview Single Frame

Use the **Manual Preview** feature to check a representative frame.

### Step 3: Identify Issues

- Banding? → Increase blur
- Halos? → Negative dilate or more blur
- Streaks? → Increase dilate_left
- Too dark? → Reduce gamma

### Step 4: Adjust and Re-test

Make small adjustments (±1-2 values) and re-preview.

### Step 5: Process Full Video

Once satisfied, process the full video with confirmed settings.

---

## File Locations

**Core Functions:** `dependency/stereocrafter_util.py`

| Function | Line | Purpose |
|----------|------|---------|
| `custom_dilate()` | 680 | Morphological dilation/erosion |
| `custom_dilate_left()` | 768 | One-sided left dilation |
| `custom_blur_left_masked()` | 870 | Directional blur with mask |
| `custom_blur()` | 913 | Gaussian blur |

**UI Controls:** `stereocrafter_ui/splatting/splatting_ui.py`

| Setting | UI Label | Variable |
|---------|----------|----------|
| Dilate X | Depth Dilate X | `depth_dilate_size_x` |
| Dilate Y | Depth Dilate Y | `depth_dilate_size_y` |
| Blur X | Depth Blur X | `depth_blur_size_x` |
| Blur Y | Depth Blur Y | `depth_blur_size_y` |
| Dilate Left | Depth Dilate Left | `depth_dilate_left` |
| Blur Left Mix | Depth Blur Left Mix | `depth_blur_left_mix` |
| Gamma | Depth Gamma | `depth_gamma` |

---

## Summary

| Setting | Primary Use | Typical Range |
|---------|-------------|---------------|
| **Dilate X/Y** | Fix edge artifacts | -5 to +5 |
| **Blur X/Y** | Reduce banding | 0-9 |
| **Dilate Left** | Fix left-edge streaks | 0-6 |
| **Blur Left Mix** | Blend left blur | 0.3-0.7 |
| **Gamma** | Adjust depth curve | 0.8-1.5 |

**Golden Rules:**

1. **Start balanced** (settings above) and adjust based on artifacts
2. **Use 16-bit processing** (automatic) to prevent banding
3. **Preview first** before processing full video
4. **Less is more** - subtle adjustments often work best
5. **Test at target resolution** - 4K needs different settings than 1080p
