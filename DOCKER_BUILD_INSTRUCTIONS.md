# Docker Build Instructions

## Building Docker Image with Weights

Since your weights are baked into the Docker image, here's how to properly build and use it.

## Option 1: Build with Weights (Recommended)

### Prerequisites
- Docker installed
- HuggingFace account with access token
- ~100GB free disk space
- Good internet connection (will download ~50GB)

### Build Command

```bash
# Set your HuggingFace token
export HF_TOKEN="your_huggingface_token_here"

# Build the image (takes 30-60 minutes)
docker build \
  --build-arg HF_TOKEN=$HF_TOKEN \
  -f Dockerfile.with-weights \
  -t writesimplybcc/stereocrafter-webui:dev \
  .

# Push to registry (optional, for Runpod)
docker push writesimplybcc/stereocrafter-webui:dev
```

### What This Does

1. **Installs system dependencies** (Python, CUDA, etc.)
2. **Installs Python packages** (PyTorch, Diffusers, etc.)
3. **Copies your code** into the image
4. **Downloads model weights** (~50GB) during build
5. **Bakes weights into image** - no runtime downloads needed!

### Image Size

- **Without weights:** ~15GB
- **With weights:** ~65GB

## Option 2: Use Existing Image

If the image is already built and pushed to a registry:

```bash
# Pull the image
docker pull writesimplybcc/stereocrafter-webui:dev

# Run locally
docker run --gpus all -p 7860:7860 writesimplybcc/stereocrafter-webui:dev
```

## Runpod Configuration

### Pod Settings

**When creating a pod on Runpod:**

1. **Container Image:**
   ```
   writesimplybcc/stereocrafter-webui:dev
   ```

2. **Container Disk:**
   ```
   50 GB (for temp files and outputs)
   ```

3. **Docker Command:** (Leave empty or use)
   ```
   /workspace/runpod-docker-entrypoint.sh
   ```

4. **Expose HTTP Ports:**
   ```
   7860
   ```

5. **Environment Variables:**
   - None required (weights are in image)
   - Optional: `RUNPOD_POD_ID` (auto-set by Runpod)

### NO Network Volume Needed!

Since weights are in the Docker image:
- ✅ No network volume required
- ✅ No persistent storage needed
- ✅ Instant startup (no downloads)
- ✅ Works offline

## Startup Scripts

### For Docker with Weights

Use `runpod-docker-entrypoint.sh` (already set as ENTRYPOINT):
- Verifies weights exist
- Starts webui immediately
- No downloads

### Alternative Scripts

**If you need to override:**

```bash
# Simple start (no checks)
bash runpod-docker-simple.sh

# With verification
bash runpod-docker-entrypoint.sh
```

## Verifying the Build

### Check Image Size

```bash
docker images writesimplybcc/stereocrafter-webui:dev

# Should show ~65GB
```

### Check Weights in Image

```bash
# Run a shell in the container
docker run -it --rm writesimplybcc/stereocrafter-webui:dev bash

# Inside container, check weights
ls -lh /workspace/weights/
du -sh /workspace/weights/*

# Should show:
# 15G  DepthCrafter
# 24G  stable-video-diffusion-img2vid-xt-1-1
# 9G   StereoCrafter
```

### Test Run

```bash
# Run locally with GPU
docker run --gpus all -p 7860:7860 writesimplybcc/stereocrafter-webui:dev

# Should start immediately without downloads
# Access at http://localhost:7860
```

## Troubleshooting

### Weights Not in Image

**Symptom:**
```
❌ ERROR: Model weights missing from Docker image!
```

**Cause:** HF_TOKEN not provided during build

**Fix:**
```bash
# Rebuild with token
docker build --build-arg HF_TOKEN=$HF_TOKEN -f Dockerfile.with-weights -t writesimplybcc/stereocrafter-webui:dev .
```

### Image Too Large

**Symptom:** Image is 65GB+

**This is normal!** Model weights are ~50GB.

**Options:**
1. Accept the size (recommended for Runpod)
2. Use multi-stage build to compress
3. Use network volumes instead (not recommended per your requirement)

### Build Fails During Weight Download

**Symptom:**
```
Error downloading models
```

**Causes:**
- Invalid HF_TOKEN
- Network timeout
- Insufficient disk space

**Fix:**
```bash
# Verify token works
python -c "from huggingface_hub import login; login(token='$HF_TOKEN')"

# Check disk space
df -h

# Retry build with more verbose output
docker build --progress=plain --build-arg HF_TOKEN=$HF_TOKEN -f Dockerfile.with-weights -t writesimplybcc/stereocrafter-webui:dev .
```

### Runpod Still Downloading Weights

**Symptom:** Weights downloading on Runpod despite being in image

**Cause:** Using wrong startup script or old image

**Fix:**
1. Verify image tag: `writesimplybcc/stereocrafter-webui:dev`
2. Check Docker Command is empty or uses `runpod-docker-entrypoint.sh`
3. Pull latest image: `docker pull writesimplybcc/stereocrafter-webui:dev`

## Build Time Estimates

| Step | Time | Size |
|------|------|------|
| Base image pull | 5 min | 5 GB |
| System packages | 2 min | 2 GB |
| Python packages | 10 min | 8 GB |
| Code copy | 1 min | 1 GB |
| **Weight download** | **20-30 min** | **50 GB** |
| **Total** | **40-50 min** | **65 GB** |

## Optimization Tips

### Faster Builds

1. **Use build cache:**
   ```bash
   # Don't use --no-cache unless necessary
   docker build --build-arg HF_TOKEN=$HF_TOKEN -f Dockerfile.with-weights -t writesimplybcc/stereocrafter-webui:dev .
   ```

2. **Parallel downloads:**
   - Already optimized in Dockerfile
   - Uses Python's concurrent downloads

3. **Local registry:**
   - Push to local registry for faster pulls
   - Useful for multiple Runpod pods

### Smaller Images (Advanced)

If you need smaller images:

1. **Multi-stage build:**
   - Build in one stage
   - Copy only needed files to final stage
   - Can reduce by ~10GB

2. **Compress weights:**
   - Use model quantization
   - Trade quality for size

3. **Separate weight layers:**
   - Use Docker layer caching
   - Weights in separate layer for reuse

## Summary

✅ **Weights baked into Docker image**
✅ **No runtime downloads needed**
✅ **No network volumes required**
✅ **Instant startup on Runpod**
✅ **~65GB image size (normal)**

**Build once, use everywhere!**
