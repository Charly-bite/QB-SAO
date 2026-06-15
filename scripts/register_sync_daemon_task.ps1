<#
Register a scheduled task that runs the `start_sync_daemon.bat` at user logon.
Run this PowerShell script as Administrator to register the task.
#>
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
$batch = Join-Path $repoRoot "scripts\start_sync_daemon.bat"

Write-Output "Registering scheduled task to run: $batch"

$action = New-ScheduledTaskAction -Execute $batch
$trigger = New-ScheduledTaskTrigger -AtLogOn

Register-ScheduledTask -TaskName "Open-OMS Sync Daemon" -Action $action -Trigger $trigger -RunLevel Highest -Force

Write-Output "Task 'Open-OMS Sync Daemon' registered (runs at user logon)."
