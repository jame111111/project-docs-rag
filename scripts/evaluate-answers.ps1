param([ValidateSet('dev', 'final', 'all')][string]$Split = 'dev')
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONPATH = 'backend'
$env:PYTHONIOENCODING = 'utf-8'
& .\.venv\Scripts\python.exe -m evaluation.answer_eval --split $Split
exit $LASTEXITCODE
