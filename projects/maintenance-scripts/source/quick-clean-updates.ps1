<#
.SYNOPSIS
    Quick Windows 10 Update Cleanup Script

.DESCRIPTION
    Cleans up Windows Update temporary files and resets the update cache.
    Run with Administrator privileges.

.NOTES
    Author: Copilot
    Version: 2.0 - Simplified and more reliable
#>

# Verify Admin Privileges
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Warning "Please run this script as Administrator."
    exit 1
}

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "Windows Update Cleanup" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Stop Windows Update Services
Write-Host "Stopping services..." -ForegroundColor Yellow
Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
Stop-Service -Name BITS -Force -ErrorAction SilentlyContinue
Stop-Service -Name cryptsvc -Force -ErrorAction SilentlyContinue
Stop-Service -Name trustedinstaller -Force -ErrorAction SilentlyContinue

# Clear Update Cache Folders
$folders = @(
    "$env:windir\SoftwareDistribution\DataStore",
    "$env:windir\SoftwareDistribution\Download"
)

foreach ($folder in $folders) {
    if (Test-Path $folder) {
        Get-ChildItem -Path $folder -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleared: $folder" -ForegroundColor Green
    }
}

# Reset BITS Queue
Write-Host "Resetting BITS queue..." -ForegroundColor Yellow
$bq = Get-WmiObject -Namespace "root\Microsoft\Windows\BITS" -Class Win32_BitsQueue -ErrorAction SilentlyContinue
if ($bq) {
    $bq | Remove-WmiObject -Force -ErrorAction SilentlyContinue
}

# Reset Winsock
Write-Host "Resetting network..." -ForegroundColor Yellow
netsh winsock reset
netsh int ip reset

# Start Services
Write-Host "Starting services..." -ForegroundColor Yellow
Start-Service -Name wuauserv -ErrorAction SilentlyContinue
Start-Service -Name BITS -ErrorAction SilentlyContinue
Start-Service -Name cryptsvc -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "✓ Cleanup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "Check for updates by pressing Windows Key + R" -ForegroundColor Cyan
Write-Host "Then type: wuauclt /detectnow" -ForegroundColor White