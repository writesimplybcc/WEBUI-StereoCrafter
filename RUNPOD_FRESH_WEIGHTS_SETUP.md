# Runpod Setup - Fresh Weights Download on Every Start

## Overview

This configuration downloads model weights fresh from HuggingFace on every container start. No persistent storage is used.

## How It Works

1. Container starts
2. `runpod-startup.sh` runs automatically
3. Downloads all 3 models (~48GB total):
   - Stable Video Diffusion (~24GB)
   - DepthCrafter (~15GB)
   - StereoCrafter (~9GB)
4. Verifies downloads completed successfully
5. Starts WEBUI on port 7860

## Files

### `runpod-startup.sh`
Main startup script that:
- Checks for HF_TOKEN (required)
- Creates fresh `weights/` directory
- Downloads all models sequentially
- Verifies downloads
- Starts WEBUI

### `Dockerfile`
Lightweight Docker image (~5GB) that:
- Installs Python 3.10 and dependencies
- Copies application code
- Sets `runpod-startup.sh` as entrypoint
- Does NOT include weights (downloaded at runtime)

## Runpod Configuration

### 1. Build Docker Image

```bash
# Build lightweight image (no weights)
docker build -t writesimplybcc/stereocrafter-webui:latest .

# Push to Docker Hub
docker push writesimplybcc/stereocrafter-webui:latest
```

Image size: ~5GB (without weights)

### 2. Runpod Template Settings

**Container Image:**
```
writesimplybcc/stereocrafter-webui:latest
```

**Docker Command:**
Leave empty (uses ENTRYPOINT from Dockerfile)

**Container Disk:**
```
60 GB
```
(Needs space for 48GB weights + temp files)

**Network Volume:**
```
NONE
```
(Not using persistent storage)

**Environment Variables:**
```
HF_TOKEN=hf_your_token_here
```
(REQUIRED - Get from https://huggingface.co/settings/tokens)

**Expose HTTP Ports:**
```
7860
```

**GPU:**
```
RTX 6000 Ada (48GB) or RTX Pro 6000 (96GB)
```

## Startup Process

### Timeline

```
00:00 - Container starts
00:01 - Environment check
00:02 - HuggingFace login
00:03 - Start downloading Stable Video Diffusion
05:00 - Start downloading DepthCrafter
08:00 - Start downloading StereoCrafter
10:00 - Verify all weights
10:01 - Start WEBUI
10:02 - WEBUI ready at http://0.0.0.0:7860
```

**Total startup time: ~10-12 minutes** (depends on Runpod network speed)

### Console Output

```
==========================================
StereoCrafter WEBUI - Runpod Startup
==========================================
Started: Tue Mar 10 12:00:00 UTC 2026
Working directory: /workspace

Environment:
  Python: Python 3.10.12
  PyTorch: 2.1.0+cu121
  CUDA: 12.1
  GPU: NVIDIA RTX 6000 Ada Generation
  RUNPOD_POD_ID: abc123xyz

✅ HF_TOKEN is set

Preparing weights directory...
Logging into HuggingFace...
✅ HuggingFace login successful

==========================================
Downloading Model Weights
==========================================
This will take 10-15 minutes on first run...

[1/3] Downloading Stable Video Diffusion (~24GB)...
✅ Stable Video Diffusion downloaded

[2/3] Downloading DepthCrafter (~15GB)...
✅ DepthCrafter downloaded

[3/3] Downloading StereoCrafter (~9GB)...
✅ StereoCrafter downloaded

==========================================
Download Complete!
==========================================
Total weights size: 48G

Verifying downloaded weights...
✅ All weights verified

==========================================
Starting StereoCrafter WEBUI
==========================================

Access URLs:
  Local: http://0.0.0.0:7860
  Runpod: Use the URL provided in Runpod dashboard

Startup log: /tmp/stereocrafter-startup.log

Running on local URL:  http://0.0.0.0:7860
```

## Error Handling

### Missing HF_TOKEN

```
❌ ERROR: HF_TOKEN not set!
   HuggingFace token is required to download model weights.
   Please set HF_TOKEN in Runpod environment variables.
```

**Fix:** Add HF_TOKEN to Runpod environment variables

### Download Failed

```
❌ Failed to download DepthCrafter
```

**Fix:** Check HuggingFace token permissions and network connectivity

### Insufficient Disk Space

```
No space left on device
```

**Fix:** Increase Container Disk to at least 60GB

## Advantages

✅ No persistent storage needed
✅ Always get latest model versions
✅ Clean state on every restart
✅ No stale cache issues
✅ Simple Runpod configuration

## Disadvantages

⚠️ 10-12 minute startup time on each container start
⚠️ Uses Runpod bandwidth for downloads
⚠️ Requires stable internet connection

## Cost Optimization

If startup time is a concern, consider:

1. **Use Runpod's persistent storage** (but you said not to)
2. **Keep container running** instead of stopping/starting
3. **Use spot instances** for lower cost during long processing jobs

## Troubleshooting

### Check Startup Logs

```bash
# Inside container
cat /tmp/stereocrafter-startup.log
```

### Verify Weights Downloaded

```bash
# Inside container
ls -lh /workspace/weights/
# Should show: DepthCrafter, StereoCrafter, stable-video-diffusion-img2vid-xt-1-1

du -sh /workspace/weights/*
# Should show: ~15G, ~9G, ~24G
```

### Test HuggingFace Token

```bash
# Inside container
python -c "from huggingface_hub import login; login(token='YOUR_TOKEN')"
```

## Summary

This setup downloads fresh weights on every container start, ensuring no persistent storage is needed. The 10-12 minute startup time is the tradeoff for always having clean, up-to-date models.

Once WEBUI starts, it will use the correct 48GB tier settings (window_size: 140, overlap: 30) for optimal performance on RTX 6000 Ada.
