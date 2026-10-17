param([int]$Port = 0, [string]$Python = "python")
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPython = Join-Path $repoRoot ".benchmark/windows-web-env/Scripts/python.exe"
Push-Location $repoRoot
try {
    if (-not (Test-Path -LiteralPath $envPython)) {
        & $Python -m venv (Join-Path $repoRoot ".benchmark/windows-web-env")
        if ($LASTEXITCODE -ne 0) { throw "Python 3.12+ is required. Pass -Python with its executable path." }
    }
    & $envPython -c "import fastapi, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        & $envPython -m pip install -r web-requirements.txt
        if ($LASTEXITCODE -ne 0) { throw "Web dependency installation failed." }
    }
    # Port 0 = default 8765, or a free port when Windows has reserved it; the server prints the URL.
    $portArgs = @()
    if ($Port -ne 0) { $portArgs = @("--port", $Port) }
    & $envPython -m benchmark_lab @portArgs
    if ($LASTEXITCODE -ne 0) { throw "Demo server exited with an error." }
} finally { Pop-Location }
