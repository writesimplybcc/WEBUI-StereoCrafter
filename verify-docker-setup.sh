#!/bin/bash
# Verification script to check Docker setup and diagnose weight download issues
# Run this inside your Runpod container to see what's happening

echo "=========================================="
echo "StereoCrafter Docker Setup Verification"
echo "=========================================="
echo "Date: $(date)"
echo ""

# 1. Check which script is running
echo "1. STARTUP SCRIPT CHECK"
echo "   Current process tree:"
ps aux | grep -E "bash|python|webui" | grep -v grep
echo ""

# 2. Check if weights exist in Docker image
echo "2. WEIGHTS IN DOCKER IMAGE"
echo "   Checking /workspace/weights/..."
if [ -d "/workspace/weights" ]; then
    echo "   ✅ /workspace/weights/ exists"
    echo ""
    echo "   Contents:"
    ls -lh /workspace/weights/ 2>/dev/null || echo "   (empty or unreadable)"
    echo ""
    echo "   Sizes:"
    du -sh /workspace/weights/* 2>/dev/null || echo "   (no subdirectories)"
    echo ""
    echo "   Total size:"
    du -sh /workspace/weights/ 2>/dev/null || echo "   (cannot calculate)"
else
    echo "   ❌ /workspace/weights/ does NOT exist"
fi
echo ""

# 3. Check for specific model directories
echo "3. MODEL DIRECTORIES"
MODELS_FOUND=0
MODELS_TOTAL=3

if [ -d "/workspace/weights/DepthCrafter" ]; then
    echo "   ✅ DepthCrafter found"
    MODELS_FOUND=$((MODELS_FOUND + 1))
else
    echo "   ❌ DepthCrafter NOT found"
fi

if [ -d "/workspace/weights/stable-video-diffusion-img2vid-xt-1-1" ]; then
    echo "   ✅ Stable Video Diffusion found"
    MODELS_FOUND=$((MODELS_FOUND + 1))
else
    echo "   ❌ Stable Video Diffusion NOT found"
fi

if [ -d "/workspace/weights/StereoCrafter" ]; then
    echo "   ✅ StereoCrafter found"
    MODELS_FOUND=$((MODELS_FOUND + 1))
else
    echo "   ❌ StereoCrafter NOT found"
fi

echo ""
echo "   Models found: $MODELS_FOUND/$MODELS_TOTAL"
echo ""

# 4. Check Docker image info
echo "4. DOCKER IMAGE INFO"
if [ -f "/.dockerenv" ]; then
    echo "   ✅ Running inside Docker container"
else
    echo "   ⚠️  Not running in Docker (or /.dockerenv missing)"
fi
echo ""

# 5. Check environment variables
echo "5. ENVIRONMENT VARIABLES"
echo "   RUNPOD_POD_ID: ${RUNPOD_POD_ID:-not set}"
echo "   HF_TOKEN: ${HF_TOKEN:+set (hidden)}${HF_TOKEN:-not set}"
echo "   DOWNLOAD_WEIGHTS: ${DOWNLOAD_WEIGHTS:-not set}"
echo ""

# 6. Check which startup scripts exist
echo "6. AVAILABLE STARTUP SCRIPTS"
for script in runpod-docker-entrypoint.sh runpod-docker-startup.sh runpod-startup.sh; do
    if [ -f "/workspace/$script" ]; then
        echo "   ✅ $script exists"
        if [ -x "/workspace/$script" ]; then
            echo "      (executable)"
        else
            echo "      (NOT executable)"
        fi
    else
        echo "   ❌ $script NOT found"
    fi
done
echo ""

# 7. Check Dockerfile entrypoint
echo "7. DOCKERFILE CONFIGURATION"
if [ -f "/workspace/Dockerfile.with-weights" ]; then
    echo "   Dockerfile.with-weights found"
    echo "   ENTRYPOINT line:"
    grep "ENTRYPOINT" /workspace/Dockerfile.with-weights || echo "   (not found)"
else
    echo "   ❌ Dockerfile.with-weights NOT found"
fi
echo ""

# 8. Check recent downloads
echo "8. RECENT DOWNLOAD ACTIVITY"
echo "   Checking for recent .git directories (indicates downloads):"
find /workspace/weights -name ".git" -type d -mtime -1 2>/dev/null | while read gitdir; do
    echo "   ⚠️  Recent download: $(dirname $gitdir)"
done
if [ -z "$(find /workspace/weights -name ".git" -type d -mtime -1 2>/dev/null)" ]; then
    echo "   ✅ No recent downloads detected"
fi
echo ""

# 9. Check disk usage
echo "9. DISK USAGE"
echo "   /workspace total:"
du -sh /workspace 2>/dev/null || echo "   (cannot calculate)"
echo ""
echo "   Breakdown:"
du -sh /workspace/* 2>/dev/null | sort -h | tail -10
echo ""

# 10. Summary and recommendations
echo "=========================================="
echo "SUMMARY"
echo "=========================================="
echo ""

if [ $MODELS_FOUND -eq $MODELS_TOTAL ]; then
    echo "✅ All model weights are present in Docker image"
    echo ""
    echo "If weights are still being downloaded:"
    echo "  1. Check Runpod is using the correct Docker image"
    echo "  2. Verify Docker Command is empty or set to:"
    echo "     /workspace/runpod-docker-entrypoint.sh"
    echo "  3. Check image was built with weights (should be ~65GB)"
    echo ""
else
    echo "❌ Model weights are MISSING from Docker image"
    echo ""
    echo "This means:"
    echo "  - Docker image was not built with weights included"
    echo "  - Need to rebuild using: Dockerfile.with-weights"
    echo ""
    echo "To fix:"
    echo "  1. Build image with weights:"
    echo "     docker build --build-arg HF_TOKEN=\$HF_TOKEN \\"
    echo "       -f Dockerfile.with-weights \\"
    echo "       -t writesimplybcc/stereocrafter-webui:dev ."
    echo ""
    echo "  2. Push to registry:"
    echo "     docker push writesimplybcc/stereocrafter-webui:dev"
    echo ""
    echo "  3. Redeploy on Runpod with new image"
    echo ""
fi

echo "Verification complete!"
echo "Log saved to: /tmp/docker-verification.log"
echo ""
