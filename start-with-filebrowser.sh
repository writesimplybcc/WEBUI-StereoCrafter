#!/bin/bash
set -e

echo "=== Starting WEBUI-StereoCrafter with FileBrowser ==="

DB_FILE="/workspace/.filebrowser/filebrowser.db"

# Initialize FileBrowser if not already done
if [ ! -f "$DB_FILE" ]; then
    echo "Initializing FileBrowser..."
    mkdir -p /workspace/.filebrowser
    filebrowser config init --database "$DB_FILE"
    filebrowser config set --address 0.0.0.0 --database "$DB_FILE"
    filebrowser config set --port 8080 --database "$DB_FILE"
    filebrowser config set --root /workspace/StereoCrafter --database "$DB_FILE"
    filebrowser config set --auth.method=json --database "$DB_FILE"
    filebrowser users add "${FB_USERNAME:-admin}" "${FB_PASSWORD:-adminadmin12}" --perm.admin --database "$DB_FILE"
else
    echo "Using existing FileBrowser configuration..."
fi

# Start FileBrowser in background
echo "Starting FileBrowser on port 8080..."
nohup filebrowser --database "$DB_FILE" &> /filebrowser.log &
echo "FileBrowser started"

# Wait for FileBrowser to initialize
sleep 2

# Run the original startup script (downloads weights + starts WebUI)
echo "Starting WEBUI-StereoCrafter..."
cd /workspace/WEBUI-StereoCrafter
exec bash runpod-docker-startup.sh
