[CmdletBinding()]
param(
    [int]$Port = 5180,
    [string]$ApiTarget = "http://127.0.0.1:8003"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "port $Port is already listening"
}

# vite.config.ts gives this process-level target precedence over .env defaults.
$command = "set `"VITE_API_PROXY_TARGET=$ApiTarget`" && call npm.cmd run dev -- --host 127.0.0.1 --port $Port"
$startInfo = @{
    FilePath = $env:ComSpec
    ArgumentList = @("/c", $command)
    WorkingDirectory = $root
    WindowStyle = "Hidden"
    PassThru = $true
}
$process = Start-Process @startInfo

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/" -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # Vite has not finished binding yet.
    }
}

if (-not $ready) {
    Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    throw "isolated Studio did not become ready on port $Port"
}

[pscustomobject]@{
    port = $Port
    api_target = $ApiTarget
    pid = $process.Id
    ready = $true
} | ConvertTo-Json -Compress
