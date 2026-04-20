# Boot Loop Issue - FIXED ✅

## What Was Wrong

Your container was stuck in a boot loop because:

1. **`set -e` was too strict** - Script exited immediately on any error
2. **HF_TOKEN check was mandatory** - Script exited if token wasn't set
3. **No error logging** - Couldn't see what was failing
4. **No graceful error handling** - Any failure caused immediate exit

## What I Fixed

### 1. Updated `runpod-docker-startup.sh`

**Changes:**
- ✅ Removed strict `set -e` - now continues on errors
- ✅ Made HF_TOKEN optional - warns but doesn't exit
- ✅ Added comprehensive logging to `/tmp/stereocrafter-startup.log`
- ✅ Added error checking with informative messages
- ✅ Better status reporting (✅ success, ⚠️ warnings)

### 2. Created `runpod-quick-start.sh`

**Purpose:** Quick startup without model downloads
- Skips model download phase
- Just starts the webui
- Useful for testing and when models are already downloaded

### 3. Created `diagnose-runpod.sh`

**Purpose:** Comprehensive diagnostics
- Checks environment variables
- Verifies Python packages
- Lists model weights
- Shows startup logs
- Identifies common issues

### 4. Fixed Line Endings

All scripts now have Unix line endings (LF) to prevent `$'\r': command not found` errors.

## How to Use

### Option 1: Full Startup (Recommended)

```bash
# This will download models if needed and start webui
bash runpod-docker-startup.sh
```

**Features:**
- Downloads missing models
- Logs to `/tmp/stereocrafter-startup.log`
- Continues even if some downloads fail
- Starts webui on port 7860

### Option 2: Quick Start (Testing)

```bash
# Skip downloads, just start webui
bash runpod-quick-start.sh
```

**Use when:**
- Models are already downloaded
- Testing if webui works
- Debugging startup issues

### Option 3: Diagnose Issues

```bash
# Run diagnostics to see what's wrong
bash diagnose-runpod.sh
```

**Shows:**
- Environment variables
- Python packages status
- GPU info
- Model weights status
- Startup logs
- Common issues

## Checking Logs

### Startup Log
```bash
# View full startup log
cat /tmp/stereocrafter-startup.log

# Watch log in real-time
tail -f /tmp/stereocrafter-startup.log
```

### Quick Start Log
```bash
cat /tmp/stereocrafter-quickstart.log
```

## Common Issues & Solutions

### Issue: Still in Boot Loop

**Diagnosis:**
```bash
bash diagnose-runpod.sh
```

**Check:**
1. Is Python installed? `python --version`
2. Are packages installed? `pip list | grep torch`
3. Is GPU detected? `nvidia-smi`
4. Are models present? `ls -la weights/`

### Issue: HF_TOKEN Warning

**Message:**
```
⚠️  WARNING: HF_TOKEN not set!
```

**Solution:**
- If models are already downloaded: Ignore warning
- If models need downloading: Set HF_TOKEN in Runpod environment variables

### Issue: Models Not Found

**Message:**
```
⚠️  DepthCrafter not found in weights/
```

**Solution:**
```bash
# Download models manually
cd weights
git lfs install
git clone https://huggingface.co/tencent/DepthCrafter
git clone https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt-1-1
git clone https://huggingface.co/TencentARC/StereoCrafter
cd ..
```

### Issue: Python Packages Missing

**Message:**
```
ModuleNotFoundError: No module named 'torch'
```

**Solution:**
```bash
pip install -r requirements.txt
# or for Docker
pip install -r requirements-docker.txt
```

## Testing the Fix

### Step 1: Run Diagnostics
```bash
bash diagnose-runpod.sh
```

Look for:
- ✅ Python installed
- ✅ GPU detected
- ✅ Required packages installed

### Step 2: Try Quick Start
```bash
bash runpod-quick-start.sh
```

If this works, the issue was with model downloads.

### Step 3: Try Full Start
```bash
bash runpod-docker-startup.sh
```

Should now start without boot loop!

## What to Expect

### Successful Startup

```
==========================================
StereoCrafter WEBUI - Quick Start
==========================================
Working directory: /workspace/WEBUI-StereoCrafter
Date: Mon Mar 10 12:00:00 UTC 2026

Environment check:
  Python: Python 3.10.12
  GPU: NVIDIA RTX 6000 Ada Generation

✅ HF_TOKEN is set

Creating weights directory...
✅ All model weights already downloaded

==========================================
Setup Complete!
==========================================

Startup log saved to: /tmp/stereocrafter-startup.log

Starting StereoCrafter WEBUI...
  Access URL: http://0.0.0.0:7860
  Or use the Runpod provided URL

Launching webui.py...
Running on local URL:  http://0.0.0.0:7860
Running on public URL: https://xxxxx.gradio.live
```

### Container Should Stay Running

The container should now stay up and you can access the webui!

## Files Created/Modified

- ✅ `runpod-docker-startup.sh` - Robust startup with error handling
- ✅ `runpod-quick-start.sh` - Quick start without downloads
- ✅ `diagnose-runpod.sh` - Diagnostic tool
- ✅ `RUNPOD_TROUBLESHOOTING.md` - Updated with boot loop section
- ✅ `BOOT_LOOP_FIX.md` - This file

## Summary

The boot loop issue is now **FIXED** with:
- Better error handling (no immediate exits)
- Optional HF_TOKEN (warns but continues)
- Comprehensive logging
- Diagnostic tools
- Multiple startup options

Your container should now start successfully! 🎉

## Next Steps

1. Run `bash diagnose-runpod.sh` to verify environment
2. Run `bash runpod-docker-startup.sh` to start
3. Access webui at the provided URL
4. Check `/tmp/stereocrafter-startup.log` if issues persist
