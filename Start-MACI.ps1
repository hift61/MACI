# Run from PowerShell: .\Start-MACI.ps1
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$maciPython = Join-Path $PSScriptRoot '.venv-gui\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $maciPython)) {
    $maciPython = (Get-Command python -ErrorAction Stop).Source
}
& $maciPython -c 'import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(name) for name in ("pygame", "rich", "openai")) else 1)'
if ($LASTEXITCODE -ne 0) {
    & $maciPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        throw 'Package installation failed. Use Python 3.10 or newer with pip installed.'
    }
}
& $maciPython (Join-Path $PSScriptRoot 'launcher.py')
