# Build and push Docker image with NVENC FFmpeg support
# Run this from: E:\WEBUI-StereoCrafter
# Usage: .\build-and-push-nvenc.ps1

$ErrorActionPreference = "Stop"

$IMAGE_NAME = "writesimplybcc/stereocrafter-webui"
$TAG = "nvenc"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "StereoCrafter WEBUI - NVENC Build" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Image: ${IMAGE_NAME}:${TAG}"
Write-Host ""

# Check if Docker is running
try {
    docker info | Out-Null
} catch {
    Write-Host "ERROR: Docker is not running!" -ForegroundColor Red
    Write-Host "Start Docker Desktop and try again." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Building Docker image..." -ForegroundColor Yellow
Write-Host "This will take 10-15 minutes (FFmpeg compilation)" -ForegroundColor Yellow
Write-Host ""

docker build -t "${IMAGE_NAME}:${TAG}" -f Dockerfile .

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Build failed!" -ForegroundColor Red
    Write-Host "Check the output above for details." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "Build Complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""

docker images "${IMAGE_NAME}:${TAG}"

Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Test locally: docker run --gpus all -p 7860:7860 ${IMAGE_NAME}:${TAG}"
Write-Host "2. Push to Docker Hub: docker push ${IMAGE_NAME}:${TAG}"
Write-Host "3. Update RunPod to use image: ${IMAGE_NAME}:${TAG}"
Write-Host ""

$PUSH = Read-Host "Push to Docker Hub now? (y/n)"
if ($PUSH -eq "y") {
    Write-Host "Pushing to Docker Hub..." -ForegroundColor Yellow
    docker push "${IMAGE_NAME}:${TAG}"
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "ERROR: Push failed!" -ForegroundColor Red
        Write-Host "Make sure you're logged in: docker login" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Green
    Write-Host "Image pushed successfully!" -ForegroundColor Green
    Write-Host "============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "RunPod Configuration:" -ForegroundColor Cyan
    Write-Host "  Container Image: ${IMAGE_NAME}:${TAG}"
    Write-Host "  Environment Variables: HF_TOKEN=your_token_here"
    Write-Host "  Container Disk: 60 GB"
    Write-Host "  Expose HTTP Ports: 7860"
    Write-Host ""
} else {
    Write-Host "Skipping push." -ForegroundColor Yellow
}

Read-Host "Press Enter to exit"
