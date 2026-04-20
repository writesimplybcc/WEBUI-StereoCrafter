#!/bin/bash
# Docker entrypoint for StereoCrafter WEBUI
# Assumes weights are already baked into the Docker image at /workspace/weights

set -e

echo "=========================================="
echo "StereoCrafter WEBUI - Docker Container"
echo "=========================================="
echo "Started: $(date)"
echo "Working directory: $(pwd)"
echo ""

# Environment info
echo "Environment:"
echo "  Python: $(python --version 2>&1)"
echo "  PyTorch: $(python -c 'import torch; print(torch.__version__)' 2>&1)"
echo "  CUDA: $(python -c 'import torch; print(torch.version.cuda)' 2>&1)"
echo "  GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>&1 || echo 'No GPU detected')"
echo "  RUNPOD_POD_ID: ${RUNPOD_POD_ID:-not set}"
echo ""

# Verify weights exist in Docker image
echo "Verifying model weights (from Docker image):"
WEIGHTS_OK=true

if [ -d "/workspace/weights/DepthCrafter" ]; then
    echo "  ✅ DepthCrafter"
else
    echo "  ❌ DepthCrafter NOT FOUND"
    WEIGHTS_OK=false
fi

if [ -d "/workspace/weights/stable-video-diffusion-img2vid-xt-1-1" ]; then
    echo "  ✅ Stable Video Diffusion"
else
    echo "  ❌ Stable Video Diffusion NOT FOUND"
    WEIGHTS_OK=false
fi

if [ -d "/workspace/weights/StereoCrafter" ]; then
    echo "  ✅ StereoCrafter"
else
    echo "  ❌ StereoCrafter NOT FOUND"
    WEIGHTS_OK=false
fi

if [ "$WEIGHTS_OK" = false ]; then
    echo ""
    echo "❌ ERROR: Model weights missing from Docker image!"
    echo "   The Docker image should contain weights at /workspace/weights/"
    echo "   Please rebuild the Docker image with weights included."
    echo ""
    exit 1
fi

echo ""
echo "✅ All model weights verified"
echo ""

# Start the application
echo "=========================================="
echo "Starting StereoCrafter WEBUI..."
echo "=========================================="
echo ""
echo "Access URLs:"
echo "  Local: http://0.0.0.0:7860"
echo "  Runpod: Use the URL provided in Runpod dashboard"
echo ""

# Use exec to replace shell with Python process
# This ensures proper signal handling and clean shutdown
exec python webui.py --share --server-name 0.0.0.0 --server-port 7860
