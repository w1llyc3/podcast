param([string]$Model = 'large-v3-turbo')
$ErrorActionPreference = 'Stop'
if (-not (Test-Path "$PSScriptRoot\.venv\Scripts\python.exe")) { throw 'Run run-local.ps1 -InstallDependencies first' }
$pwsh = (Get-Command powershell.exe).Source
$arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "{0}\run-local.ps1" -Model "{1}"' -f $PSScriptRoot,$Model
$action = New-ScheduledTaskAction -Execute $pwsh -Argument $arguments -WorkingDirectory $PSScriptRoot
$logon = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 12) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName 'PodcastLocalWorker' -Action $action -Trigger @($logon,$hourly) -Settings $settings -Principal $principal -Description 'Cloud RSS metadata only; local transcription and PDF under D:\podcast' -Force | Select-Object TaskName,State
