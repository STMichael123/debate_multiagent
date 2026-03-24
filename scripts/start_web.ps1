 param(
    [int]$Port = 8000,
    [string]$BindHost = "127.0.0.1",
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "未找到虚拟环境 Python：$pythonExe"
}

& (Join-Path $PSScriptRoot "cleanup_web.ps1") -Port $Port

$env:PYTHONPATH = "src"

$arguments = @(
    "-m",
    "uvicorn",
    "debate_agent.app.web:app",
    "--host",
    $BindHost,
    "--port",
    "$Port"
)

if (-not $NoReload) {
    $arguments += "--reload"
}

Write-Host "启动 Web 服务: host=$BindHost port=$Port reload=$(-not $NoReload)"
& $pythonExe @arguments