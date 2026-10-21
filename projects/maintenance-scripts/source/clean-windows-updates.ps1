<#
.SYNOPSIS
    Clean Windows 10 Update Files and Refresh Windows Update

.DESCRIPTION
    Removes old update files, clears the Windows Update cache, and resets the
    Windows Update components to force a fresh update check.

.NOTES
    File:      clean-windows-updates.ps1
    Author:    Copilot
    Requires:  Administrative privileges
    Version:   1.0
#>

# Check for administrator privileges
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Warning "This script requires Administrator privileges. Please run as administrator."
    exit 1
}

Write-Host "Starting Windows Update cleanup..." -ForegroundColor Cyan

# Stop Windows Update service
Write-Host "Stopping Windows Update services..." -ForegroundColor Yellow
Stop-Service -Name wuauserv -Force -ErrorAction SilentlyContinue
Stop-Service -Name BITS -Force -ErrorAction SilentlyContinue
Stop-Service -Name cryptsvc -Force -ErrorAction SilentlyContinue

# Create backup directory
$backupDir = "$env:windir\System32\catroot2\Backup"
if (-not (Test-Path $backupDir)) {
    New-Item -Path $backupDir -ItemType Directory -Force | Out-Null
}

# Move current catroot2 to backup
$catroot2Path = "$env:windir\System32\catroot2"
if (Test-Path $catroot2Path) {
    Move-Item -Path $catroot2Path -Destination "$backupDir\catroot2_old" -Force -ErrorAction SilentlyContinue
    Write-Host "Backup created at: $backupDir\catroot2_old" -ForegroundColor Green
}

# Clear Windows Update client cache
Write-Host "Clearing Windows Update cache..." -ForegroundColor Yellow
$cacheFolders = @(
    "$env:windir\SoftwareDistribution\DataStore",
    "$env:windir\SoftwareDistribution\Download",
    "$env:windir\System32\Tasks\Microsoft\Windows\WindowsUpdate",
    "$env:windir\SoftwareDistribution\Reporting",
    "$env:windir\System32\catroot2"
)

foreach ($folder in $cacheFolders) {
    if (Test-Path $folder) {
        Get-ChildItem -Path $folder -Recurse -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleared: $folder" -ForegroundColor Gray
    }
}

# Reset BITS queue
Write-Host "Resetting BITS queue..." -ForegroundColor Yellow
$bq = Get-WmiObject -Namespace "root\Microsoft\Windows\BITS" -Class Win32_BitsQueue -ErrorAction SilentlyContinue
if ($bq) {
    $bq | Remove-WmiObject -Force -ErrorAction SilentlyContinue
}

# Reset Windows Update agent components
Write-Host "Resetting Windows Update agent..." -ForegroundColor Yellow
$wuaucltPath = "$env:windir\System32\wuauclt.exe"
if (Test-Path $wuaucltPath) {
    & $wuaucltPath /resetwu
}

# Reset Winsock catalog
Write-Host "Resetting Winsock catalog..." -ForegroundColor Yellow
netsh winsock reset
netsh int ip reset

# Start services
Write-Host "Starting Windows Update services..." -ForegroundColor Yellow
Start-Service -Name wuauserv -ErrorAction SilentlyContinue
Start-Service -Name BITS -ErrorAction SilentlyContinue
Start-Service -Name cryptsvc -ErrorAction SilentlyContinue
Start-Service -Name TrustedInstaller -ErrorAction SilentlyContinue

# Set service permissions
$services = @("wuauserv", "BITS", "cryptsvc")
foreach ($service in $services) {
    $sec = Get-Acl "HKLM:\SYSTEM\CurrentControlSet\Services\$service"
    $acl = New-Object System.Security.AccessControl.CommonSecurityDescriptor(1,0)
    $acl.SetSecurityDescriptorInfo(0,1,1)
    Set-Acl -Path "HKLM:\SYSTEM\CurrentControlSet\Services\$service" -AclObject $sec
}

Write-Host "`nCleanup completed successfully!" -ForegroundColor Green
Write-Host "`nYou can now check for updates by running:" -ForegroundColor Cyan
Write-Host "  Settings -> Update & Security -> Windows Update -> Check for updates" -ForegroundColor White
Write-Host "`nOr press Windows Key + R and type:" -ForegroundColor Cyan
Write-Host "  wuauclt /detectnow" -ForegroundColor White