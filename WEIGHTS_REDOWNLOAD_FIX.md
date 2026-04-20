# Weights Re-downloading Issue - SOLVED ✅

## Problem

Weights are being re-downloaded every time the pod starts, even though they're in the Docker image.

**Why:** Container storage is **ephemeral** - it's lost when the container restarts.

## Solution: Runpod Network Volumes

Use Runpod's **Network Volumes** for persistent storage.

## Quick Setup (5 minutes)

### 1. Create Network Volume

**In Runpod Dashboard:**
1. Go to **Storage** → **Network Volumes**
2. Click **"+ New Network Volume"**
3. Settings:
   - Name: `stereocrafter-weights`
   - Size: `100 GB`
   - Region: Same as your pods
4. Click **"Create"**

### 2. Attach to Pod

**In Pod Settings:**
1. **Volume Mount Path:** `/workspace/weights`
2. **Select Volume:** `stereocrafter-weights`
3. **Container Disk:** `50 GB` (for code/temp)

### 3. First Run

```bash
bash runpod-docker-startup.sh
```

**Downloads models once** (~20-30 minutes for 50GB)

### 4. All Future Runs

```bash
bash runpod-docker-startup.sh
```

**Output:**
```
✅ All model weights already downloaded and verified
   Skipping download phase...

Starting StereoCrafter WEBUI...
```

**Starts instantly!** No re-downloading.

## What Changed in Code

Updated `runpod-docker-startup.sh` to:
- ✅ Check for model files, not just directories
- ✅ Verify models are complete (check for key files)
- ✅ Show disk usage
- ✅ Better status messages

## Cost Analysis

### Network Volume Cost
- **Storage:** $0.10/GB/month
- **100GB:** $10/month

### Break-even Point
- **Without volume:** 20 min download × $1/hr = $0.33 per start
- **With volume:** $10/month ÷ $0.33 = **30 starts/month**

**If you start pods >30 times/month, network volume saves money!**

## Verification

### Check Volume is Mounted
```bash
df -h /workspace/weights
```

Should show network volume, not container disk.

### Check Models Exist
```bash
ls -lh /workspace/weights/
du -sh /workspace/weights/*
```

Should show:
- `DepthCrafter/` (~15GB)
- `stable-video-diffusion-img2vid-xt-1-1/` (~24GB)
- `StereoCrafter/` (~9GB)

## Alternative: Bake into Docker Image

If you don't want network volumes, you can bake weights into the Docker image:

**Pros:**
- No volume cost
- Portable

**Cons:**
- 50GB image size
- Slow to build/push/pull
- Wastes bandwidth

**Not recommended** unless you rarely start pods.

## Summary

✅ **Network Volume = Persistent Storage**
✅ **One-time download, permanent benefit**
✅ **Instant pod startup after first run**
✅ **Cost-effective for frequent use**

**Setup:** 5 minutes
**First download:** 20-30 minutes
**Future starts:** Instant!

Your weights will now persist! 🎉

## Documentation

See **`RUNPOD_PERSISTENT_STORAGE.md`** for complete guide.
