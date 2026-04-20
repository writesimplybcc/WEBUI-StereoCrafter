# PowerShell script to fix Windows line endings (CRLF) to Unix line endings (LF)
# Run this on Windows if you get "$'\r': command not found" errors

Write-Host "Fixing line endings for shell scripts..." -ForegroundColor Cyan

$files = Get-ChildItem -Filter "*.sh"

foreach ($file in $files) {
    Write-Host "  Fixing: $($file.Name)" -ForegroundColor Yellow
    
    # Read file content
    $content = Get-Content $file.FullName -Raw
    
    # Replace CRLF with LF
    $content = $content -replace "`r`n", "`n"
    
    # Write back without adding extra newline
    [System.IO.File]::WriteAllText($file.FullName, $content)
}

Write-Host ""
Write-Host "Done! Line endings fixed." -ForegroundColor Green
Write-Host ""
Write-Host "You can now run your startup scripts on Linux/Runpod:" -ForegroundColor Cyan
Write-Host "  bash runpod-docker-startup.sh"
Write-Host "  bash runpod-startup.sh"
