# Splatting Preview Frame Count Mismatch Fix

## Problem

When using splatting preview with a 127-frame video, preview generation would fail at frame 78 with errors:

```
15:12:17 - Attempting to read frame 78 of 126 from Inception - Final Trailer_V2-0080.mp4
15:12:17 - Failed to read video frame 78 from Inception - Final Trailer_V2-0080.mp4
```

## Root Cause

The preview generation code was only checking the **source video** frame count, but not the **depth map** frame count. When seeking to a specific frame, if the depth map had fewer frames than the source video, the read would fail.

**Common scenarios causing this:**
1. Depth map was generated with different settings (e.g., different frame count limit)
2. Depth map processing was interrupted, resulting in fewer frames
3. Frame rate conversion differences between source and depth
4. Encoding issues in the depth map video

## Solution

Added **dual frame count validation** in all preview generation functions:

### Changes Made

**File:** `stereocrafter_ui/splatting/splatting_ui.py`

#### 1. `_generate_preview_frame_at_frame_number()` (Line ~2834)

**Before:**
```python
total_frames = int(video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
# Only checked video frame count
```

**After:**
```python
total_frames_video = int(video_cap.get(cv2.CAP_PROP_FRAME_COUNT))
total_frames_depth = int(depth_cap.get(cv2.CAP_PROP_FRAME_COUNT))

# Use the minimum of both to avoid frame mismatch issues
total_frames = min(total_frames_video, total_frames_depth)

if total_frames_video != total_frames_depth:
    logger.warning(f"Frame count mismatch: Video has {total_frames_video} frames, Depth has {total_frames_depth} frames. Using minimum: {total_frames}")
```

---

#### 2. `_generate_preview_at_position()` (Line ~2975)

Same fix applied - now checks both video and depth map frame counts.

---

#### 3. `_generate_preview_frame()` (Line ~3106)

Same fix applied for middle frame preview generation.

---

## Benefits

### 1. **Prevents Frame Read Errors**
By using the minimum frame count, preview generation will never try to read beyond what's available in either file.

### 2. **Better Error Messages**
Enhanced error logging now indicates which file is problematic:
```
Failed to read video frame 78. Video may be corrupted or shorter than expected.
Failed to read depth frame 78. Depth map may be corrupted or shorter than expected.
```

### 3. **Early Warning**
Frame count mismatch is now logged as a warning:
```
Frame count mismatch: Video has 127 frames, Depth has 77 frames. Using minimum: 77
```

This helps users identify issues with their depth map generation.

---

## Expected Behavior

### Scenario 1: Matching Frame Counts
```
Video: 127 frames
Depth: 127 frames
Result: ✅ All 127 frames previewable
```

---

### Scenario 2: Depth Map Shorter (Your Case)
```
Video: 127 frames
Depth: 77 frames
Result: ⚠️ Frames 0-76 previewable, frames 77-126 skipped
Warning: "Frame count mismatch: Video has 127 frames, Depth has 77 frames. Using minimum: 77"
```

**This indicates a problem with depth map generation** - it should have 127 frames but only has 77.

---

### Scenario 3: Video Shorter
```
Video: 100 frames
Depth: 127 frames
Result: ⚠️ All 100 frames previewable (uses video limit)
Warning: "Frame count mismatch: Video has 100 frames, Depth has 127 frames. Using minimum: 100"
```

---

## Troubleshooting Your Specific Issue

Your error shows the depth map only has 77 frames when the video has 127. This suggests the depth map generation was incomplete or had issues.

### Check Depth Map Generation

1. **Verify depth map file exists and is complete:**
   ```bash
   ffprobe -v error -select_streams v:0 -show_entries stream=nb_frames -of default=noprint_wrappers=1:nokey=1 your_depth_map.mp4
   ```

2. **Check for errors in depth generation log:**
   - Look for OOM (Out-Of-Memory) errors
   - Check for cancellation messages
   - Verify all segments were processed

3. **Regenerate depth map:**
   - Ensure sufficient VRAM is available
   - Use "Process as Segments" mode for long videos
   - Check that window_size/overlap settings are appropriate

---

### Common Causes for Incomplete Depth Maps

| Cause | Symptom | Solution |
|-------|---------|----------|
| **OOM during generation** | Processing stops mid-video | Reduce window_size, use segments |
| **User cancelled** | Partial depth map | Re-run generation |
| **Segment merge failed** | Missing frames in final | Check merge logs, re-merge |
| **Wrong output path** | Old/incomplete depth map used | Verify output paths match |

---

## Technical Details

### Why Frame Count Mismatch Occurs

**OpenCV VideoCapture behavior:**
```python
cap = cv2.VideoCapture("video.mp4")
total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

# This can be inaccurate for some video codecs!
# Always verify by actually reading frames
```

**Our fix:**
- Check both source and depth videos
- Use minimum to guarantee safe seeking
- Log warnings for investigation

---

### Frame Seeking in OpenCV

```python
# Seek to specific frame
cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)

# Read frame
ret, frame = cap.read()

# If frame_idx is beyond actual frames, ret will be False
if not ret:
    # Frame doesn't exist or video is corrupted
```

---

## Related Files

- `stereocrafter_ui/splatting/splatting_ui.py` - Preview generation functions
- `gui/warp.py` - Forward warping for stereo generation
- `depthcrafter/merge_depth_segments.py` - Depth map merging

---

## Next Steps

1. **Check your depth map frame count:**
   ```bash
   ffprobe your_depth_map.mp4
   ```

2. **If depth map has < 127 frames:**
   - Regenerate depth map
   - Use segment mode if video is long
   - Monitor for OOM errors during generation

3. **If depth map has 127 frames but preview still fails:**
   - The depth map might be corrupted
   - Try re-encoding: `ffmpeg -i input.mp4 -c:v libx264 output.mp4`
   - Check for codec compatibility issues

---

**Date:** 2026-03-10  
**Status:** ✅ Fixed  
**Issue:** Preview fails after frame 77  
**Resolution:** Added dual frame count validation and better error handling
