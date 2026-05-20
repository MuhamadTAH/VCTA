# ============================================================
#  start_tunnel.ps1  -  Start FastAPI + Cloudflare Tunnel
#  (Use this if ngrok blocks your IP with ERR_NGROK_9040)
# ============================================================

$AppPort   = 8000
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

Set-Location $ScriptDir

function Write-Banner($msg) {
    $line = "=" * 60
    Write-Host ""
    Write-Host $line -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Yellow
    Write-Host $line -ForegroundColor Cyan
    Write-Host ""
}

function Pause-Exit($code = 0) {
    Write-Host ""
    Write-Host "Press any key to exit..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit $code
}

# -- Find cloudflared -------------------------------------------
$cloudflared = Get-Command "cloudflared" -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    # Try common install paths
    $paths = @(
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\cloudflared\cloudflared.exe",
        "C:\cloudflared\cloudflared.exe"
    )
    foreach ($p in $paths) {
        if (Test-Path $p) { $cloudflared = $p; break }
    }
}

if (-not $cloudflared) {
    Write-Host "[ERROR] cloudflared not found." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install it with one of these commands:" -ForegroundColor Yellow
    Write-Host "  winget install Cloudflare.cloudflared" -ForegroundColor Cyan
    Write-Host "  OR download from: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/" -ForegroundColor Cyan
    Pause-Exit 1
} else {
    $cfExe = if ($cloudflared -is [string]) { $cloudflared } else { $cloudflared.Source }
    Write-Host "[+] Found cloudflared: $cfExe" -ForegroundColor Green
}

# -- Kill stale processes on the port ---------------------------
Write-Host "[*] Cleaning up old processes..." -ForegroundColor DarkGray
Get-Process -Name "cloudflared" -ErrorAction SilentlyContinue | Stop-Process -Force
Get-NetTCPConnection -LocalPort $AppPort -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 1

# -- Start FastAPI (uvicorn) in a separate window ---------------
Write-Banner "Starting FastAPI on port $AppPort"
$uvicornArgs = "uvicorn app.main:app --host 0.0.0.0 --port $AppPort --reload"
$uvicornProc = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList "-NoExit", "-Command", $uvicornArgs `
    -WorkingDirectory $ScriptDir `
    -PassThru

Write-Host "[+] uvicorn PID: $($uvicornProc.Id)" -ForegroundColor Green

# Wait until the server is listening
Write-Host "[*] Waiting for FastAPI to be ready..." -ForegroundColor DarkGray
$tries = 0
do {
    Start-Sleep -Seconds 1
    $tries++
    $conn = Test-NetConnection -ComputerName "127.0.0.1" -Port $AppPort -WarningAction SilentlyContinue -ErrorAction SilentlyContinue
} while (-not $conn.TcpTestSucceeded -and $tries -lt 20)

if (-not $conn.TcpTestSucceeded) {
    Write-Host "[ERROR] FastAPI did not start within 20s. Check the other window for errors." -ForegroundColor Red
    Pause-Exit 1
}
Write-Host "[+] FastAPI is up!" -ForegroundColor Green

# -- Start cloudflared tunnel -----------------------------------
Write-Banner "Starting Cloudflare tunnel -> http://localhost:$AppPort"

$logFile = "$env:TEMP\cloudflared_out.txt"
if (Test-Path $logFile) { Remove-Item $logFile -Force }

$cfProc = Start-Process `
    -FilePath $cfExe `
    -ArgumentList "tunnel", "--url", "http://localhost:$AppPort" `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError  "$env:TEMP\cloudflared_err.txt" `
    -PassThru `
    -WindowStyle Hidden

Write-Host "[+] cloudflared PID: $($cfProc.Id)" -ForegroundColor Green
Write-Host "[*] Waiting for public URL..." -ForegroundColor DarkGray

# -- Parse the URL from cloudflared output ----------------------
$publicUrl = $null
$tries = 0

do {
    Start-Sleep -Seconds 1
    $tries++
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        if ($content -match "(https://[a-z0-9\-]+\.trycloudflare\.com)") {
            $publicUrl = $matches[1]
        }
    }
} while (-not $publicUrl -and $tries -lt 40)

# -- Display result ---------------------------------------------
if ($publicUrl) {
    Write-Banner "YOUR PUBLIC HTTPS URL"
    Write-Host "  $publicUrl" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Local app : http://localhost:$AppPort" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Keep this window open to maintain the tunnel." -ForegroundColor Yellow

    $publicUrl | Set-Clipboard
    Write-Host "[+] URL copied to clipboard!" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Could not get public URL from cloudflared." -ForegroundColor Red
    Write-Host ""
    Write-Host "cloudflared output:" -ForegroundColor DarkGray
    Get-Content $logFile -ErrorAction SilentlyContinue | Select-Object -Last 20
    Get-Content "$env:TEMP\cloudflared_err.txt" -ErrorAction SilentlyContinue | Select-Object -Last 20
}

# -- Keep window alive ------------------------------------------
Write-Host ""
Write-Host "Press Ctrl+C or close this window to stop the tunnel." -ForegroundColor Gray
Write-Host ""

$cfProc.WaitForExit()
Write-Host "[!] cloudflared exited." -ForegroundColor Red
Pause-Exit
