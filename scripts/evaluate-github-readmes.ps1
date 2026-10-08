param(
    [ValidateSet('all', 'retrieval', 'answers')][string]$Phase = 'all',
    [ValidateSet('all', 'dev', 'final')][string]$Split = 'all',
    [string]$RuntimeRoot = 'data/runtime/github-readmes-v2'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $previousPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $projectRoot 'backend'
    $env:PYTHONUTF8 = '1'
    & .\.venv\Scripts\python.exe -m evaluation.github_readme_eval --phase $Phase --split $Split --runtime-root $RuntimeRoot
    if ($LASTEXITCODE -ne 0) { throw 'README evaluation failed. Check logs; partial results remain in the new run directory.' }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
