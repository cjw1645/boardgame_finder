$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw '먼저 python -m venv .venv 및 의존성 설치를 진행하세요.'
}
Set-Location -LiteralPath $projectRoot
& $pythonPath -m streamlit run service_app/app.py --server.address=127.0.0.1 --server.port=8501 --server.headless=true --browser.gatherUsageStats=false
exit $LASTEXITCODE
