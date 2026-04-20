# NVENC FFmpeg Setup for Docker/RunPod

## The Problem

The error `No capable devices found` means FFmpeg can't access NVENC encoders, even though CUDA works. This happens because:

1. **FFmpeg wasn't compiled with NVENC support** (most common)
2. **NVIDIA Container Toolkit isn't properly configured** in RunPod
3. **Video Codec SDK headers aren't available** during FFmpeg build

## Solution: Build Docker Image with NVENC FFmpeg

The Dockerfiles have been updated to build FFmpeg from source with full NVENC support:
- Downloads NVIDIA Video Codec SDK headers
- Compiles FFmpeg 6.1.2 with `--enable-nvenc`, `--enable-cuda-llvm`, `--enable-cuvid`
- Verifies NVENC encoders are available after build

### Build Time: 10-15 minutes (FFmpeg compilation)

## Quick Start (Windows)

### Step 1: Build the Image

**Option A: PowerShell (Recommended)**
```powershell
cd E:\WEBUI-StereoCrafter
.\build-and-push-nvenc.ps1
```

**Option B: Command Prompt**
```cmd
cd E:\WEBUI-StereoCrafter
build-and-push-nvenc.bat
```

**Option C: Git Bash / WSL**
```bash
cd /e/WEBUI-StereoCrafter
./build-and-push.sh
```

### Step 2: Push to Docker Hub

The build script will prompt you. Or manually:
```bash
docker push writesimplybcc/stereocrafter-webui:nvenc
```

### Step 3: Update RunPod

1. Go to RunPod dashboard
2. Edit your pod (or create new one)
3. Change **Container Image** to: `writesimplybcc/stereocrafter-webui:nvenc`
4. Set **Container Disk** to: `60 GB`
5. Set **Expose HTTP Ports** to: `7860`
6. Add environment variable: `HF_TOKEN=your_token_here`
7. Start the pod

### Step 4: Verify NVENC

Once the pod is running, SSH in and run:
```bash
ffmpeg -encoders | grep nvenc
```

Expected output:
```
 V..... h264_nvenc           NVIDIA NVENC H.264 encoder (codec h264)
 V..... hevc_nvenc           NVIDIA NVENC HEVC encoder (codec hevc)
```

## Performance Comparison

| Encoder | 4K (43 frames) | Speed | Quality |
|---------|---------------|-------|---------|
| `libx264` (CPU, current) | ~10-20 sec | 2-4 fps | Excellent |
| `h264_nvenc` (GPU, after rebuild) | ~2-5 sec | 10-20 fps | Very Good |
| `hevc_nvenc` (GPU, HDR) | ~3-7 sec | 7-15 fps | Excellent |

## Manual Build Commands (Without Script)

If you prefer to run commands manually:

```bash
# Navigate to project directory
cd E:\WEBUI-StereoCrafter

# Build image (10-15 min)
docker build -t writesimplybcc/stereocrafter-webui:nvenc -f Dockerfile .

# Test locally (requires Docker Desktop with WSL2 backend and GPU passthrough)
docker run --gpus all -p 7860:7860 writesimplybcc/stereocrafter-webui:nvenc

# Push to Docker Hub
docker push writesimplybcc/stereocrafter-webui:nvenc
```

## Build with Baked-in Weights (Alternative)

If you want weights included in the image (faster pod startup):

```bash
# Requires HF_TOKEN
docker build --build-arg HF_TOKEN=your_token_here `
  -t writesimplybcc/stereocrafter-webui:nvenc-weights `
  -f Dockerfile.with-weights .

# Push
docker push writesimplybcc/stereocrafter-webui:nvenc-weights
```

## Troubleshooting

### Build Fails During FFmpeg Configure

**Error:** `ERROR: nvenc not found`

**Cause:** NVIDIA Video Codec SDK headers not installed

**Fix:** Ensure this line succeeds in Dockerfile:
```dockerfile
RUN git clone --depth 1 https://git.videolan.org/git/ffmpeg/nv-codec-headers.git /tmp/nv-codec-headers \
    && cd /tmp/nv-codec-headers && make && make install
```

### Build Fails During Compilation

**Error:** `cuda.h: No such file or directory`

**Cause:** CUDA headers not found (should be in nvidia/cuda base image)

**Fix:** Verify CUDA is installed in base image:
```dockerfile
RUN ls /usr/local/cuda/include/cuda.h
```

### NVENC Not Available at Runtime

**Error:** `No capable devices found` (at runtime, not build time)

**Cause:** NVIDIA Container Toolkit not properly configured in RunPod

**Fix:** RunPod should have this by default. Check:
```bash
ls -la /dev/nvidia*
# Should show: nvidia0, nvidiactl, nvidia-uvm, nvidia-modeset
```

## Fallback Behavior

Even with NVENC built, the code will **automatically fall back to CPU encoding** if:
- NVENC initialization fails
- Resolution exceeds NVENC limits (4K for H.264 on RTX 30xx)
- GPU memory is exhausted

You'll see this in the logs:
```
NVENC encoder 'h264_nvenc' not available. Falling back to CPU encoder.
Using CPU encoder: libx264 with CRF 18
```
