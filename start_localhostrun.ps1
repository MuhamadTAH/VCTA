# ============================================================
#  start_localhostrun.ps1  -  FastAPI + localhost.run tunnel
#  No install needed. Works from any IP. Supports webhooks.
# ============================================================

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

# -- Find a free port starting from 8000 ------------------------
function Get-FreePort($start = 8000) {
    $port = $start
    while ($port -lt 9000) {
        $inUse = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        if (-not $inUse) { return $port }
        Write-Host "  Port $port is busy, trying $($port+1)..." -ForegroundColor DarkGray
        $port++
    }
    return $null
}

Write-Host "[*] Finding a free port..." -ForegroundColor DarkGray
$AppPort = Get-FreePort 8000
if (-not $AppPort) {
    Write-Host "[ERROR] No free port found between 8000-8999!" -ForegroundColor Red
    Pause-Exit 1
}
Write-Host "[+] Using port $AppPort" -ForegroundColor Green

# -- Start FastAPI (uvicorn) in a separate window ---------------
# No --reload to avoid orphaned child processes on Windows
Write-Banner "Starting FastAPI on port $AppPort"
$uvicornCmd = "python -m uvicorn app.main:app --host 0.0.0.0 --port $AppPort"
$uvicornProc = Start-Process `
    -FilePath "powershell.exe" `
    -ArgumentList "-NoExit", "-Command", "Set-Location '$ScriptDir'; $uvicornCmd" `
    -WorkingDirectory $ScriptDir `
    -PassThru

Write-Host "[+] uvicorn PID: $($uvicornProc.Id)" -ForegroundColor Green

# Wait until the port is open (TCP only - no HTTP check, app may be slow to init)
Write-Host "[*] Waiting for FastAPI to bind port $AppPort ..." -ForegroundColor DarkGray
$tries = 0
$ready = $false
do {
    Start-Sleep -Seconds 1
    $tries++
    $listening = Get-NetTCPConnection -LocalPort $AppPort -State Listen -ErrorAction SilentlyContinue
    if ($listening) { $ready = $true }
} while (-not $ready -and $tries -lt 30)

if (-not $ready) {
    Write-Host "[ERROR] FastAPI did not bind port $AppPort within 30s." -ForegroundColor Red
    Write-Host "        Check the FastAPI window for errors." -ForegroundColor Yellow
    Pause-Exit 1
}

Write-Host "[+] FastAPI is listening on port $AppPort" -ForegroundColor Green

# -- Start localhost.run SSH tunnel -----------------------------
Write-Banner "Starting localhost.run tunnel -> localhost:$AppPort"
Write-Host "(First run: type 'yes' if asked to accept the SSH host key)" -ForegroundColor Yellow
Write-Host ""

$logFile = "$env:TEMP\lhr_out.txt"
$errFile = "$env:TEMP\lhr_err.txt"

# Clean up old log files safely
foreach ($f in @($logFile, $errFile)) {
    if (Test-Path $f) {
        try { [System.IO.File]::Delete($f) } catch {}
    }
}

$sshProc = Start-Process `
    -FilePath "ssh" `
    -ArgumentList `
        "-T", `
        "-o", "StrictHostKeyChecking=no", `
        "-o", "ServerAliveInterval=30", `
        "-o", "ServerAliveCountMax=3", `
        "-R", "80:localhost:$AppPort", `
        "nokey@localhost.run" `
    -RedirectStandardOutput $logFile `
    -RedirectStandardError  $errFile `
    -PassThru `
    -WindowStyle Hidden

Write-Host "[+] SSH PID: $($sshProc.Id)" -ForegroundColor Green
Write-Host "[*] Waiting for public URL..." -ForegroundColor DarkGray

# Parse the HTTPS URL from SSH output (check both stdout and stderr)
# localhost.run wraps the URL in ANSI color codes, so strip them first
$publicUrl = $null
$tries = 0
$ansiPattern = [regex]'\x1b\[[0-9;]*[mKHFABCDJsu]'

do {
    Start-Sleep -Seconds 1
    $tries++
    foreach ($f in @($logFile, $errFile)) {
        if (Test-Path $f) {
            try {
                $raw   = [System.IO.File]::ReadAllText($f)
                $clean = $ansiPattern.Replace($raw, '')
                # plain-text mode: 'tunneled with tls termination, https://xxx.lhr.life'
                # or just the bare URL on its own line
                if ($clean -match "(https://[a-zA-Z0-9\-]+\.lhr\.life)") {
                    $publicUrl = $matches[1]
                    break
                }
            } catch {}
        }
    }
} while (-not $publicUrl -and $tries -lt 60)

# -- Display result ---------------------------------------------
if ($publicUrl) {
    Write-Banner "YOUR PUBLIC HTTPS URL"
    Write-Host "  $publicUrl" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Telegram webhook : $publicUrl/webhook" -ForegroundColor Cyan
    Write-Host "  API docs         : $publicUrl/docs" -ForegroundColor Cyan
    Write-Host "  Local app        : http://localhost:$AppPort" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Keep this window open to maintain the tunnel." -ForegroundColor Yellow
    $publicUrl | Set-Clipboard
    Write-Host "[+] URL copied to clipboard!" -ForegroundColor Green
} else {
    Write-Host "[ERROR] Could not get public URL. SSH output:" -ForegroundColor Red
    foreach ($f in @($logFile, $errFile)) {
        if (Test-Path $f) {
            try { Get-Content $f | Select-Object -Last 15 } catch {}
        }
    }
}

# -- Keep window alive ------------------------------------------
Write-Host ""
Write-Host "Press Ctrl+C or close this window to stop the tunnel." -ForegroundColor Gray
$sshProc.WaitForExit()
Write-Host "[!] SSH tunnel disconnected." -ForegroundColor Red
Pause-Exit
