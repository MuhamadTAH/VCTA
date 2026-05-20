# ============================================================
#  start_localtunnel.ps1  -  FastAPI + localtunnel (npx)
#  Uses your existing Node.js. No IP restrictions. Webhook ok.
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

# -- Kill stale processes on the port ---------------------------
Write-Host "[*] Cleaning up old processes on port $AppPort..." -ForegroundColor DarkGray
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
    Write-Host "[ERROR] FastAPI did not start within 20s. Check the other window." -ForegroundColor Red
    Pause-Exit 1
}
Write-Host "[+] FastAPI is up!" -ForegroundColor Green

# -- Start localtunnel via npx ----------------------------------
Write-Banner "Starting localtunnel -> localhost:$AppPort"

$logFile = "$env:TEMP\lt_out.txt"
if (Test-Path $logFile) { Remove-Item $logFile -Force }

$ltProc = Start-Process `
    -FilePath "cmd.exe" `
    -ArgumentList "/c", "npx -y localtunnel --port $AppPort > `"$logFile`" 2>&1" `
    -PassThru `
    -WindowStyle Hidden

Write-Host "[+] localtunnel PID: $($ltProc.Id)" -ForegroundColor Green
Write-Host "[*] Waiting for public URL (may take 15-30s on first run)..." -ForegroundColor DarkGray

# Parse the URL from output
$publicUrl = $null
$tries = 0

do {
    Start-Sleep -Seconds 2
    $tries++
    if (Test-Path $logFile) {
        $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
        if ($content -match "(https://[a-zA-Z0-9\-]+\.loca\.lt)") {
            $publicUrl = $matches[1]
        }
    }
} while (-not $publicUrl -and $tries -lt 25)

# -- Display result ---------------------------------------------
if ($publicUrl) {
    Write-Banner "YOUR PUBLIC HTTPS URL"
    Write-Host "  $publicUrl" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Webhook example:" -ForegroundColor Cyan
    Write-Host "  $publicUrl/webhook" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  NOTE: First visit in browser may ask for a password." -ForegroundColor Yellow
    Write-Host "  Password is your public IP: $(Invoke-RestMethod -Uri 'https://api.ipify.org' -ErrorAction SilentlyContinue)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Keep this window open to maintain the tunnel." -ForegroundColor Yellow

    $publicUrl | Set-Clipboard
    Write-Host "[+] URL copied to clipboard!" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Could not get public URL." -ForegroundColor Red
    Write-Host ""
    Write-Host "localtunnel output:" -ForegroundColor DarkGray
    Get-Content $logFile -ErrorAction SilentlyContinue | Select-Object -Last 20
}

# -- Keep window alive ------------------------------------------
Write-Host ""
Write-Host "Press Ctrl+C or close this window to stop the tunnel." -ForegroundColor Gray
$ltProc.WaitForExit()
Write-Host "[!] Tunnel exited." -ForegroundColor Red
Pause-Exit
