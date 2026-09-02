$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot
if (Test-Path -LiteralPath '.venv\Scripts\python.exe') {
    & '.venv\Scripts\python.exe' 'main.py'
} else {
    python 'main.py'
}

