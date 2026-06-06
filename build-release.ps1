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
    & $venvPython tools\prepare_effect_assets.py
    & $venvPython pig_pet.py --qa-only
    & $venvPython tools\smoke_test.py
    & $venvPython -m PyInstaller --noconfirm --clean pig_pet.spec

    $releaseDir = Join-Path $projectDir 'dist\GifPigDesktopPet'
    $zipPath = Join-Path $projectDir 'dist\GifPigDesktopPet-windows-x64.zip'
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $zipPath
    Write-Host "Release: $releaseDir"
    Write-Host "ZIP: $zipPath"
} finally {
    Pop-Location
}
