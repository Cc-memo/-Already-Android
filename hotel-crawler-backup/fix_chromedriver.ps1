# Fix ChromeDriver on Windows (PowerShell)
# Usage: .\fix_chromedriver.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "ChromeDriver Fix Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Config
$ChromeDriverDir  = Join-Path $PSScriptRoot "bin"
$ChromeDriverPath = Join-Path $ChromeDriverDir "chromedriver.exe"
$TempDir          = $env:TEMP

function Get-VersionFromOutput {
    param(
        [AllowNull()]
        [AllowEmptyString()]
        [string]$Text
    )
    if ([string]::IsNullOrWhiteSpace($Text)) { return $null }
    $m = [regex]::Match($Text, "(\d+\.\d+\.\d+\.\d+)")
    if ($m.Success) { return $m.Groups[1].Value }
    $m = [regex]::Match($Text, "(\d+\.\d+)")
    if ($m.Success) { return $m.Groups[1].Value }
    return $null
}

Write-Host "[1/4] Detect Chrome version..." -ForegroundColor Yellow

$ChromePaths = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

$ChromeExe = $null
foreach ($p in $ChromePaths) {
    if (Test-Path -LiteralPath $p) { $ChromeExe = $p; break }
}

if (-not $ChromeExe) {
    Write-Host "ERROR: Chrome not found." -ForegroundColor Red
    exit 1
}

Write-Host "Found Chrome: $ChromeExe" -ForegroundColor Green
# Prefer file version (more stable across locales), fallback to --version output
$ChromeVersion = $null
try {
    $ChromeVersion = (Get-Item -LiteralPath $ChromeExe).VersionInfo.ProductVersion
} catch {
    $ChromeVersion = $null
}
if (-not $ChromeVersion) {
    $ChromeVersionOutput = & $ChromeExe --version 2>&1
    $ChromeVersion = Get-VersionFromOutput -Text ($ChromeVersionOutput | Out-String)
}
if (-not $ChromeVersion) {
    Write-Host "WARN: Could not parse Chrome version output. Fallback to milestone 131." -ForegroundColor Yellow
    $ChromeMajorVersion = "131"
} else {
    $ChromeMajorVersion = ($ChromeVersion -split "\.")[0]
    Write-Host "Chrome version: $ChromeVersion (milestone $ChromeMajorVersion)" -ForegroundColor Green
}

Write-Host ""
Write-Host "[2/4] Check existing ChromeDriver..." -ForegroundColor Yellow

$NeedDownload = $true
if (Test-Path -LiteralPath $ChromeDriverPath) {
    try {
        $DriverVersionOutput = & $ChromeDriverPath --version 2>&1
        $DriverVersion = Get-VersionFromOutput -Text ($DriverVersionOutput | Out-String)
        if ($DriverVersion) {
            $DriverMajorVersion = ($DriverVersion -split "\.")[0]
            Write-Host "ChromeDriver version: $DriverVersion" -ForegroundColor Green
            if ($DriverMajorVersion -eq $ChromeMajorVersion) {
                Write-Host "OK: Milestone matches. No update needed." -ForegroundColor Green
                $NeedDownload = $false
            } else {
                Write-Host "WARN: Milestone mismatch. Need update." -ForegroundColor Yellow
            }
        } else {
            Write-Host "WARN: Could not parse ChromeDriver version. Will redownload." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "WARN: ChromeDriver exists but cannot run. Will redownload." -ForegroundColor Yellow
    }
} else {
    Write-Host "ChromeDriver not found. Will download." -ForegroundColor Yellow
}

if (-not (Test-Path -LiteralPath $ChromeDriverDir)) {
    New-Item -ItemType Directory -Path $ChromeDriverDir -Force | Out-Null
}

Write-Host ""
Write-Host "[3/4] Download matching ChromeDriver..." -ForegroundColor Yellow

if ($NeedDownload) {
    try {
        $MilestoneUrl = "https://googlechromelabs.github.io/chrome-for-testing/latest-versions-per-milestone-with-downloads.json"
        Write-Host "Fetching milestone metadata..." -ForegroundColor Cyan
        $meta = Invoke-RestMethod -Uri $MilestoneUrl -UseBasicParsing

        $ms = $ChromeMajorVersion
        $milestone = $meta.milestones.$ms
        if (-not $milestone) {
            throw ("Milestone not found in metadata: " + $ms)
        }

        $downloads = $milestone.downloads.chromedriver
        if (-not $downloads) {
            throw "No chromedriver downloads found in metadata."
        }

        $win64 = $downloads | Where-Object { $_.platform -eq "win64" } | Select-Object -First 1
        if (-not $win64) {
            $win64 = $downloads | Where-Object { $_.platform -eq "win32" } | Select-Object -First 1
        }
        if (-not $win64 -or -not $win64.url) {
            throw "Could not find a download URL for win64/win32."
        }

        $downloadUrl = $win64.url
        Write-Host ("Downloading: " + $downloadUrl) -ForegroundColor Cyan

        $zipPath = Join-Path $TempDir "chromedriver.zip"
        Invoke-WebRequest -Uri $downloadUrl -OutFile $zipPath -UseBasicParsing

        $extractPath = Join-Path $TempDir ("chromedriver-extract-" + [Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Path $extractPath -Force | Out-Null
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force

        $extractedDriver = Get-ChildItem -Path $extractPath -Filter "chromedriver.exe" -Recurse | Select-Object -First 1
        if (-not $extractedDriver) {
            throw "chromedriver.exe not found after extracting zip."
        }

        if (Test-Path -LiteralPath $ChromeDriverPath) {
            $backupPath = ($ChromeDriverPath + ".backup." + (Get-Date -Format "yyyyMMddHHmmss"))
            Copy-Item -LiteralPath $ChromeDriverPath -Destination $backupPath -Force
            Write-Host ("Backed up old driver: " + $backupPath) -ForegroundColor Green
        }

        Copy-Item -LiteralPath $extractedDriver.FullName -Destination $ChromeDriverPath -Force
        Write-Host "ChromeDriver updated." -ForegroundColor Green

        Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $extractPath -Recurse -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host ("ERROR: Download/update failed: " + $_.Exception.Message) -ForegroundColor Red
        Write-Host "Manual download page: https://googlechromelabs.github.io/chrome-for-testing/" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "Skip download." -ForegroundColor Green
}

Write-Host ""
Write-Host "[4/4] Verify ChromeDriver..." -ForegroundColor Yellow

if (-not (Test-Path -LiteralPath $ChromeDriverPath)) {
    Write-Host "ERROR: ChromeDriver still missing." -ForegroundColor Red
    exit 1
}

try {
    $DriverVersionOutput = & $ChromeDriverPath --version 2>&1
    Write-Host "OK: Done." -ForegroundColor Green
    Write-Host ("Path: " + $ChromeDriverPath) -ForegroundColor Cyan
    Write-Host ("Version: " + ($DriverVersionOutput | Out-String).Trim()) -ForegroundColor Cyan
} catch {
    Write-Host "WARN: Driver exists but cannot run. Check permissions/AV." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Finished" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan

