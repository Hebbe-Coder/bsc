[CmdletBinding()]
param(
    [switch]$Rotate
)

$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $PSScriptRoot
$backendEnvPath = Join-Path $projectRoot '.env'
$studioEnvPath = Join-Path $projectRoot '.env.development.local'

function New-LocalSecret {
    param([int]$ByteCount = 36)

    $bytes = [byte[]]::new($ByteCount)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    } finally {
        $rng.Dispose()
    }
    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_').TrimEnd('=')
}

function Set-EnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Value
    )

    $lines = if (Test-Path -LiteralPath $Path) {
        [System.IO.File]::ReadAllLines($Path)
    } else {
        [string[]]@()
    }
    $pattern = '^(\s*' + [regex]::Escape($Name) + '\s*=).*?$'
    $found = $false
    $updated = [System.Collections.Generic.List[string]]::new()
    foreach ($line in $lines) {
        if ($line -match $pattern) {
            if (-not $found) {
                $updated.Add("$Name=$Value")
                $found = $true
            }
        } else {
            $updated.Add($line)
        }
    }
    if (-not $found) {
        $updated.Add("$Name=$Value")
    }
    [System.IO.File]::WriteAllLines(
        $Path,
        $updated,
        [System.Text.UTF8Encoding]::new($false)
    )
}

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
            $value = $Matches['value'].Trim()
            # Support copied .env.example comments such as "API_KEY= # add key".
            return ($value -replace '\s+#.*$', '').Trim()
        }
    }
    return ''
}

$apiKey = Get-EnvValue -Path $backendEnvPath -Name 'API_KEY'
if ($Rotate -or [string]::IsNullOrWhiteSpace($apiKey)) {
    $apiKey = 'bsc-local-' + (New-LocalSecret)
}

$sessionSecret = Get-EnvValue -Path $backendEnvPath -Name 'AUTH_SESSION_SECRET'
if ($Rotate -or [string]::IsNullOrWhiteSpace($sessionSecret)) {
    $sessionSecret = New-LocalSecret
}

Set-EnvValue -Path $backendEnvPath -Name 'API_KEY' -Value $apiKey
Set-EnvValue -Path $backendEnvPath -Name 'AUTH_SESSION_SECRET' -Value $sessionSecret
Set-EnvValue -Path $studioEnvPath -Name 'BSC_LOCAL_API_KEY' -Value $apiKey
# This public marker contains no credential. It only lets Studio describe the
# Vite server-side proxy's authenticated state accurately.
Set-EnvValue -Path $studioEnvPath -Name 'VITE_BSC_LOCAL_PROXY_AUTH' -Value 'true'

# Never print a credential. Restart the backend and Vite after this command so
# both processes load the newly aligned local configuration.
[pscustomobject]@{
    backend_env_updated = $true
    studio_proxy_updated = $true
    api_key_rotated = [bool]$Rotate
    restart_required = $true
} | ConvertTo-Json -Compress
