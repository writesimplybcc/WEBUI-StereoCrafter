#!/bin/bash
# Diagnostic script to help debug Runpod boot loop issues

echo "=========================================="
echo "StereoCrafter Runpod Diagnostics"
echo "=========================================="
echo "Date: $(date)"
echo ""

echo "1. Environment Variables:"
echo "   RUNPOD_POD_ID: ${RUNPOD_POD_ID:-not set}"
echo "   HF_TOKEN: ${HF_TOKEN:+set (hidden)}${HF_TOKEN:-NOT SET}"
echo "   CUDA_VISIBLE_DEVICES: ${CUDA_VISIBLE_DEVICES:-not set}"
echo ""

echo "2. System Info:"
echo "   Hostname: $(hostname)"
echo "   User: $(whoami)"
echo "   Working directory: $(pwd)"
echo "   Disk space:"
df -h . | tail -1
echo ""

echo "3. Python Environment:"
echo "   Python version: $(python --version 2>&1)"
echo "   Python location: $(which python)"
echo "   Pip version: $(pip --version 2>&1)"
echo ""

echo "4. GPU Info:"
if command -v nvidia-smi &> /dev/null; then
    echo "   GPU detected:"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
    echo "   ⚠️  nvidia-smi not found - no GPU detected"
fi
echo ""

echo "5. Required Python Packages:"
for pkg in torch diffusers transformers gradio huggingface_hub; do
    if python -c "import $pkg" 2>/dev/null; then
        version=$(python -c "import $pkg; print($pkg.__version__)" 2>/dev/null || echo "unknown")
        echo "   ✅ $pkg ($version)"
    else
        echo "   ❌ $pkg - NOT INSTALLED"
    fi
done
echo ""

echo "6. Model Weights:"
if [ -d "weights" ]; then
    echo "   weights/ directory exists"
    echo "   Contents:"
    ls -lh weights/ 2>/dev/null || echo "   (empty or inaccessible)"
    
    for model in DepthCrafter stable-video-diffusion-img2vid-xt-1-1 StereoCrafter; do
        if [ -d "weights/$model" ]; then
            size=$(du -sh "weights/$model" 2>/dev/null | cut -f1)
            echo "   ✅ $model ($size)"
        else
            echo "   ❌ $model - NOT FOUND"
        fi
    done
else
    echo "   ❌ weights/ directory does not exist"
fi
echo ""

echo "7. Startup Logs:"
if [ -f "/tmp/stereocrafter-startup.log" ]; then
    echo "   Found startup log, last 20 lines:"
    echo "   ----------------------------------------"
    tail -20 /tmp/stereocrafter-startup.log
    echo "   ----------------------------------------"
else
    echo "   ⚠️  No startup log found at /tmp/stereocrafter-startup.log"
fi
echo ""

echo "8. Container Logs (if available):"
if [ -f "/var/log/runpod.log" ]; then
    echo "   Found container log, last 20 lines:"
    echo "   ----------------------------------------"
    tail -20 /var/log/runpod.log
    echo "   ----------------------------------------"
else
    echo "   ⚠️  No container log found"
fi
echo ""

echo "9. Port Check:"
if command -v netstat &> /dev/null; then
    echo "   Listening ports:"
    netstat -tuln | grep LISTEN | grep -E ':(7860|8080|3000)' || echo "   No web ports listening"
else
    echo "   ⚠️  netstat not available"
fi
echo ""

echo "10. Process Check:"
echo "   Python processes:"
ps aux | grep python | grep -v grep || echo "   No Python processes running"
echo ""

echo "=========================================="
echo "Diagnostic Complete"
echo "=========================================="
echo ""
echo "Common Issues:"
echo "  1. HF_TOKEN not set → Set in Runpod environment variables"
echo "  2. Models not downloaded → Run: bash runpod-docker-startup.sh"
echo "  3. Python packages missing → Run: pip install -r requirements.txt"
echo "  4. Port already in use → Check process list above"
echo "  5. Line ending issues → Run: bash fix-line-endings.sh"
echo ""
echo "To view full startup log:"
echo "  cat /tmp/stereocrafter-startup.log"
echo ""
echo "To test webui directly:"
echo "  python webui.py --share --server-name 0.0.0.0 --server-port 7860"
