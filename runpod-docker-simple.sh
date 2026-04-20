#!/bin/bash
# Simple startup script for Docker images with weights already baked in
# No downloads, no checks, just start the webui

echo "=========================================="
echo "StereoCrafter WEBUI - Docker Start"
echo "=========================================="
echo "Date: $(date)"
echo "Working directory: $(pwd)"
echo ""

# Quick environment check
echo "Environment:"
echo "  Python: $(python --version 2>&1)"
echo "  GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>&1 || echo 'No GPU')"
echo "  RUNPOD_POD_ID: ${RUNPOD_POD_ID:-not set}"
echo ""

# Quick weights check (non-blocking)
echo "Weights check:"
if [ -d "weights/DepthCrafter" ]; then
    echo "  ✅ DepthCrafter"
else
    echo "  ⚠️  DepthCrafter not found"
fi

if [ -d "weights/stable-video-diffusion-img2vid-xt-1-1" ]; then
    echo "  ✅ Stable Video Diffusion"
else
    echo "  ⚠️  Stable Video Diffusion not found"
fi

if [ -d "weights/StereoCrafter" ]; then
    echo "  ✅ StereoCrafter"
else
    echo "  ⚠️  StereoCrafter not found"
fi

echo ""
echo "=========================================="
echo "Starting WEBUI..."
echo "=========================================="
echo ""
echo "Access at: http://0.0.0.0:7860"
echo "Or use Runpod's provided URL"
echo ""

# Start the webui
exec python webui.py --share --server-name 0.0.0.0 --server-port 7860
