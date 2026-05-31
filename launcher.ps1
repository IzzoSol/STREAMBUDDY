# STREAMBUDDY Launcher — One-Command Setup + Run
param(
    [switch]$Api,
    [switch]$Docker,
    [switch]$Setup,
    [switch]$Twitch,
    [string]$Channel = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Status($msg) { Write-Host ">>> $msg" -ForegroundColor Cyan }

function Run-Setup {
    Write-Status "Setting up STREAMBUDDY..."
    
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Status "Created .env from .env.example — EDIT IT with your API keys!"
    } else {
        Write-Status ".env exists"
    }

    Write-Status "Installing Python dependencies..."
    pip install -r requirements.txt 2>&1 | Out-Null
    Write-Status "Dependencies installed"
}

function Run-API {
    Write-Status "Starting STREAMBUDDY API on http://localhost:8080"
    Write-Status "OBS overlay: http://localhost:8080/obs/overlay"
    Write-Status "Web UI: http://localhost:8080/api/v1/webui"
    python main.py --api
}

function Run-Docker {
    Write-Status "Building Docker image..."
    docker-compose build
    Write-Status "Starting STREAMBUDDY via Docker..."
    docker-compose up -d
    Write-Status "API running at http://localhost:8080"
    docker-compose logs -f
}

# Main
if ($Setup) {
    Run-Setup
    exit
}

if ($Docker) {
    Run-Docker
    exit
}

if ($Api) {
    if (-not (Test-Path ".env")) { Run-Setup }
    Run-API
    exit
}

# Interactive menu
Run-Setup

Write-Host ""
Write-Host "===================================" -ForegroundColor Magenta
Write-Host "  STREAMBUDDY v2.3" -ForegroundColor Cyan
Write-Host "  AI Game Assistant + Strategy Swarm" -ForegroundColor Cyan
Write-Host "==============================" -ForegroundColor Magenta
Write-Host ""
Write-Host "1) Start API server (port 8080)" -ForegroundColor Yellow
Write-Host "2) Start interactive CLI" -ForegroundColor Yellow
Write-Host "3) Start via Docker" -ForegroundColor Yellow
Write-Host "4) Edit .env config" -ForegroundColor Yellow
Write-Host "5) Exit" -ForegroundColor Yellow
Write-Host ""

$choice = Read-Host "Choose (1-5)"
switch ($choice) {
    "1" { python main.py --api }
    "2" { python main.py }
    "3" { Run-Docker }
    "4" { notepad ".env" }
    "5" { exit }
}
