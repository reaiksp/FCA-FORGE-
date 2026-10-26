param([switch]$Engine, [switch]$Separator, [switch]$Models, [switch]$All)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
function Run-Native {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $Executable" }
}
function New-PythonEnvironment {
    param([string]$Directory)
    if (-not (Test-Path -LiteralPath "$Directory/Scripts/python.exe")) {
        Run-Native 'py' @('-3.12', '-m', 'venv', $Directory)
    }
}
New-PythonEnvironment '.venv'
Run-Native '.venv/Scripts/python.exe' @('-m', 'pip', 'install', '-r', 'requirements-app.lock')
Run-Native '.venv/Scripts/python.exe' @('-m', 'pip', 'install', '-e', '.', '--no-deps')
if ($Engine -or $All -or $Models) {
    $UpstreamConfig = Get-Content -LiteralPath 'configs/upstream.json' -Raw | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath 'vendor/Applio/.git')) {
        Run-Native 'git' @('clone', $UpstreamConfig.repository, 'vendor/Applio')
    }
    $CurrentRevision = & git -C vendor/Applio rev-parse HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Incomplete Applio checkout; finish or repair it before continuing.' }
    if ($CurrentRevision -ne $UpstreamConfig.commit) {
        $LocalChanges = & git -C vendor/Applio status --porcelain
        if ($LocalChanges) { throw 'Applio has local changes. Preserve them before selecting the pinned version.' }
        Run-Native 'git' @('-C', 'vendor/Applio', 'fetch', 'origin', $UpstreamConfig.commit)
        Run-Native 'git' @('-C', 'vendor/Applio', 'checkout', '--detach', $UpstreamConfig.commit)
    }
    New-PythonEnvironment '.venv-rvc'
    Run-Native '.venv-rvc/Scripts/python.exe' @('-m', 'pip', 'install', 'torch==2.11.0', 'torchaudio==2.11.0', '--index-url', 'https://download.pytorch.org/whl/cu130')
    Run-Native '.venv-rvc/Scripts/python.exe' @('-m', 'pip', 'install', '-r', 'requirements-rvc.lock')
}
if ($Separator -or $All) {
    New-PythonEnvironment '.venv-separator'
    Run-Native '.venv-separator/Scripts/python.exe' @('-m', 'pip', 'install', 'torch==2.11.0', 'torchaudio==2.11.0', 'torchvision==0.26.0', '--index-url', 'https://download.pytorch.org/whl/cu130')
    Run-Native '.venv-separator/Scripts/python.exe' @('-m', 'pip', 'install', '-r', 'requirements-separator.lock')
}
if ($Models -or $All) {
    Run-Native '.venv-rvc/Scripts/python.exe' @('scripts/download_models.py')
}
Run-Native '.venv/Scripts/python.exe' @('scripts/doctor.py')
Write-Host 'Setup complete. Run start.bat to launch Cover Studio.'
