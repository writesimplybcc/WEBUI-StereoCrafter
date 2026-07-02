#!/bin/bash
# File Browser Setup Script for StereoCrafter Integration

echo "Setting up File Browser for StereoCrafter..."

# Detect OS and architecture
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)

if [[ "$ARCH" == "x86_64" ]]; then
    ARCH="amd64"
elif [[ "$ARCH" == "aarch64" ]]; then
    ARCH="arm64"
fi

echo "Detected: $OS-$ARCH"

# Download latest File Browser release
echo "Downloading File Browser..."
curl -L -o filebrowser.tar.gz "https://github.com/filebrowser/filebrowser/releases/latest/download/${OS}-${ARCH}-filebrowser.tar.gz"

# Extract
tar -xzf filebrowser.tar.gz
chmod +x filebrowser

# Create config directory
mkdir -p filebrowser-config

# Create basic configuration
cat > filebrowser-config.json << 'EOF'
{
  "port": 7878,
  "baseURL": "",
  "address": "0.0.0.0",
  "log": "stdout",
  "database": "./filebrowser.db",
  "root": ".",
  "username": "admin",
  "password": "stereocrafter2026",
  "permissions": {
    "admin": true,
    "execute": true,
    "create": true,
    "rename": true,
    "modify": true,
    "delete": true,
    "share": true,
    "download": true
  }
}
EOF

echo "Setup complete!"
echo "Run: ./filebrowser --config filebrowser-config.json"
echo "Access at: http://localhost:7878"
echo "Username: admin"
echo "Password: stereocrafter2026 (CHANGE THIS!)"