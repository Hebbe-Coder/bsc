[CmdletBinding()]
param(
    [string]$HorizonHome = "D:\bsc\horizon",
    [string]$TaskName = "BSC-Horizon-Daily-Radar",
    [string]$At = "07:30",
    [ValidateRange(1, 168)]
    [int]$Hours = 48,
    [ValidateRange(30, 600)]
    [int]$StageTimeoutSeconds = 300,
    [ValidateRange(60, 900)]
    [int]$CycleTimeoutSeconds = 480,
    [switch]$RunAsSystem
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$runner = Join-Path $repoRoot "scripts\run_horizon_pipeline.py"
$python = Join-Path $HorizonHome ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $runner -PathType Leaf)) {
    throw "Horizon producer script was not found."
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Horizon virtual-environment Python was not found."
}

try {
    $time = [DateTime]::ParseExact($At, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
} catch {
    throw "At must use 24-hour HH:mm format."
}

$arguments = "-u `"$runner`" --horizon-home `"$HorizonHome`" --hours $Hours --no-enrich --stage-timeout-seconds $StageTimeoutSeconds --cycle-timeout-seconds $CycleTimeoutSeconds"
$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $repoRoot
$trigger = New-ScheduledTaskTrigger -Daily -At (Get-Date -Hour $time.Hour -Minute $time.Minute -Second 0)
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 15) `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew

if ($RunAsSystem) {
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
} else {
    $principal = New-ScheduledTaskPrincipal `
        -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Limited
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName
$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    task_name = $task.TaskName
    state = $task.State.ToString()
    next_run_time = $info.NextRunTime
    user = $task.Principal.UserId
    logon_type = $task.Principal.LogonType.ToString()
    action = $task.Actions.Execute
    arguments = $task.Actions.Arguments
} | ConvertTo-Json -Compress
