#!/bin/bash
set -e

echo "=========================================="
echo "Download StereoCrafter Model Weights"
echo "=========================================="
echo ""

WEIGHTS_DIR="${WEIGHTS_DIR:-/workspace/WEBUI-StereoCrafter/weights}"
mkdir -p "$WEIGHTS_DIR"
cd "$WEIGHTS_DIR"

if [ -z "$HF_TOKEN" ]; then
    echo "HF_TOKEN is not set."
    echo "DepthCrafter and StereoCrafter require a Hugging Face token."
    echo "Get one at: https://huggingface.co/settings/tokens"
    echo "Accept model terms at:"
    echo "  - https://huggingface.co/tencent/DepthCrafter"
    echo "  - https://huggingface.co/TencentARC/StereoCrafter"
    echo ""
    read -p "Paste your HF_TOKEN here: " HF_TOKEN
    export HF_TOKEN
    echo ""
fi

if [ -z "$HF_TOKEN" ]; then
    echo "ERROR: HF_TOKEN is still empty. Cannot download gated models."
    exit 1
fi

MODELS=(
    "stabilityai/stable-video-diffusion-img2vid-xt-1-1:stable-video-diffusion-img2vid-xt-1-1"
    "tencent/DepthCrafter:DepthCrafter"
    "TencentARC/StereoCrafter:StereoCrafter"
)

FAILED=0

for entry in "${MODELS[@]}"; do
    REPO="${entry%%:*}"
    FOLDER="${entry##*:}"
    echo "----------------------------------------"
    echo "Downloading: $REPO"
    echo "Target:      $WEIGHTS_DIR/$FOLDER"

    if [ -d "$FOLDER" ] && [ "$(ls -A "$FOLDER" 2>/dev/null)" ]; then
        echo "SKIP: Directory already exists and is not empty. Remove it first to re-download."
        echo "  rm -rf $WEIGHTS_DIR/$FOLDER"
        continue
    fi

    if python -c "
from huggingface_hub import snapshot_download
import os, sys
try:
    snapshot_download(
        '$REPO',
        local_dir='$FOLDER',
        local_dir_use_symlinks=False,
        token=os.environ.get('HF_TOKEN') or None
    )
    print('SUCCESS')
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
"; then
        echo "Done: $FOLDER"
    else
        echo "FAILED to download $REPO"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "=========================================="
if [ "$FAILED" -eq 0 ]; then
    echo "All weights downloaded successfully."
else
    echo "Completed with $FAILED failure(s). Check output above."
    exit 1
fi
echo "=========================================="
