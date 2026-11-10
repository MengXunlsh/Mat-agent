param([ValidateRange(1,65535)][int]$Port = 8790, [switch]$OpenBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$entryPoint = Join-Path $projectRoot 'scripts\run_harness_web.py'
if (-not (Test-Path -LiteralPath $projectPython -PathType Leaf)) {
    throw '项目专用 Python 环境尚未就绪；本入口不会自动安装依赖。'
}
Push-Location -LiteralPath $projectRoot
try {
    $launchArguments = @('-X', 'utf8', '-B', $entryPoint, '--port', $Port)
    if ($OpenBrowser) { $launchArguments += '--open-browser' }
    & $projectPython @launchArguments
    exit $LASTEXITCODE
}
finally { Pop-Location }
