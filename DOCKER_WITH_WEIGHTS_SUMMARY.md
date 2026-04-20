# Docker with Weights - Final Configuration

## Your Setup

✅ **Weights are baked into Docker image**
✅ **No persistent storage needed**
✅ **No runtime downloads**
✅ **Instant startup**

## Correct Startup Script

Use **`runpod-docker-entrypoint.sh`** - This script:
- ✅ Assumes weights are in Docker image at `/workspace/weights/`
- ✅ Verifies weights exist (fails fast if missing)
- ✅ Starts webui immediately
- ❌ Does NOT try to download weights
- ❌ Does NOT configure persistent storage

## Runpod Configuration

### Container Image
```
writesimplybcc/stereocrafter-webui:dev
```

### Docker Command (Entrypoint)
```
/workspace/runpod-docker-entrypoint.sh
```

Or leave empty (ENTRYPOINT is set in Dockerfile)

### Container Disk
```
50 GB (for temp files and outputs only)
```

### Network Volume
```
NONE - Not needed!
```

### Environment Variables
```
NONE required
```

## What Happens on Startup

```
========================================
StereoCrafter WEBUI - Docker Container
========================================

Environment:
  Python: Python 3.10.12
  GPU: NVIDIA RTX 6000 Ada Generation

Verifying model weights (from Docker image):
  ✅ DepthCrafter
  ✅ Stable Video Diffusion
  ✅ StereoCrafter

✅ All model weights verified

========================================
Starting StereoCrafter WEBUI...
========================================

Access URLs:
  Local: http://0.0.0.0:7860
  Runpod: Use the URL provided in Runpod dashboard

Running on local URL:  http://0.0.0.0:7860
```

**Starts in seconds!** No downloads.

## Files for Docker Setup

### Use These:
- ✅ `runpod-docker-entrypoint.sh` - Main startup script
- ✅ `Dockerfile.with-weights` - Build Docker image with weights
- ✅ `DOCKER_BUILD_INSTRUCTIONS.md` - How to build the image

### Ignore These (for persistent storage setups):
- ❌ `RUNPOD_PERSISTENT_STORAGE.md` - Not needed
- ❌ `WEIGHTS_REDOWNLOAD_FIX.md` - Not applicable
- ❌ `runpod-docker-startup.sh` - Old script with download logic

## If Weights Are Missing

If you see:
```
❌ ERROR: Model weights missing from Docker image!
```

**This means:**
- Weights were not included during Docker build
- Need to rebuild image with weights

**Fix:**
```bash
# Rebuild with weights
docker build --build-arg HF_TOKEN=$HF_TOKEN -f Dockerfile.with-weights -t writesimplybcc/stereocrafter-webui:dev .
```

See `DOCKER_BUILD_INSTRUCTIONS.md` for details.

## Verification

### Check Image Has Weights

```bash
# Run container shell
docker run -it --rm writesimplybcc/stereocrafter-webui:dev bash

# Inside container
ls -lh /workspace/weights/
# Should show: DepthCrafter, stable-video-diffusion-img2vid-xt-1-1, StereoCrafter

du -sh /workspace/weights/*
# Should show: ~15G, ~24G, ~9G
```

### Check Image Size

```bash
docker images writesimplybcc/stereocrafter-webui:dev

# Should show ~65GB (this is normal with weights)
```

## Summary

Your Docker setup is now configured for:
- ✅ Weights baked into image (~65GB)
- ✅ No persistent storage needed
- ✅ No runtime downloads
- ✅ Instant startup on Runpod
- ✅ Proper entrypoint script

**Just deploy the image and it works!** 🎉
