# Runpod Troubleshooting Guide

## Error: Container Boot Loop

**Symptoms:**
```
start container for writesimplybcc/stereocrafter-webui:dev: begin
start container for writesimplybcc/stereocrafter-webui:dev: begin
start container for writesimplybcc/stereocrafter-webui:dev: begin
```

Container keeps restarting without staying up.

**Diagnosis:**

1. **Run diagnostics:**
   ```bash
   bash diagnose-runpod.sh
   ```

2. **Check startup log:**
   ```bash
   cat /tmp/stereocrafter-startup.log
   ```

3. **Check container logs:**
   ```bash
   docker logs <container_id>
   ```

**Common Causes:**

### Cause 1: Script Exits Immediately

The startup script has `set -e` which exits on any error.

**Fix:** Use the updated `runpod-docker-startup.sh` which has better error handling.

### Cause 2: Missing HF_TOKEN

Old script required HF_TOKEN and exited if not set.

**Fix:** 
- Set HF_TOKEN in Runpod environment variables, OR
- Use updated script which allows running without it

### Cause 3: Python Import Error

Missing dependencies cause immediate exit.

**Fix:**
```bash
pip install -r requirements.txt
# or
pip install -r requirements-docker.txt
```

### Cause 4: Port Already in Use

Port 7860 might be occupied.

**Fix:**
```bash
# Check what's using the port
netstat -tuln | grep 7860

# Kill the process if needed
pkill -f "webui.py"
```

### Cause 5: Line Ending Issues

Windows line endings cause script to fail.

**Fix:**
```bash
bash fix-line-endings.sh
```

**Quick Test:**

Try starting manually to see the actual error:
```bash
# Skip model downloads, just start webui
bash runpod-quick-start.sh

# Or run directly
python webui.py --share --server-name 0.0.0.0 --server-port 7860
```

## Error: `$'\r': command not found`

This error occurs when shell scripts have Windows line endings (CRLF) instead of Unix line endings (LF).

### Quick Fix

**On Runpod/Linux:**
```bash
# Fix all shell scripts
bash fix-line-endings.sh
```

**On Windows (before uploading to Runpod):**
```powershell
# Fix all shell scripts
powershell -ExecutionPolicy Bypass -File fix-line-endings.ps1
```

**Manual fix for a single file:**
```bash
# On Linux/Runpod
sed -i 's/\r$//' runpod-docker-startup.sh

# Or using dos2unix (if available)
dos2unix runpod-docker-startup.sh
```

### Why This Happens

- Windows uses CRLF (`\r\n`) for line endings
- Linux/Unix uses LF (`\n`) for line endings
- Bash interprets `\r` as a literal character, causing errors

### Prevention

**Option 1: Configure Git (Recommended)**

Add to `.gitattributes`:
```
*.sh text eol=lf
```

This ensures shell scripts always use Unix line endings, even on Windows.

**Option 2: Use WSL on Windows**

If you're developing on Windows, use WSL (Windows Subsystem for Linux) to edit shell scripts.

**Option 3: Configure Your Editor**

- **VS Code:** Set `"files.eol": "\n"` for `.sh` files
- **Notepad++:** Edit → EOL Conversion → Unix (LF)
- **Sublime Text:** View → Line Endings → Unix

## Other Common Runpod Issues

### Issue: HF_TOKEN not set

**Error:**
```
ERROR: HF_TOKEN not set!
```

**Fix:**
1. Go to Runpod pod settings
2. Add environment variable: `HF_TOKEN=your_token_here`
3. Get token from: https://huggingface.co/settings/tokens

### Issue: Out of Memory

**Error:**
```
torch.OutOfMemoryError: CUDA out of memory
```

**Fix:**
The code now has adaptive scaling, but if you still get OOM:

1. **Check for competing processes:**
   ```bash
   nvidia-smi
   ```

2. **Restart the pod:**
   - Clears memory fragmentation

3. **Process in segments:**
   - Split video into smaller chunks

4. **Reduce resolution:**
   - Process at 1440p or 1080p instead of 4K

### Issue: Models not downloading

**Error:**
```
Failed to download model
```

**Fix:**

1. **Check HF_TOKEN is valid:**
   ```bash
   echo $HF_TOKEN
   ```

2. **Check internet connection:**
   ```bash
   ping huggingface.co
   ```

3. **Manually download models:**
   ```bash
   cd weights
   git lfs install
   git clone https://huggingface.co/tencent/DepthCrafter
   ```

### Issue: Permission denied

**Error:**
```
Permission denied: ./runpod-docker-startup.sh
```

**Fix:**
```bash
chmod +x runpod-docker-startup.sh
chmod +x runpod-startup.sh
bash runpod-docker-startup.sh
```

### Issue: Python module not found

**Error:**
```
ModuleNotFoundError: No module named 'xxx'
```

**Fix:**
```bash
# Reinstall requirements
pip install -r requirements.txt

# Or for Docker
pip install -r requirements-docker.txt
```

## Verification Steps

After fixing line endings, verify the scripts are correct:

```bash
# Check syntax without running
bash -n runpod-docker-startup.sh
bash -n runpod-startup.sh

# Should return no errors
```

## Getting Help

If you continue to have issues:

1. **Check the logs:**
   ```bash
   tail -f /var/log/runpod.log
   ```

2. **Check VRAM usage:**
   ```bash
   watch -n 1 nvidia-smi
   ```

3. **Verify environment:**
   ```bash
   echo "Python: $(python --version)"
   echo "PyTorch: $(python -c 'import torch; print(torch.__version__)')"
   echo "CUDA: $(python -c 'import torch; print(torch.version.cuda)')"
   echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader)"
   ```

## Quick Start Checklist

- [ ] Fix line endings: `bash fix-line-endings.sh`
- [ ] Set HF_TOKEN in Runpod environment variables
- [ ] Make scripts executable: `chmod +x *.sh`
- [ ] Run startup script: `bash runpod-docker-startup.sh`
- [ ] Verify GPU: `nvidia-smi`
- [ ] Test with small video first

## Summary

The most common issue is **line endings**. Always run `fix-line-endings.sh` after uploading files from Windows to Runpod!
