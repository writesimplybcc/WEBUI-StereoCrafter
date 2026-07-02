@echo off
REM File Browser Setup Script for StereoCrafter Integration (Windows)

echo Setting up File Browser for StereoCrafter...

REM Detect architecture
if "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
    set ARCH=amd64
) else if "%PROCESSOR_ARCHITECTURE%"=="ARM64" (
    set ARCH=arm64
) else (
    set ARCH=386
)

echo Detected architecture: %ARCH%

REM Download File Browser
echo Downloading File Browser...
powershell -Command "& {Invoke-WebRequest -Uri 'https://github.com/filebrowser/filebrowser/releases/latest/download/windows-%ARCH%-filebrowser.zip' -OutFile 'filebrowser.zip'}"

REM Extract
powershell -Command "& {Expand-Archive -Path 'filebrowser.zip' -DestinationPath '.'}"

REM Create config directory
if not exist filebrowser-config mkdir filebrowser-config

REM Create basic configuration
echo { > filebrowser-config.json
echo   "port": 7878, >> filebrowser-config.json
echo   "baseURL": "", >> filebrowser-config.json
echo   "address": "0.0.0.0", >> filebrowser-config.json
echo   "log": "stdout", >> filebrowser-config.json
echo   "database": "./filebrowser.db", >> filebrowser-config.json
echo   "root": ".", >> filebrowser-config.json
echo   "username": "admin", >> filebrowser-config.json
echo   "password": "stereocrafter2026", >> filebrowser-config.json
echo   "permissions": { >> filebrowser-config.json
echo     "admin": true, >> filebrowser-config.json
echo     "execute": true, >> filebrowser-config.json
echo     "create": true, >> filebrowser-config.json
echo     "rename": true, >> filebrowser-config.json
echo     "modify": true, >> filebrowser-config.json
echo     "delete": true, >> filebrowser-config.json
echo     "share": true, >> filebrowser-config.json
echo     "download": true >> filebrowser-config.json
echo   } >> filebrowser-config.json
echo } >> filebrowser-config.json

echo Setup complete!
echo Run: filebrowser.exe --config filebrowser-config.json
echo Access at: http://localhost:7878
echo Username: admin
echo Password: stereocrafter2026 (CHANGE THIS!)
pause