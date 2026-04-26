#!/bin/bash
# File Browser Pre-Initialization Script for Cloud Deployment
# This script creates the database and user before deployment

echo "Pre-initializing File Browser for cloud deployment..."

# Set your credentials here (change these!)
FB_USERNAME="${FB_USERNAME:-stereocrafter}"
FB_PASSWORD="${FB_PASSWORD:-CHANGE_THIS_PASSWORD_BEFORE_DEPLOYMENT_12345}"

# Create database directory
mkdir -p ./filebrowser-data

# Initialize database with user
echo "Creating File Browser database with user: $FB_USERNAME"

# Use filebrowser to create the initial database
./filebrowser users add "$FB_USERNAME" "$FB_PASSWORD" --perm.admin --database ./filebrowser-data/filebrowser.db

echo "✅ File Browser pre-initialized!"
echo "Username: $FB_USERNAME"
echo "Database: ./filebrowser-data/filebrowser.db"
echo ""
echo "To use in Docker, mount the database:"
echo "volumes:"
echo "  - ./filebrowser-data/filebrowser.db:/database/filebrowser.db"