$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName 'PodcastLocalWorker' -ErrorAction SilentlyContinue
if ($task) {
    $task | Select-Object TaskName,State
    Get-ScheduledTaskInfo -TaskName 'PodcastLocalWorker' | Select-Object LastRunTime,LastTaskResult,NextRunTime
} else { Write-Output 'Scheduled task is not installed.' }
if (Test-Path 'D:\podcast\worker-state.json') { Get-Content 'D:\podcast\worker-state.json' }
if (Test-Path 'D:\podcast\logs\worker.log') { Get-Content 'D:\podcast\logs\worker.log' -Tail 15 }
