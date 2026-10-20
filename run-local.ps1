$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path ".venv")) { py -3 -m venv .venv }
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-local.txt
& ".\.venv\Scripts\python.exe" scripts\local_worker.py --output "$env:USERPROFILE\Podcast Library" --model small --max-items 3
