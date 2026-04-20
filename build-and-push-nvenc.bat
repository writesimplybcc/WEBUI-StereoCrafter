@echo off
REM Build and push Docker image with NVENC FFmpeg support
REM Run this from: E:\WEBUI-StereoCrafter

setlocal EnableDelayedExpansion

set IMAGE_NAME=writesimplybcc/stereocrafter-webui
set TAG=nvenc

echo ============================================
echo StereoCrafter WEBUI - NVENC Build
echo ============================================
echo Image: %IMAGE_NAME%:%TAG%
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ERROR: Docker is not running!
    echo Start Docker Desktop and try again.
    pause
    exit /b 1
)

echo Building Docker image...
echo This will take 10-15 minutes (FFmpeg compilation)
echo.

docker build -t %IMAGE_NAME%:%TAG% -f Dockerfile .

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    echo Check the output above for details.
    pause
    exit /b 1
)

echo.
echo ============================================
echo Build Complete!
echo ============================================
echo.

docker images %IMAGE_NAME%:%TAG%

echo.
echo Next steps:
echo 1. Test locally: docker run --gpus all -p 7860:7860 %IMAGE_NAME%:%TAG%
echo 2. Push to Docker Hub: docker push %IMAGE_NAME%:%TAG%
echo 3. Update RunPod to use image: %IMAGE_NAME%:%TAG%
echo.
set /p PUSH="Push to Docker Hub now? (y/n): "
if /i "%PUSH%"=="y" (
    echo Pushing to Docker Hub...
    docker push %IMAGE_NAME%:%TAG%
    if errorlevel 1 (
        echo.
        echo ERROR: Push failed!
        echo Make sure you're logged in: docker login
        pause
        exit /b 1
    )
    echo.
    echo ============================================
    echo Image pushed successfully!
    echo ============================================
    echo.
    echo RunPod Configuration:
    echo   Container Image: %IMAGE_NAME%:%TAG%
    echo   Environment Variables: HF_TOKEN=your_token_here
    echo   Container Disk: 60 GB
    echo   Expose HTTP Ports: 7860
    echo.
) else (
    echo Skipping push.
)

pause
