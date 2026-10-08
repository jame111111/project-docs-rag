$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = 'utf-8'
& .\.venv\Scripts\python.exe -m uvicorn app.api:app --app-dir backend --host 127.0.0.1 --port 8000
