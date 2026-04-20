# Occlusion Mask and Inpainting Guide

**Date:** 2026-03-18  
**Topic:** Understanding the Dark Shadow in Splatting Output

---

## What Is the Dark Shadow?

The **dark shadow to the right of objects** you see in the splatting preview is the **occlusion mask** - it's **NOT a bug**, it's **correct behavior** showing areas that need inpainting.

---

## Why Does It Happen?

### Depth-Based Warping

When you warp the left view to create the right view using depth-based splatting:

```
Left View → Warp (using depth map) → Right View
                               ↓
                     Some pixels have NO source
                     (occluded areas appear BLACK)
```

**The dark shadow = pixels that don't exist in the left view**

---

### Visual Example

```
Original Left View:          Warped Right View:
┌─────────────────┐          ┌─────────────────┐
│      ████       │          │      ████       │
│      ████  ←Object         │      ████       │
│      ████       │          │      ████▓▓▓▓▓▓│ ← Dark shadow
└─────────────────┘          └─────────────────┘
                                    (occlusion)
```

**Why it appears on the RIGHT:**
1. Objects shift **left** when creating right-eye view (positive disparity)
2. This reveals areas **behind** objects that weren't visible in the left view
3. These areas have **no color information** → appear black/dark

---

## The Occlusion Mask

### What It Represents

The occlusion mask is a **binary mask** where:
- **White (1.0)** = Visible pixels (have source color)
- **Black (0.0)** = Occluded pixels (no source, needs inpainting)

### 4-Panel Output Layout

```
┌──────────────┬──────────────┐
│   Original   │    Depth     │
│   (Left)     │    Map       │
├──────────────┼──────────────┤
│  Occlusion   │    Warped    │
│    Mask      │   (Right)    │
│   (BLACK)    │   (shadows)  │
└──────────────┴──────────────┘
```

**Bottom-left panel** shows the occlusion mask - black areas indicate where inpainting is needed.

---

## Is This a Problem?

### ✅ **NO - This is CORRECT**

The occlusion mask shows **where inpainting is needed**:

| Stage | What You See | Purpose |
|-------|--------------|---------|
| **Splatting** | Dark shadow on right | Shows occluded areas |
| **Inpainting** | Shadow gets filled | AI generates missing content |
| **Merging** | Clean final output | Blended with original |

---

## The Full Pipeline

```
┌─────────────────────────────────────────────────────────┐
│  1. Splatting (Current Stage)                          │
│     Input: Left view + Depth map                       │
│     Output: Warped right view + occlusion mask         │
│     You see: Dark shadows where pixels are missing     │
│     Status: ✅ EXPECTED - needs inpainting             │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  2. Inpainting (Next Stage)                            │
│     Input: Occlusion mask from splatting               │
│     Process: AI (Stable Video Diffusion) fills shadows │
│     Output: Complete right view (no shadows)           │
│     Status: ✅ OCCLUDED AREAS FILLED                   │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  3. Merging (Final Stage)                              │
│     Input: Inpainted right view + Original left view   │
│     Process: Blend into SBS format                     │
│     Output: Final stereo 3D video                      │
│     Status: ✅ CLEAN STEREO OUTPUT                     │
└─────────────────────────────────────────────────────────┘
```

---

## Technical Details

### How Occlusions Are Detected

**In `splatting_ui.py` (Line 923):**

```python
# GPU compute - core splatting
with torch.no_grad():
    right_video_tensor_raw, occlusion_mask_tensor = stereo_projector(
        left_video_tensor, 
        disp_map_tensor
    )
    
# occlusion_mask_tensor:
#   1.0 = occluded (no source pixel)
#   0.0 = visible (has source pixel)
```

### How Occlusions Are Filled (Edge Boundaries)

**Left Edge Fill (Line 1267):**
```python
def _fill_left_edge_occlusions(
    right_video_tensor: torch.Tensor, 
    occlusion_mask_tensor: torch.Tensor, 
    boundary_width_pixels: int = 3
) -> torch.Tensor:
    """
    Creates a thin, content-filled boundary at the left edge
    by replicating the first visible pixels.
    """
```

**Right Edge Fill (Line 1344):**
```python
def _fill_right_edge_occlusions(
    right_video_tensor: torch.Tensor, 
    occlusion_mask_tensor: torch.Tensor, 
    boundary_width_pixels: int = 3
) -> torch.Tensor:
    """
    Creates a thin, content-filled boundary at the right edge
    by replicating the last visible pixels.
    """
```

**Note:** These only fill **thin edge boundaries** (3 pixels), not the full occlusion area. The main occlusion filling happens in the **Inpainting UI**.

---

## Why Shadows Persist Through Merging

If you're seeing the shadow **after merging**, there are two possibilities:

### Possibility 1: You're Viewing the Occlusion Mask Panel

**4-Panel Output Layout:**
```
┌──────────────┬──────────────┐
│   Original   │    Depth     │
├──────────────┼──────────────┤
│  Occlusion   │    Warped    │  ← Bottom-left IS the mask (black = occluded)
│    Mask      │   (with      │
│   (BLACK)    │   shadows)   │
└──────────────┴──────────────┘
```

**Solution:** This is **correct** - the occlusion mask panel is **SUPPOSED** to be black where occluded.

**To view the actual warped content:** Look at the **bottom-right panel** (Warped Right).

---

### Possibility 2: Inpainting Didn't Fill Properly

If the **final merged output** still has shadows:

**Causes:**
1. **Inpainting failed** to generate content for occluded areas
2. **Mask not detected** properly (threshold issue)
3. **Blend settings** too weak
4. **Shadow parameters** need adjustment

**Solutions in Merging UI:**

| Setting | Default | Try This | Purpose |
|---------|---------|----------|---------|
| Shadow Shift | 5 | 3-7 | How far shadow extends |
| Shadow Decay Gamma | 1.3 | 1.0-1.5 | Shadow falloff curve |
| Shadow Start Opacity | 0.8 | 0.6-0.9 | Initial darkness |
| Shadow Opacity Decay | 0.08 | 0.05-0.1 | Fade rate |
| Mask Blur Kernel | 10 | 5-15 | Soften mask edges |

---

## Shadow Parameters in Merging UI

The merging UI has **shadow effect controls** to soften occlusion boundaries:

### Function Definition (Line 74)

```python
def apply_shadow_blur(
    mask: torch.Tensor, 
    shift_per_step: int, 
    start_opacity: float, 
    opacity_decay_per_step: float, 
    min_opacity: float, 
    decay_gamma: float = 1.0, 
    use_gpu: bool = True
) -> torch.Tensor:
    """
    Creates a soft shadow effect at occlusion boundaries
    to improve depth perception and hide harsh transitions.
    """
```

### Parameters Explained

| Parameter | Default | Range | Effect |
|-----------|---------|-------|--------|
| **Shadow Shift** | 5 | 0-20 | How many pixels the shadow extends |
| **Shadow Decay Gamma** | 1.3 | 0.5-2.0 | Curve of shadow falloff (higher = sharper) |
| **Shadow Start Opacity** | 0.8 | 0.0-1.0 | Initial shadow darkness at edge |
| **Shadow Opacity Decay** | 0.08 | 0.01-0.2 | How quickly opacity decreases per pixel |
| **Shadow Min Opacity** | 0.2 | 0.0-0.5 | Minimum opacity at shadow end |

### How It Works

```
Occlusion Boundary:
┌────────────────────────────────────────────────────────┐
│  Visible │  Shadow Gradient  │  Fully Occluded       │
│  Pixel   │  (soft fade)      │  (black)              │
│          │                   │                       │
│  ███████ │ ▓▓▓▒▒▒░░░         │                       │
│          │ ←Shift=5 pixels→  │                       │
└────────────────────────────────────────────────────────┘

Without shadow:  ███████│               ← Harsh edge
With shadow:     ███████│▓▓▓▒▒▒░░░      ← Soft transition
```

**Purpose:** Creates a **subtle gradient** at occlusion boundaries to make them less noticeable.

---

## How to Check What You're Seeing

### Step 1: Check Preview Source (Splatting UI)

In the **Splatting UI preview**, select different modes:

| Preview Mode | What You See | Normal? |
|--------------|--------------|---------|
| **Splat Result** | Warped right view (with shadows) | ✅ Yes |
| **Occlusion Mask** | Black/white mask (black = occluded) | ✅ Yes |
| **Anaglyph** | Red/cyan stereo preview | ✅ Yes |
| **Depth Map** | Colorized depth visualization | ✅ Yes |

**If shadows appear in "Splat Result"** → ✅ **Correct** (needs inpainting)

---

### Step 2: Check After Inpainting

After running **Inpainting UI**:

1. Open the inpainted output file
2. Shadows should be **filled with AI-generated content**
3. Some minor artifacts may remain (normal for AI inpainting)

**If shadows persist:**
- Check inpainting settings (tile number, frames chunk)
- Verify depth map quality
- Try different inference steps

---

### Step 3: Check Final Merge

After **Merging UI**:

1. Final SBS output should have **no visible shadows**
2. Occluded areas should be filled and blended
3. Transition should be smooth

**If shadows persist:**
- Adjust shadow parameters (see table above)
- Check mask threshold
- Verify inpainted video was used

---

## Common Issues and Solutions

### Issue 1: Large Black Areas in Splatting

**Symptom:** Large portions of the right view are black

**Cause:** 
- Very high disparity values
- Objects at screen edge with nowhere to shift

**Solution:**
- Reduce **Max Disparity** setting
- Adjust **Convergence Point**
- Add borders to source video

---

### Issue 2: Shadows Not Filled After Inpainting

**Symptom:** Black areas remain after inpainting step

**Causes:**
- Inpainting model failed to generate content
- Mask not properly extracted
- VRAM limitations caused incomplete processing

**Solutions:**
- Reduce tile number (use smaller tiles)
- Reduce frames chunk (process fewer frames at once)
- Increase inference steps for better quality
- Check inpainting logs for errors

---

### Issue 3: Harsh Edge at Occlusion Boundary

**Symptom:** Visible line where occluded area meets visible area

**Cause:** Mask boundary too sharp, no blending

**Solution in Merging UI:**
- Increase **Mask Blur Kernel** (10 → 15-20)
- Adjust **Shadow Shift** (5 → 3-7)
- Reduce **Shadow Start Opacity** (0.8 → 0.5-0.6)

---

### Issue 4: Shadow Too Dark/Noticeable

**Symptom:** Shadow effect is too prominent in final output

**Solution:**
```
Shadow Shift: 5 → 3
Shadow Decay Gamma: 1.3 → 1.0
Shadow Start Opacity: 0.8 → 0.5
Shadow Min Opacity: 0.2 → 0.1
```

---

## Best Practices

### For Splatting

1. **Use appropriate disparity** - too high creates large occlusions
2. **Preview before batch** - check occlusion areas in preview mode
3. **Enable both HiRes and LoRes** - LoRes generates metadata for inpainting

### For Inpainting

1. **Start with conservative settings:**
   - Tile Number: 2-3
   - Frames Chunk: 15-23
   - Inference Steps: 5-10

2. **Monitor VRAM usage** - reduce settings if OOM errors occur

3. **Check intermediate results** - verify occlusions are being filled

### For Merging

1. **Adjust shadow parameters** based on content:
   - High contrast scenes → softer shadows
   - Low contrast scenes → can use stronger shadows

2. **Test with short clips** before full batch processing

3. **Use preview function** to dial in settings

---

## Summary

| Question | Answer |
|----------|--------|
| **What is the dark shadow?** | Occlusion mask (areas with no source pixels) |
| **Is it a bug?** | ❌ No - this is correct behavior |
| **Why on the right?** | Objects shift left, revealing hidden background areas |
| **Does it persist?** | Should be removed by inpainting |
| **Can I adjust it?** | Yes - use shadow parameters in Merging UI |
| **Should I worry?** | ❌ No - this is expected and will be filled |
| **What if it remains after merging?** | Adjust shadow parameters or check inpainting quality |

---

## Key Takeaways

1. **The dark shadow is NORMAL** - it's the occlusion mask showing where pixels need to be generated

2. **It WILL be filled** - the inpainting step uses AI to generate content for occluded areas

3. **Final output should be clean** - after merging, shadows should not be visible

4. **You can adjust the appearance** - shadow parameters in Merging UI control how occlusions are blended

5. **If problems persist** - check each stage (splatting → inpainting → merging) for issues

**The occlusion mask is a feature, not a bug! It's the system telling you exactly where the AI needs to generate new content.**
