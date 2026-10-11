param(
    [string]$Python = 'py'
)

$ErrorActionPreference = 'Stop'
$projectDir = $PSScriptRoot
$venvDir = Join-Path $projectDir '.venv-build'

Push-Location $projectDir
try {
    if (-not (Test-Path -LiteralPath $venvDir)) {
        & $Python -3 -m venv $venvDir
    }
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Build dependencies failed.' }
    & $venvPython tools\package_app_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Icon packaging failed.' }
    & $venvPython pig_pet.py --qa-only
    if ($LASTEXITCODE -ne 0) { throw 'Manifest validation failed.' }
    & $venvPython tools\smoke_test.py
    if ($LASTEXITCODE -ne 0) { throw 'Legacy geometry validation failed.' }
    & $venvPython tools\test_windows_port.py
    if ($LASTEXITCODE -ne 0) { throw 'Windows port validation failed.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File hooks\codex-pig-hook.ps1 -SelfTest
    if ($LASTEXITCODE -ne 0) {
        throw 'Windows Codex hook self-test failed.'
    }
    & $venvPython -m PyInstaller --noconfirm --clean pig_pet.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    & $venvPython tools\test_windows_runtime.py --exe
    if ($LASTEXITCODE -ne 0) { throw 'Packaged Windows runtime validation failed.' }

    $releaseDir = Join-Path $projectDir 'dist\GifPigDesktopPet'
    $zipPath = Join-Path $projectDir 'dist\GifPigDesktopPet-windows-x64.zip'
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $zipPath
    Write-Host "Release: $releaseDir"
    Write-Host "ZIP: $zipPath"
} finally {
    Pop-Location
}
