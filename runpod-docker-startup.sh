#!/bin/bash
# StereoCrafter WEBUI - Improved Startup Script
# Combines reliable download logic with flexible error handling

echo "=========================================="
echo "StereoCrafter WEBUI - Quick Start"
echo "=========================================="
echo "Working directory: $(pwd)"
echo "Date: $(date)"
echo ""

# Log everything to a file for debugging
exec 1> >(tee -a /tmp/stereocrafter-startup.log)
exec 2>&1

# ============================================================
# INSTALL NVENC-ENABLED FFMPEG (if not already present)
# ============================================================
FFMPEG_HAS_NVENC=false
if command -v ffmpeg &> /dev/null; then
    if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q "h264_nvenc"; then
        FFMPEG_HAS_NVENC=true
        echo "✅ FFmpeg has NVENC support"
    else
        echo "⚠️  System FFmpeg lacks NVENC support"
    fi
fi

if [ "$FFMPEG_HAS_NVENC" = false ]; then
    echo "Installing NVENC-enabled FFmpeg..."
    # Install FFmpeg with NVENC support from conda-forge
    conda install -y -c conda-forge ffmpeg || {
        echo "⚠️  Conda FFmpeg install failed, trying apt..."
        # Fallback: try to install from NVIDIA repo or Ubuntu repos
        apt-get update -qq && apt-get install -y -qq ffmpeg 2>/dev/null || {
            echo "⚠️  FFmpeg installation failed - will use CPU encoding"
        }
    }

    # Verify again
    if command -v ffmpeg &> /dev/null; then
        if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q "h264_nvenc"; then
            FFMPEG_HAS_NVENC=true
            echo "✅ FFmpeg now has NVENC support"
        else
            echo "⚠️  FFmpeg still lacks NVENC support - will use CPU encoding"
        fi
    fi
fi
echo ""

echo "Environment check:"
echo "  Python: $(python --version 2>&1)"
echo "  GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader 2>&1 || echo 'No GPU detected')"
echo ""

# Check for HF_TOKEN (warn but don't exit - allow running with cached models)
HF_LOGIN_SUCCESS=false
if [ -z "$HF_TOKEN" ]; then
    echo "⚠️  WARNING: HF_TOKEN not set!"
    echo "   Models may fail to download if they require authentication"
    echo "   Set HF_TOKEN in RunPod environment variables if needed"
    echo ""
    echo "   Continuing anyway - will try to use cached models..."
    echo ""
else
    echo "✅ HF_TOKEN is set"
    echo ""
    
    # Configure git credentials (keemzin/StereoCrafter approach)
    echo "Configuring HuggingFace authentication..."
    git config --global credential.helper store
    
    # Login via Python huggingface_hub
    python -c "import os; from huggingface_hub import login; login(token=os.environ['HF_TOKEN'].strip(), add_to_git_credential=True)" 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✅ HuggingFace login successful"
        HF_LOGIN_SUCCESS=true
    else
        echo "⚠️  HuggingFace login failed"
        echo "   Model downloads may fail if they require authentication"
    fi
    echo ""
fi

# Navigate to weights folder
cd weights 2>/dev/null || mkdir -p weights && cd weights

echo "=========================================="
echo "Model Weight Verification"
echo "=========================================="

# Check which models are missing (keemzin/StereoCrafter approach - check individually)
SVD_MISSING=false
DEPTH_MISSING=false
STEREO_MISSING=false

if [ ! -d "stable-video-diffusion-img2vid-xt-1-1" ]; then
    echo "⚠️  stable-video-diffusion-img2vid-xt-1-1 not found"
    SVD_MISSING=true
else
    echo "✅ stable-video-diffusion-img2vid-xt-1-1 found ($(du -sh stable-video-diffusion-img2vid-xt-1-1 2>/dev/null | cut -f1))"
fi

if [ ! -d "DepthCrafter" ]; then
    echo "⚠️  DepthCrafter not found"
    DEPTH_MISSING=true
else
    echo "✅ DepthCrafter found ($(du -sh DepthCrafter 2>/dev/null | cut -f1))"
fi

if [ ! -d "StereoCrafter" ]; then
    echo "⚠️  StereoCrafter not found"
    STEREO_MISSING=true
else
    echo "✅ StereoCrafter found ($(du -sh StereoCrafter 2>/dev/null | cut -f1))"
fi

echo ""

# Download missing models (keemzin/StereoCrafter approach - always download what's missing)
if [ "$SVD_MISSING" = false ] && [ "$DEPTH_MISSING" = false ] && [ "$STEREO_MISSING" = false ]; then
    echo "✅ All model weights already downloaded"
    echo "   Total size: $(du -sh . 2>/dev/null | cut -f1)"
else
    echo "=========================================="
    echo "Downloading Missing Models"
    echo "=========================================="
    echo ""
    
    # Function to download a model (tries CLI first, falls back to Python)
    download_model() {
        local repo=$1
        local folder=$2
        
        echo "Downloading $repo → $folder..."
        
        # Try huggingface-cli first (faster, more reliable - keemzin/StereoCrafter approach)
        if command -v huggingface-cli &> /dev/null; then
            echo "  Using huggingface-cli (fast method)..."
            huggingface-cli download "$repo" --local-dir "$folder" 2>&1
            
            if [ $? -eq 0 ]; then
                echo "  ✅ Download complete: $folder ($(du -sh $folder 2>/dev/null | cut -f1))"
                return 0
            else
                echo "  ⚠️  huggingface-cli failed, trying Python fallback..."
            fi
        else
            echo "  huggingface-cli not found, using Python..."
        fi
        
        # Fallback to Python snapshot_download
        python -c "from huggingface_hub import snapshot_download; snapshot_download('$repo', local_dir='$folder', local_dir_use_symlinks=False)" 2>&1
        
        if [ $? -eq 0 ]; then
            echo "  ✅ Download complete: $folder ($(du -sh $folder 2>/dev/null | cut -f1))"
            return 0
        else
            echo "  ❌ Download failed: $folder"
            return 1
        fi
    }
    
    # Download each missing model
    DOWNLOAD_SUCCESS=true
    
    if [ "$SVD_MISSING" = true ]; then
        if ! download_model "stabilityai/stable-video-diffusion-img2vid-xt-1-1" "stable-video-diffusion-img2vid-xt-1-1"; then
            DOWNLOAD_SUCCESS=false
        fi
    fi
    
    if [ "$DEPTH_MISSING" = true ]; then
        if ! download_model "tencent/DepthCrafter" "DepthCrafter"; then
            DOWNLOAD_SUCCESS=false
        fi
    fi
    
    if [ "$STEREO_MISSING" = true ]; then
        if ! download_model "TencentARC/StereoCrafter" "StereoCrafter"; then
            DOWNLOAD_SUCCESS=false
        fi
    fi
    
    echo ""
    if [ "$DOWNLOAD_SUCCESS" = true ]; then
        echo "✅ All model downloads completed successfully"
        echo "   Total size: $(du -sh . 2>/dev/null | cut -f1)"
    else
        echo "⚠️  Some downloads failed"
        echo "   The application may fail to start if models are required"
        echo "   Check HF_TOKEN and try again"
    fi
fi

cd .. || { echo "ERROR: Cannot cd back to root"; exit 1; }

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Startup log saved to: /tmp/stereocrafter-startup.log"
echo ""
echo "Starting StereoCrafter WEBUI..."
echo "  Access URL: http://0.0.0.0:7860"
echo "  Or use the Runpod provided URL"
echo ""

# Start the application (this should keep running)
echo "Launching webui.py..."
python webui.py --share --server-name 0.0.0.0 --server-port 7860
