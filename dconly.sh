#!/bin/bash
set -e

echo "=== Starting WEBUI-StereoCrafter (DepthCrafter Only) with FileBrowser ==="

DB_FILE="/workspace/.filebrowser/filebrowser.db"

# Source .env file if it exists (for RSA key and other vars)
if [ -f "/workspace/WEBUI-StereoCrafter/.env" ]; then
    echo "Loading environment from .env..."
    # Export all variables from .env
    export $(grep -v '^#' /workspace/WEBUI-StereoCrafter/.env | xargs)
fi

# Install FileBrowser if it's not installed
if ! command -v filebrowser &> /dev/null; then
    echo "FileBrowser not found. Installing..."
    curl -fsSL https://raw.githubusercontent.com/filebrowser/get/master/get.sh | bash
fi

# Initialize FileBrowser if not already done
if [ ! -f "$DB_FILE" ]; then
    echo "Initializing FileBrowser..."
    mkdir -p /workspace/.filebrowser
    filebrowser config init --database "$DB_FILE"
    filebrowser config set --address 0.0.0.0 --database "$DB_FILE"
    filebrowser config set --port 7878 --database "$DB_FILE"
    filebrowser config set --root /workspace/WEBUI-StereoCrafter --database "$DB_FILE"
    filebrowser config set --auth.method=json --database "$DB_FILE"
    filebrowser users add "${FB_USERNAME:-admin}" "${FB_PASSWORD:-adminadmin12}" --perm.admin --database "$DB_FILE"
else
    echo "Using existing FileBrowser configuration..."
fi

# Start FileBrowser in background
echo "Starting FileBrowser on port 7878..."
nohup filebrowser --database "$DB_FILE" &> /filebrowser.log &
echo "FileBrowser started"

# Wait for FileBrowser to initialize
sleep 2

echo "=========================================="
echo "StereoCrafter WEBUI - DepthCrafter Only"
echo "=========================================="
cd /workspace/WEBUI-StereoCrafter
echo "Working directory: $(pwd)"
echo ""

# Check for HF_TOKEN
if [ -z "$HF_TOKEN" ]; then
    echo "ERROR: HF_TOKEN not set!"
    echo "Please set HF_TOKEN in RunPod environment variables"
    exit 1
fi

# Create weights folder if it doesn't exist
mkdir -p weights
cd weights

echo "Checking DepthCrafter model weights..."

# Remove any stale lock files from previous interrupted download attempts
find . -name "*.lock" -type f -delete 2>/dev/null || true

# Configure git credential helper
git config --global credential.helper store

# Login to HuggingFace using Python (this properly sets up credentials)
echo "Logging into Hugging Face..."
python -c "import os; from huggingface_hub import login; login(token=os.environ['HF_TOKEN'].strip(), add_to_git_credential=True)"

# Verify login worked
if [ $? -ne 0 ]; then
    echo "ERROR: HuggingFace login failed"
    exit 1
fi

echo "HuggingFace login successful"

# Download DepthCrafter ONLY
if [ ! -d "DepthCrafter" ]; then
    echo "Downloading DepthCrafter..."
    if command -v hf &> /dev/null; then
        hf download tencent/DepthCrafter --local-dir DepthCrafter
    else
        python -c "from huggingface_hub import snapshot_download; snapshot_download('tencent/DepthCrafter', local_dir='DepthCrafter', local_dir_use_symlinks=False)"
    fi
else
    echo "✅ DepthCrafter weights already downloaded"
fi

cd ..

echo ""
echo "=========================================="
echo "Setup Complete! (DepthCrafter Only)"
echo "=========================================="
echo ""
echo "Starting StereoCrafter WEBUI..."
echo ""

# Start the application
exec python webui.py --share --server-name 0.0.0.0 --server-port 7860
