# URGENT: Fix OOM Error on RTX 6000 Ada

## Problem

The OOM error is happening because you're running the OLD Docker image that doesn't have the VRAM tier fixes.

## Solution

You MUST rebuild and redeploy the Docker image with the updated code.

### Step 1: Rebuild Docker Image

```bash
# On your local machine where the code is
cd /path/to/WEBUI-StereoCrafter

# Build new image with fixes
docker build -t writesimplybcc/stereocrafter-webui:latest .

# Push to Docker Hub
docker push writesimplybcc/stereocrafter-webui:latest
```

### Step 2: Restart Runpod Container

On Runpod:
1. Stop the current pod
2. Start a new pod (it will pull the latest image)
3. Wait for weights to download (~10-12 minutes)
4. WEBUI will start with correct settings

### Step 3: Verify Fix

Check the console logs for:

```
============================================================
VRAM Configuration Detection
============================================================
GPU: nvidia rtx 6000 ada generation
Total VRAM: 47.50 GB
...
✓ Selected: 48GB+ tier (optimized for stability)
  window_size: 110, overlap: 25
============================================================
```

### Step 4: Check WEBUI Defaults

Open DepthCrafter tab and verify:
- Window Size: **110** (not 130 or 140)
- Overlap: **25** (not 28 or 30)

## What Changed

### Before (OLD - Causes OOM)
- window_size: 130 or 140
- overlap: 28 or 30
- Result: 41GB + 9.81GB = **50.81GB needed** → OOM!

### After (NEW - Should work)
- window_size: 110
- overlap: 25
- Result: 41GB + ~7GB = **~48GB needed** → Fits in 47.5GB!

## Why This Happened

The Docker image you're running was built BEFORE I made the fixes to `dependency/stereocrafter_util.py`. The fixes exist in your local code but not in the deployed Docker image.

## Alternative: Quick Test Without Rebuild

If you can't rebuild immediately, manually set these values in the WEBUI:

1. Open DepthCrafter tab
2. Set Window Size: **80**
3. Set Overlap: **15**
4. Try processing again

This should work as a temporary workaround.

## Files That Need to Be in New Image

These files were updated and MUST be in the Docker image:

1. `dependency/stereocrafter_util.py` - VRAM tier fix (110/25 for 48GB)
2. `webui.py` - CUDA initialization
3. `depthcrafter/depth_crafter_ppl.py` - Memory management
4. `depthcrafter/depthcrafter_logic.py` - VRAM checks

The Dockerfile already copies these files, but you need to rebuild the image.

## Summary

**You cannot fix this without rebuilding the Docker image.**

The code fixes are done, but they're not in the running container. Rebuild, push, and restart the pod.
