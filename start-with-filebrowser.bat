@echo off
REM StereoCrafter with File Browser Launcher

echo Starting StereoCrafter with File Browser...

REM Check if Docker is available
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Docker is not installed. Please install Docker first.
    pause
    exit /b 1
)

REM Check if docker-compose is available
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo docker-compose is not available. Please install docker-compose.
    pause
    exit /b 1
)

REM Start services
echo Starting services with docker-compose...
docker-compose up -d

echo.
echo Services started!
echo - StereoCrafter WebUI: http://localhost:7860
echo - File Browser: http://localhost:8080
echo.
echo Press Ctrl+C to stop services...
docker-compose logs -f