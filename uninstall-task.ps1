$ErrorActionPreference = 'Stop'
Unregister-ScheduledTask -TaskName 'PodcastLocalWorker' -Confirm:$false
