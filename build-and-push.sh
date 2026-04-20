#!/bin/bash
# Build and push Docker image with NVENC FFmpeg support

set -e

IMAGE_NAME="writesimplybcc/stereocrafter-webui"
TAG="nvenc"

echo "============================================"
echo "StereoCrafter WEBUI - NVENC Build"
echo "============================================"
echo "Image: ${IMAGE_NAME}:${TAG}"
echo ""

# Check if Docker is running
docker info > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "ERROR: Docker is not running!"
    echo "Start Docker Desktop and try again."
    exit 1
fi

echo "Building Docker image..."
echo "This will take 10-15 minutes (FFmpeg compilation)"
echo ""

docker build -t ${IMAGE_NAME}:${TAG} -f Dockerfile .

echo ""
echo "============================================"
echo "Build Complete!"
echo "============================================"
echo ""
echo "Image size:"
docker images ${IMAGE_NAME}:${TAG}

echo ""
echo "Next steps:"
echo "1. Test locally: docker run --gpus all -p 7860:7860 ${IMAGE_NAME}:${TAG}"
echo "2. Push to Docker Hub: docker push ${IMAGE_NAME}:${TAG}"
echo "3. Update RunPod to use image: ${IMAGE_NAME}:${TAG}"
echo ""
echo "Push to Docker Hub? (y/n)"
read -r response

if [ "$response" = "y" ]; then
    echo "Pushing to Docker Hub..."
    docker push ${IMAGE_NAME}:${TAG}
    echo ""
    echo "============================================"
    echo "Image pushed successfully!"
    echo "============================================"
    echo ""
    echo "Runpod Configuration:"
    echo "  Container Image: ${IMAGE_NAME}:${TAG}"
    echo "  Environment Variables: HF_TOKEN=your_token_here"
    echo "  Container Disk: 60 GB"
    echo "  Expose HTTP Ports: 7860"
else
    echo "Skipping push."
fi
