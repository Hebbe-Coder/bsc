[CmdletBinding()]
param(
    [int]$Port = 5185,
    [string]$ApiTarget = "http://127.0.0.1:8002"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$studioEnvPath = Join-Path $root '.env.development.local'

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return ''
    }

    $pattern = '^\s*' + [regex]::Escape($Name) + '\s*=\s*(?<value>.*)$'
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ($line -match $pattern) {
            return $Matches['value'].Trim().Trim('"').Trim("'")
        }
    }
    return ''
}

if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "port $Port is already listening"
}

$localApiKey = Get-EnvValue -Path $studioEnvPath -Name 'BSC_LOCAL_API_KEY'
if ([string]::IsNullOrWhiteSpace($localApiKey)) {
    throw "BSC_LOCAL_API_KEY is missing. Run scripts/provision_local_api_access.ps1 first."
}

# These values are inherited only by Vite. The browser continues to make
# same-origin requests and never receives the API key.
$previousKey = $env:BSC_LOCAL_API_KEY
$previousTarget = $env:BSC_VITE_API_PROXY_TARGET
try {
    $env:BSC_LOCAL_API_KEY = $localApiKey
    $env:BSC_VITE_API_PROXY_TARGET = $ApiTarget
    $startInfo = @{
        FilePath = 'npm.cmd'
        ArgumentList = @('run', 'dev', '--', '--host', '127.0.0.1', '--port', "$Port", '--force')
        WorkingDirectory = $root
        WindowStyle = 'Hidden'
        PassThru = $true
    }
    $process = Start-Process @startInfo
} finally {
    if ($null -eq $previousKey) {
        Remove-Item Env:BSC_LOCAL_API_KEY -ErrorAction SilentlyContinue
    } else {
        $env:BSC_LOCAL_API_KEY = $previousKey
    }
    if ($null -eq $previousTarget) {
        Remove-Item Env:BSC_VITE_API_PROXY_TARGET -ErrorAction SilentlyContinue
    } else {
        $env:BSC_VITE_API_PROXY_TARGET = $previousTarget
    }
}

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
    throw "authorized Studio did not become ready on port $Port"
}

[pscustomobject]@{
    port = $Port
    api_target = $ApiTarget
    pid = $process.Id
    ready = $true
} | ConvertTo-Json -Compress
