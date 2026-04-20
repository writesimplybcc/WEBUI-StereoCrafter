#!/bin/bash
# Quick start script - skips model downloads, just starts the webui
# Use this if models are already downloaded or for testing

echo "=========================================="
echo "StereoCrafter WEBUI - Quick Start (No Downloads)"
echo "=========================================="
echo "Working directory: $(pwd)"
echo "Date: $(date)"
echo ""

# Log everything
exec 1> >(tee -a /tmp/stereocrafter-quickstart.log)
exec 2>&1

echo "Environment check:"
echo "  Python: $(python --version 2>&1)"
echo "  GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>&1 || echo 'No GPU detected')"
echo ""

echo "Checking for model weights..."
if [ -d "weights/DepthCrafter" ]; then
    echo "✅ DepthCrafter found"
else
    echo "⚠️  DepthCrafter not found in weights/"
fi

if [ -d "weights/stable-video-diffusion-img2vid-xt-1-1" ]; then
    echo "✅ Stable Video Diffusion found"
else
    echo "⚠️  Stable Video Diffusion not found in weights/"
fi

if [ -d "weights/StereoCrafter" ]; then
    echo "✅ StereoCrafter found"
else
    echo "⚠️  StereoCrafter not found in weights/"
fi

echo ""
echo "=========================================="
echo "Starting WEBUI..."
echo "=========================================="
echo ""
echo "Startup log: /tmp/stereocrafter-quickstart.log"
echo "Access URL: http://0.0.0.0:7860"
echo ""

# Start the application
python webui.py --share --server-name 0.0.0.0 --server-port 7860
