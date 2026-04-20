# FFmpeg Splatting Error Fix

**Date:** 2026-03-18  
**Issue:** FFmpeg "Broken pipe" error (return code 187) during 4K splatting

---

## Problem Summary

When processing 4K video with splatting settings (Blur X=15, Disparity=23, Convergence=0.6), FFmpeg crashes with:

```
FFmpeg pipe error: [Errno 32] Broken pipe
FFmpeg encoding failed (return code 187)
```

**Return code 187** indicates FFmpeg encountered a **fatal error** but the actual error message was hidden.

---

## Root Causes Identified

### 1. Hidden FFmpeg Error Output
- FFmpeg started with `-loglevel error` which hides diagnostic output
- Error messages not captured or logged properly
- No visibility into why FFmpeg crashed

### 2. Missing Frame Validation
- No validation of frame dimensions before sending to FFmpeg
- No check for NaN/Inf values in frame data (can occur with extreme blur settings)
- No validation that frame size matches expected dimensions

### 3. Poor Error Reporting
- Generic "Broken pipe" error without context
- No debug information about frame count, dimensions, or settings
- Difficult to diagnose the actual issue

---

## Fixes Applied

### Fix 1: Validate Output Dimensions

**Location:** Line 747

```python
# Validate dimensions before starting FFmpeg (must be even for most codecs)
if grid_width % 2 != 0 or grid_height % 2 != 0:
    logger.error(f"Invalid output dimensions: {grid_width}x{grid_height}. "
                 "Width and height must be even numbers for codec compatibility.")
    return False
```

**Why:** Most video codecs (H.264, HEVC) require even dimensions. Odd dimensions cause FFmpeg to crash.

---

### Fix 2: Log FFmpeg Startup Info

**Location:** Line 764

```python
logger.info(f"FFmpeg pipe started: {grid_width}x{grid_height} @ {processed_fps} fps, CRF={user_output_crf}")
```

**Why:** Provides visibility into FFmpeg configuration for debugging.

---

### Fix 3: Validate Frame Data Before Writing

**Location:** Line 949

```python
# Validate frame before sending to FFmpeg
if video_grid.shape[0] != grid_height or video_grid.shape[1] != grid_width:
    logger.error(f"Frame dimension mismatch: expected {grid_width}x{grid_height}, "
                 f"got {video_grid.shape[1]}x{video_grid.shape[0]}")
    encoding_successful = False
    break

if np.any(np.isnan(video_grid)) or np.any(np.isinf(video_grid)):
    logger.error(f"Invalid frame data (NaN/Inf detected) at frame {frame_count}. "
                 "Check depth processing settings.")
    encoding_successful = False
    break
```

**Why:**
- Catches dimension mismatches early
- Detects NaN/Inf from extreme blur/dilate settings
- Prevents sending invalid data to FFmpeg

---

### Fix 4: Better FFmpeg Write Error Handling

**Location:** Line 963

```python
try:
    ffmpeg_process.stdin.write(video_grid_bgr.tobytes())
except BrokenPipeError as pipe_err:
    logger.error(f"Broken pipe while writing frame {frame_count} to FFmpeg. "
                 "FFmpeg may have crashed.")
    logger.error(f"Check FFmpeg error output in finalization logs.")
    encoding_successful = False
    raise  # Re-raise to be caught by outer exception handler
```

**Why:** Provides immediate feedback when FFmpeg crashes mid-stream.

---

### Fix 5: Capture and Log FFmpeg Error Output

**Location:** Line 1005

```python
elif ffmpeg_process.returncode != 0:
    # Decode and log FFmpeg error output
    try:
        ffmpeg_error_msg = stderr_output.decode('utf-8', errors='replace') if stderr_output else "No error output"
    except:
        ffmpeg_error_msg = str(stderr_output) if stderr_output else "Unknown error"
    
    logger.error(f"FFmpeg encoding FAILED for {os.path.basename(final_output_video_path)}")
    logger.error(f"Return code: {ffmpeg_process.returncode}")
    logger.error(f"FFmpeg error output:\n{ffmpeg_error_msg}")
    logger.error(f"Debug info: grid={grid_width}x{grid_height}, fps={processed_fps}, "
                 f"frames={frame_count}/{num_frames}, CRF={user_output_crf}")
    encoding_successful = False
```

**Why:** Now shows the **actual FFmpeg error message** instead of just "Broken pipe".

---

### Fix 6: Add Timeout Handling

**Location:** Line 1013

```python
except subprocess.TimeoutExpired:
    logger.error("FFmpeg process timed out during finalize. Forcing termination.")
    ffmpeg_process.kill()
    ffmpeg_process.wait(timeout=10)
    stderr_output = b"Timeout expired"
```

**Why:** Prevents hanging if FFmpeg becomes unresponsive.

---

## Likely Causes of Your Specific Error

Based on your settings (4K, Blur X=15, Disparity=23, Convergence=0.6):

### Possible Cause 1: Extreme Blur Creating NaN/Inf

**Blur X=15** is a very high value that can cause:
- Numerical instability in Gaussian blur
- NaN/Inf values at frame edges
- FFmpeg rejecting invalid pixel data

**Solution:** Reduce Blur X to 5-9 range

### Possible Cause 2: Dimension Mismatch

4K video with certain disparity values can create:
- Odd-dimensional output (e.g., 7681 pixels wide)
- FFmpeg codec rejection

**Solution:** The fix now validates dimensions before encoding

### Possible Cause 3: FFmpeg Codec Incompatibility

The output format might not support:
- 16-bit input (bgr48le)
- Specific resolution
- CRF value

**Solution:** The improved error logging will now show the exact FFmpeg error

---

## Testing the Fix

### Step 1: Run with Current Settings (to see detailed error)

```
Blur X: 15
Disparity: 23
Convergence: 0.6
```

The new error logging will show **exactly why FFmpeg crashed**.

### Step 2: Check Logs for Specific Error

Look for:
```
FFmpeg encoding FAILED
Return code: 187
FFmpeg error output:
[actual error message here]
Debug info: grid=7680x2160, fps=30, frames=10/43, CRF=23
```

### Step 3: Adjust Settings Based on Error

| Error | Solution |
|-------|----------|
| "Invalid dimensions" | Reduce disparity or ensure even output |
| "NaN/Inf detected" | Reduce blur settings |
| "Invalid pixel format" | Check depth map bit depth |
| "Codec not supported" | Try different output format |

---

## Recommended Settings for 4K Splatting

### Conservative (Safe)

```
Depth Blur X:        5
Depth Blur Y:        5
Disparity:           15-20
Convergence:         0.5-0.6
Depth Dilate X:      2-3
Depth Gamma:         1.0-1.2
```

### Balanced (Your Current, Adjusted)

```
Depth Blur X:        7-9  (reduced from 15)
Depth Blur Y:        7-9
Disparity:           20-23
Convergence:         0.6
Depth Dilate X:      3-4
Depth Gamma:         1.2
```

### Aggressive (Risk of Artifacts)

```
Depth Blur X:        11-15
Depth Blur Y:        11-15
Disparity:           25-30
Convergence:         0.7-0.8
Depth Dilate X:      5-7
Depth Gamma:         1.5
```

---

## Debugging Workflow

### 1. Enable Debug Logging

In the WebUI, enable **Debug Logging** in the Help menu.

### 2. Check FFmpeg Error Output

After a failure, look for:
```
FFmpeg error output:
[libx264 @ 0x...] width not divisible by 2
```
or
```
[libx264 @ 0x...] invalid pixel format
```

### 3. Validate Frame Dimensions

Add this test before processing:
```python
# Check if output dimensions are even
test_width = 3840  # Your 4K width
test_height = 2160  # Your 4K height
print(f"Width even: {test_width % 2 == 0}")
print(f"Height even: {test_height % 2 == 0}")
```

### 4. Test with Lower Settings

Start with conservative settings and gradually increase:
```
Blur X: 5 → 7 → 9 → 11
Disparity: 15 → 18 → 20 → 23
```

---

## Files Modified

**File:** `stereocrafter_ui/splatting/splatting_ui.py`

| Change | Line | Purpose |
|--------|------|---------|
| Dimension validation | 747 | Prevent odd dimensions |
| Startup logging | 764 | Show FFmpeg config |
| Frame validation | 949 | Check for NaN/Inf |
| Write error handling | 963 | Catch pipe errors |
| Error output capture | 1005 | Show FFmpeg errors |
| Timeout handling | 1013 | Prevent hangs |

---

## Expected Behavior After Fix

### On Success
```
FFmpeg pipe started: 7680x2160 @ 30 fps, CRF=23
Successfully encoded video to Illu_V1-0002_3840_splatted4.mp4
```

### On Failure (Now with Details)
```
FFmpeg encoding FAILED for Illu_V1-0002_3840_splatted4.mp4
Return code: 187
FFmpeg error output:
[libx264 @ 0x5555555] width not divisible by 2 (7681x2160)
Debug info: grid=7681x2160, fps=30, frames=0/43, CRF=23
```

---

## Next Steps

1. **Test with reduced blur** (Blur X=7-9 instead of 15)
2. **Check the new error logs** for specific FFmpeg error messages
3. **Verify output dimensions** are even numbers
4. **Monitor for NaN/Inf warnings** in the logs

If the error persists, the detailed FFmpeg error output will show exactly what's wrong.

---

## Summary

| Issue | Fix | Status |
|-------|-----|--------|
| Hidden FFmpeg errors | Capture and log stderr | ✅ Fixed |
| No dimension validation | Check even dimensions | ✅ Fixed |
| No frame validation | Check for NaN/Inf | ✅ Fixed |
| Poor error reporting | Detailed debug info | ✅ Fixed |
| Timeout handling | Add subprocess timeout | ✅ Fixed |

**The fix provides full visibility into FFmpeg errors, making diagnosis much easier.**
