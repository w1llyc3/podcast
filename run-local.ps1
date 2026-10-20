param(
    [string]$EpisodeId = '',
    [string]$Model = 'large-v3-turbo',
    [int]$MaxItems = 3,
    [switch]$InstallDependencies
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\pip.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
    $InstallDependencies = $true
}
if ($InstallDependencies) {
    & '.\.venv\Scripts\python.exe' -m pip install -r requirements-local.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
}
$workerArgs = @('scripts\local_worker.py', '--output', 'D:\podcast', '--model', $Model, '--max-items', $MaxItems)
if ($EpisodeId) { $workerArgs += @('--episode-id', $EpisodeId) }
& '.\.venv\Scripts\python.exe' @workerArgs
exit $LASTEXITCODE
