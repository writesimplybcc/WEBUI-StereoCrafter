# CRITICAL FIX: Missing Frame Processing Code in Merging UI

## Problem
When using "Blend All Videos" with RTX A6000 on Runpod for processing a 4K file (Illu_V1-0002_1920_inpainted.mp4 at 43 frames) with output format as full SBS, the merging process would:
- Only process chunk 40-42 (the last chunk)
- Skip all chunks 0-39
- Fail with error: "❌ Processing completed with errors - no output files created"
- Log messages showed: "📥 Read 3 inpainted frames, 3 splatted frames for chunk 40-42", "✍️ WRITING 3 frames to FFmpeg for chunk 40-42", "✅ COMPLETED chunk 40-42, total frames written: 3"

## Root Cause
**Critical bug**: The entire frame blending and FFmpeg writing code was **MISSING** from `stereocrafter_ui/merging/merging_ui.py` between lines 1482-1510.

After reading frames and converting them to tensors (line 1482), the code immediately jumped to FFmpeg finalization (`ffmpeg_process.communicate()`) **WITHOUT**:
1. Extracting mask and original frame components from the splatted tensor
2. Processing the mask (binarization, dilation, blur, shadow shift)
3. Blending the inpainted frames with warped original frames
4. Assembling the final SBS output based on the selected format
5. **Writing frames to FFmpeg stdin** (the most critical missing piece!)

This meant:
- `frame_count` was never incremented during chunk processing
- No frames were actually written to FFmpeg for ANY chunk
- FFmpeg received no input data, resulting in empty/corrupt output files
- The loop appeared "broken" because the core processing logic was absent

## Solution
Added the complete frame processing pipeline to `stereocrafter_ui/merging/merging_ui.py` after line 1482:

### 1. Frame Component Extraction
- Extract mask, inpainted, original_left, and warped_original from tensors
- Handle both single-input and dual-input modes
- Support SBS and non-SBS input formats

### 2. Mask Processing
- Convert mask to grayscale
- Apply binarization threshold (if enabled)
- Apply mask dilation (if enabled)
- Apply Gaussian blur (if enabled)
- Apply shadow blur for depth effects (if enabled)

### 3. Frame Blending
- Blend right eye: `warped_original * (1 - mask) + inpainted * mask`
- Apply color transfer from original to inpainted (if enabled)

### 4. Output Format Assembly
Support for all output formats:
- Full SBS (Left-Right)
- Full SBS Cross-eye (Right-Left)
- Half SBS (Left-Right)
- Double SBS
- Anaglyph (Red/Cyan)
- Anaglyph Half-Color
- Right-Eye Only (default fallback)

### 5. FFmpeg Frame Writing
- Convert final frames to BGR48LE format (16-bit)
- Write each frame to FFmpeg stdin pipe
- Track frame_count for progress reporting
- Add proper error handling for BrokenPipeError

### 6. Error Handling Improvements
- Added try-except around frame writing to catch FFmpeg crashes
- Proper BrokenPipeError handling to trigger NVENC→CPU fallback
- Removed orphaned/duplicate error handling code blocks
- Fixed try-except block structure to prevent syntax errors

## Files Modified
- `stereocrafter_ui/merging/merging_ui.py` (lines 1482-1590)

### Additional Fix (2026-04-15)
Fixed `NameError: name 'settings' is not defined` error by replacing dictionary-style `settings["param"]` access with direct parameter variable names that are already extracted from function arguments at the beginning of `start_processing()`:
- `settings["use_gpu"]` → `use_gpu`
- `settings["enable_color_transfer"]` → `enable_color_transfer`
- `settings["mask_binarize_threshold"]` → `mask_binarize_threshold`
- `settings["mask_dilate_kernel_size"]` → `mask_dilate_kernel_size`
- `settings["mask_blur_kernel_size"]` → `mask_blur_kernel_size`
- `settings["shadow_shift"]` → `shadow_shift`
- `settings["shadow_start_opacity"]` → `shadow_start_opacity`
- `settings["shadow_opacity_decay"]` → `shadow_opacity_decay`
- `settings["shadow_min_opacity"]` → `shadow_min_opacity`
- `settings["shadow_decay_gamma"]` → `shadow_decay_gamma`

### Additional Fix (2026-04-15) - Tensor Dimension Mismatch
Fixed `RuntimeError: The size of tensor a (7680) must match the size of tensor b (3840) at non-singleton dimension 3` error.

**Root cause**: The code was incorrectly re-determining `is_sbs_input` by comparing splatted vs inpainted tensor widths:
```python
# WRONG: This overrode the correctly detected value from earlier
is_sbs_input = splatted_tensor.shape[3] > inpainted_tensor.shape[3]
is_dual_input = original_reader is not None
```

**Fix**: Removed the re-determination and used the values that are already correctly computed earlier in the function (lines 1020-1095) based on file suffixes and aspect ratios:
```python
# CORRECT: Use the already-determined values
# Note: is_sbs_input and is_dual_input are already determined earlier in the function
```

This ensures that the tensor extraction logic uses the correct input type detection, preventing dimension mismatches during frame blending.

## Expected Behavior After Fix
- All chunks (0-42 for a 43-frame video with chunk_size=16) will be processed
- Each chunk will:
  1. Read inpainted and splatted frames from video readers
  2. Blend frames using mask
  3. Assemble final SBS output
  4. Write frames to FFmpeg stdin
  5. Increment frame_count
- FFmpeg will receive all frame data and create a valid output file
- Progress logging will show: "✍️ WRITING X frames to FFmpeg for chunk Y-Z" and "✅ COMPLETED chunk Y-Z, total frames written: N"
- Final output file will be saved successfully

## Testing
Test the fix by:
1. Loading a 4K inpainted video with 43 frames
2. Setting output format to "Full SBS (Left-Right)"
3. Clicking "Blend All Videos"
4. Verifying log output shows ALL chunks being processed (0-16, 16-32, 32-43, etc.)
5. Confirming output file is created and contains valid video data

## Technical Details
- Frame format: BGR48LE (16-bit per channel, little-endian)
- Pixel format for FFmpeg: bgr48le
- Color space: RGB converted to BGR via OpenCV
- Frame normalization: [0.0, 1.0] range scaled to [0, 65535]
- Encoding: NVENC (GPU) with CPU fallback on failure

## Related Files
- `merging_gui.py` - Tkinter GUI implementation (reference for correct logic)
- `dependency/stereocrafter_util.py` - FFmpeg pipe utilities
- `stereocrafter_ui/merging/merging_ui.py` - WebUI merging component (fixed file)
