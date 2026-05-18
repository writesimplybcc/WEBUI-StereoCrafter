#!/bin/bash
# Runpod Startup Script - Downloads weights fresh every time, then starts WEBUI
# NO persistent storage - weights are downloaded from source on each container start

set -e  # Exit on error

echo "=========================================="
echo "StereoCrafter WEBUI - Runpod Startup"
echo "=========================================="
echo "Started: $(date)"
echo "Working directory: $(pwd)"
echo ""

# Log to file for debugging
exec 1> >(tee -a /tmp/stereocrafter-startup.log)
exec 2>&1

# Environment info
echo "Environment:"
echo "  Python: $(python --version 2>&1)"
echo "  PyTorch: $(python -c 'import torch; print(torch.__version__)' 2>&1)"
echo "  CUDA: $(python -c 'import torch; print(torch.version.cuda)' 2>&1)"
echo "  GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>&1 || echo 'No GPU detected')"
echo "  RUNPOD_POD_ID: ${RUNPOD_POD_ID:-not set}"
echo ""

# Check for HF_TOKEN (required for downloading)
if [ -z "$HF_TOKEN" ]; then
    echo "❌ ERROR: HF_TOKEN not set!"
    echo "   HuggingFace token is required to download model weights."
    echo "   Please set HF_TOKEN in Runpod environment variables."
    echo ""
    exit 1
fi

echo "✅ HF_TOKEN is set"
echo ""

# Create weights directory (fresh each time)
echo "Preparing weights directory..."
rm -rf weights
mkdir -p weights
cd weights

# Login to HuggingFace
echo "Logging into HuggingFace..."
git config --global credential.helper store
python -c "import os; from huggingface_hub import login; login(token=os.environ['HF_TOKEN'].strip(), add_to_git_credential=True)" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ HuggingFace login successful"
else
    echo "❌ HuggingFace login failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "Downloading Model Weights"
echo "=========================================="
echo "This will take 10-15 minutes on first run..."
echo ""

# Download Stable Video Diffusion (~24GB)
echo "[1/3] Downloading Stable Video Diffusion (~24GB)..."
python -c "from huggingface_hub import snapshot_download; snapshot_download('stabilityai/stable-video-diffusion-img2vid-xt-1-1', local_dir='stable-video-diffusion-img2vid-xt-1-1', local_dir_use_symlinks=False)" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Stable Video Diffusion downloaded"
else
    echo "❌ Failed to download Stable Video Diffusion"
    exit 1
fi

echo ""

# Download DepthCrafter (~15GB)
echo "[2/3] Downloading DepthCrafter (~15GB)..."
python -c "from huggingface_hub import snapshot_download; snapshot_download('tencent/DepthCrafter', local_dir='DepthCrafter', local_dir_use_symlinks=False)" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ DepthCrafter downloaded"
else
    echo "❌ Failed to download DepthCrafter"
    exit 1
fi

echo ""

# Download StereoCrafter (~9GB)
echo "[3/3] Downloading StereoCrafter (~9GB)..."
python -c "from huggingface_hub import snapshot_download; snapshot_download('TencentARC/StereoCrafter', local_dir='StereoCrafter', local_dir_use_symlinks=False)" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ StereoCrafter downloaded"
else
    echo "❌ Failed to download StereoCrafter"
    exit 1
fi

echo ""
echo "=========================================="
echo "Download Complete!"
echo "=========================================="
echo "Total weights size: $(du -sh . 2>/dev/null | cut -f1 || echo 'unknown')"
echo ""

# Verify all weights exist
echo "Verifying downloaded weights..."
WEIGHTS_OK=true

if [ ! -d "stable-video-diffusion-img2vid-xt-1-1" ]; then
    echo "❌ stable-video-diffusion-img2vid-xt-1-1 missing"
    WEIGHTS_OK=false
fi

if [ ! -d "DepthCrafter" ]; then
    echo "❌ DepthCrafter missing"
    WEIGHTS_OK=false
fi

if [ ! -d "StereoCrafter" ]; then
    echo "❌ StereoCrafter missing"
    WEIGHTS_OK=false
fi

if [ "$WEIGHTS_OK" = false ]; then
    echo ""
    echo "❌ ERROR: Some weights failed to download!"
    exit 1
fi

echo "✅ All weights verified"
echo ""

cd ..

echo "=========================================="
echo "Starting StereoCrafter WEBUI"
echo "=========================================="
echo ""
echo "Access URLs:"
echo "  Local: http://0.0.0.0:7860"
echo "  Runpod: Use the URL provided in Runpod dashboard"
echo ""
echo "Startup log: /tmp/stereocrafter-startup.log"
echo ""

# Start the WEBUI (this keeps the container running)
exec python webui.py --share --server-name 0.0.0.0 --server-port 7860
