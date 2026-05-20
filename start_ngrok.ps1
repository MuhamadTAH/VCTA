# ============================================================
#  start_ngrok.ps1  -  Start FastAPI + ngrok for unified-translator
# ============================================================

$NgrokExe  = "C:\Users\tarqm\AppData\Roaming\npm\node_modules\ngrok\bin\ngrok.exe"
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

# -- Check ngrok exists -----------------------------------------
if (-not (Test-Path $NgrokExe)) {
    Write-Host "[ERROR] ngrok.exe not found at: $NgrokExe" -ForegroundColor Red
    Write-Host "Install it with:  npm install -g ngrok" -ForegroundColor Yellow
    Pause-Exit 1
}

# -- Kill stale processes on the port ---------------------------
Write-Host "[*] Cleaning up old processes..." -ForegroundColor DarkGray
Get-Process -Name "ngrok" -ErrorAction SilentlyContinue | Stop-Process -Force
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

# -- Start ngrok ------------------------------------------------
Write-Banner "Starting ngrok tunnel -> http://localhost:$AppPort"

$ngrokProc = Start-Process `
    -FilePath $NgrokExe `
    -ArgumentList "http", "$AppPort", "--log=stdout", "--log-format=json" `
    -RedirectStandardOutput "$env:TEMP\ngrok_out.txt" `
    -RedirectStandardError  "$env:TEMP\ngrok_err.txt" `
    -PassThru `
    -WindowStyle Hidden

Write-Host "[+] ngrok PID: $($ngrokProc.Id)" -ForegroundColor Green

# -- Poll the ngrok local API for the public URL ----------------
Write-Host "[*] Fetching public URL from ngrok API..." -ForegroundColor DarkGray
$publicUrl = $null
$tries = 0

do {
    Start-Sleep -Seconds 1
    $tries++
    try {
        $resp   = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop
        $tunnel = $resp.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
        if (-not $tunnel) {
            $tunnel = $resp.tunnels | Select-Object -First 1
        }
        $publicUrl = $tunnel.public_url
    } catch {
        # ngrok API not ready yet, keep waiting
    }
} while (-not $publicUrl -and $tries -lt 30)

# -- Display result ---------------------------------------------
if ($publicUrl) {
    Write-Banner "YOUR PUBLIC HTTPS URL"
    Write-Host "  $publicUrl" -ForegroundColor Green
    Write-Host ""
    Write-Host "  ngrok dashboard : http://127.0.0.1:4040" -ForegroundColor Cyan
    Write-Host "  Local app       : http://localhost:$AppPort" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Keep this window open to maintain the tunnel." -ForegroundColor Yellow

    $publicUrl | Set-Clipboard
    Write-Host "[+] URL copied to clipboard!" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Could not get public URL from ngrok." -ForegroundColor Red
    Write-Host ""
    Write-Host "ngrok stdout:" -ForegroundColor DarkGray
    Get-Content "$env:TEMP\ngrok_out.txt" -ErrorAction SilentlyContinue | Select-Object -Last 20
    Write-Host ""
    Write-Host "ngrok stderr:" -ForegroundColor DarkGray
    Get-Content "$env:TEMP\ngrok_err.txt" -ErrorAction SilentlyContinue | Select-Object -Last 20
    Write-Host ""
    Write-Host "Tip: Add your authtoken with:  ngrok config add-authtoken YOUR_TOKEN" -ForegroundColor Yellow
    Write-Host "Get your token at: https://dashboard.ngrok.com/authtokens" -ForegroundColor Yellow
}

# -- Keep window alive ------------------------------------------
Write-Host ""
Write-Host "Press Ctrl+C or close this window to stop ngrok." -ForegroundColor Gray
Write-Host ""

$ngrokProc.WaitForExit()

Write-Host "[!] ngrok exited." -ForegroundColor Red
Pause-Exit
