# Runpod Persistent Storage Setup

## Problem: Weights Re-downloading Every Time

Even though weights are in your Docker image, they get lost when the container restarts because container storage is **ephemeral**.

## Solution: Network Volumes

Runpod's **Network Volumes** provide persistent storage that survives container restarts.

## Setup Guide

### Step 1: Create Network Volume (One-time Setup)

1. **Go to Runpod Dashboard**
   - Navigate to https://runpod.io

2. **Create Network Volume:**
   - Click **"Storage"** in left sidebar
   - Click **"+ Network Volumes"**
   - Click **"+ New Network Volume"**

3. **Configure Volume:**
   ```
   Name: stereocrafter-weights
   Size: 100 GB (models are ~50GB, leave room for growth)
   Region: Same as your pods (e.g., US-West)
   ```

4. **Click "Create"**
   - Wait for volume to be created (~1 minute)
   - Note the volume ID

### Step 2: Attach Volume to Pod

When creating a new pod or editing existing:

1. **In Pod Configuration:**
   - Scroll to **"Volume Mount Path"**
   - Enter: `/workspace/weights`

2. **Select Volume:**
   - Click **"Select Volume"**
   - Choose: `stereocrafter-weights`

3. **Container Disk:**
   - Set to: 50GB (for code and temp files)
   - The weights will be on the network volume

4. **Deploy Pod**

### Step 3: First Run - Download Models

On first run with the volume attached:

```bash
# The startup script will detect empty volume and download models
bash runpod-docker-startup.sh
```

**This will take 15-30 minutes** to download ~50GB of models.

**Progress:**
```
Downloading stable-video-diffusion-img2vid-xt-1-1...
  [████████████████████] 100% - 23.5 GB

Downloading DepthCrafter...
  [████████████████████] 100% - 15.2 GB

Downloading StereoCrafter...
  [████████████████████] 100% - 8.7 GB

✅ All models downloaded
Total size: 47.4 GB
```

### Step 4: Subsequent Runs - Instant Start

On all future runs:

```bash
bash runpod-docker-startup.sh
```

**Output:**
```
Checking for existing models in persistent storage...
  Location: /workspace/weights
  Disk usage: 47.4G

✅ All model weights already downloaded and verified
   Skipping download phase...

Starting StereoCrafter WEBUI...
```

**Starts in seconds!** No re-downloading.

## Verification

### Check Volume is Mounted

```bash
# Check mount point
df -h /workspace/weights

# Should show network volume, not container disk
# Example output:
# Filesystem      Size  Used Avail Use% Mounted on
# 10.0.0.50:/vol  100G   48G   52G  48% /workspace/weights
```

### Check Models Exist

```bash
ls -lh /workspace/weights/

# Should show:
# drwxr-xr-x DepthCrafter/
# drwxr-xr-x stable-video-diffusion-img2vid-xt-1-1/
# drwxr-xr-x StereoCrafter/
```

### Check Model Sizes

```bash
du -sh /workspace/weights/*

# Should show:
# 15G    DepthCrafter
# 24G    stable-video-diffusion-img2vid-xt-1-1
# 8.7G   StereoCrafter
```

## Cost Considerations

### Network Volume Pricing

- **Storage:** ~$0.10/GB/month
- **100GB volume:** ~$10/month
- **Bandwidth:** Free within same region

### Cost Comparison

**Without Network Volume:**
- Download time: 20 minutes per pod start
- Bandwidth: Free (but wastes time)
- **Cost:** $0.33 per start @ $1/hour (20 min × $1/hr)

**With Network Volume:**
- Download time: 0 minutes (instant)
- Storage cost: $10/month
- **Break-even:** 30 pod starts per month

**If you start pods more than 30 times/month, network volume saves money!**

## Alternative: Bake Weights into Docker Image

If you don't want to use network volumes, you can bake weights into the Docker image:

### Pros:
- ✅ No network volume cost
- ✅ Faster pod startup (no volume mount)
- ✅ Portable (image contains everything)

### Cons:
- ❌ Huge image size (~50GB)
- ❌ Slow to build/push/pull
- ❌ Wastes bandwidth on every pull
- ❌ Hard to update models

### How to Bake Weights:

**In Dockerfile:**
```dockerfile
# Download weights during build
RUN cd /workspace/weights && \
    huggingface-cli download stabilityai/stable-video-diffusion-img2vid-xt-1-1 --local-dir stable-video-diffusion-img2vid-xt-1-1 && \
    huggingface-cli download tencent/DepthCrafter --local-dir DepthCrafter && \
    huggingface-cli download TencentARC/StereoCrafter --local-dir StereoCrafter
```

**Build:**
```bash
docker build -t writesimplybcc/stereocrafter-webui:dev .
docker push writesimplybcc/stereocrafter-webui:dev
```

**Note:** This creates a ~50GB image that takes 30+ minutes to push/pull.

## Recommended Setup

### For Frequent Use (>30 starts/month):
**Use Network Volume**
- One-time download
- Instant subsequent starts
- Cost-effective

### For Occasional Use (<30 starts/month):
**Re-download each time**
- No storage cost
- Acceptable for occasional use
- Current default behavior

### For Production/Team Use:
**Network Volume + Shared Access**
- Multiple team members share same volume
- One download, everyone benefits
- Most cost-effective

## Troubleshooting

### Volume Not Mounting

**Check:**
```bash
mount | grep weights
df -h | grep weights
```

**If not mounted:**
1. Stop pod
2. Verify volume is attached in pod settings
3. Restart pod

### Models Still Re-downloading

**Check startup script:**
```bash
cat /tmp/stereocrafter-startup.log | grep "already downloaded"
```

**If not found:**
- Volume might not be mounted at `/workspace/weights`
- Check mount path in pod settings

### Volume Full

**Check usage:**
```bash
df -h /workspace/weights
```

**If full:**
1. Increase volume size in Runpod dashboard
2. Or clean up old files

### Slow Network Volume

**Symptoms:**
- Slow model loading
- High latency

**Solutions:**
1. Ensure volume is in same region as pod
2. Use SSD-backed volumes (faster tier)
3. Consider baking weights into image instead

## Summary

✅ **Network Volumes solve the re-download problem**
✅ **One-time setup, permanent benefit**
✅ **Cost-effective for frequent use**
✅ **Instant pod startup after first download**

**Setup time:** 5 minutes
**First download:** 20-30 minutes
**All future starts:** Instant!

Your weights will now persist across pod restarts! 🎉
