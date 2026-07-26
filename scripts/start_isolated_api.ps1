[CmdletBinding()]
param(
    [int]$Port = 8003,
    [string]$DatabaseUrl = $env:BSC_DATABASE_URL
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

# Give a one-off host process the same database target as Docker without
# changing tracked or long-lived environment configuration.
$previousDatabaseUrl = $env:DB_URL
$previousDatabaseType = $env:DB_TYPE
if ($DatabaseUrl) {
    $env:DB_URL = $DatabaseUrl
    $env:DB_TYPE = "postgresql"
}

$startInfo = @{
    FilePath = $python
    ArgumentList = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
    WorkingDirectory = $root
    WindowStyle = "Hidden"
    PassThru = $true
}
try {
    $process = Start-Process @startInfo
} finally {
    if ($null -eq $previousDatabaseUrl) {
        Remove-Item Env:DB_URL -ErrorAction SilentlyContinue
    } else {
        $env:DB_URL = $previousDatabaseUrl
    }
    if ($null -eq $previousDatabaseType) {
        Remove-Item Env:DB_TYPE -ErrorAction SilentlyContinue
    } else {
        $env:DB_TYPE = $previousDatabaseType
    }
}

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
