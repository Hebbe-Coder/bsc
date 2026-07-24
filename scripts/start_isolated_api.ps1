[CmdletBinding()]
param(
    [int]$Port = 8003
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "workspace virtual environment Python was not found: $python"
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "port $Port is already listening"
}

$startInfo = @{
    FilePath = $python
    ArgumentList = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
    WorkingDirectory = $root
    WindowStyle = "Hidden"
    PassThru = $true
}
$process = Start-Process @startInfo

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/ready" -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
        # The application has not finished binding yet.
    }
}

if (-not $ready) {
    Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    throw "isolated API did not become ready on port $Port"
}

[pscustomobject]@{
    port = $Port
    pid = $process.Id
    ready = $true
} | ConvertTo-Json -Compress
