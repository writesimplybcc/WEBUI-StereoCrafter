#!/bin/bash
set -e

echo "=========================================="
echo "Entrypoint - Processing Environment"
echo "=========================================="

# Function to inject RSA public key into .env
inject_rsa_key() {
    local env_file="/workspace/WEBUI-StereoCrafter/.env"
    local rsa_key="${RSA_PUBLIC_KEY:-}"
    
    if [ -n "$rsa_key" ]; then
        echo "RSA public key provided, injecting into .env..."
        
        # Check if RSA_PUBLIC_KEY already exists in .env
        if grep -q "^RSA_PUBLIC_KEY=" "$env_file" 2>/dev/null; then
            echo "Updating existing RSA_PUBLIC_KEY in .env"
            sed -i "s|^RSA_PUBLIC_KEY=.*|RSA_PUBLIC_KEY='$rsa_key'|" "$env_file"
        else
            echo "Adding RSA_PUBLIC_KEY to .env"
            echo "RSA_PUBLIC_KEY='$rsa_key'" >> "$env_file"
        fi
        
        echo "✅ RSA public key injected successfully"
    else
        echo "⚠️  No RSA_PUBLIC_KEY provided, skipping injection"
    fi
}

# Function to inject other optional env vars into .env
inject_env_vars() {
    local env_file="/workspace/WEBUI-StereoCrafter/.env"
    
    # List of optional env vars to inject
    for var in HF_TOKEN FB_USERNAME FB_PASSWORD; do
        local value="${!var}"
        if [ -n "$value" ]; then
            if grep -q "^${var}=$" "$env_file" 2>/dev/null; then
                sed -i "s|^${var}=.*|${var}=$value|" "$env_file"
                echo "Updated $var in .env"
            fi
        fi
    done
}

# Process environment variables
inject_rsa_key
inject_env_vars

echo ""
echo "Starting WEBUI..."
echo ""

# Execute the original CMD
exec "$@"