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
    & $venvPython -m unittest tools.test_handoff_053 -q
    if ($LASTEXITCODE -ne 0) { throw 'Handoff validation failed.' }
    & $venvPython -m unittest tools.test_appearance tools.test_appearance_stability tools.test_autostart -q
    if ($LASTEXITCODE -ne 0) { throw 'Appearance validation failed.' }
    & $venvPython tools\test_windows_port.py
    if ($LASTEXITCODE -ne 0) { throw 'Windows port validation failed.' }
    & $venvPython tools\test_animation_performance.py
    if ($LASTEXITCODE -ne 0) { throw 'Animation pixel, clock and observer validation failed.' }
    & $venvPython tools\test_internal_memory.py
    if ($LASTEXITCODE -ne 0) { throw 'Internal session validation failed.' }
    & $venvPython tools\test_compressed_rollout.py
    if ($LASTEXITCODE -ne 0) { throw 'Compressed rollout validation failed.' }
    & $venvPython tools\test_state_audit.py
    if ($LASTEXITCODE -ne 0) { throw 'State audit validation failed.' }
    & $venvPython tools\test_windows_update.py
    if ($LASTEXITCODE -ne 0) { throw 'Windows updater validation failed.' }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File hooks\codex-pig-hook.ps1 -SelfTest
    if ($LASTEXITCODE -ne 0) {
        throw 'Windows Codex hook self-test failed.'
    }
    & $venvPython -m PyInstaller --noconfirm --clean pig_pet.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    & $venvPython tools\test_windows_runtime.py --exe
    if ($LASTEXITCODE -ne 0) { throw 'Packaged Windows runtime validation failed.' }
    & $venvPython tools\test_state_runtime.py (Join-Path $projectDir 'dist\GifPigDesktopPet\pig_pet.exe')
    if ($LASTEXITCODE -ne 0) { throw 'Frozen state observer validation failed.' }

    $releaseDir = Join-Path $projectDir 'dist\GifPigDesktopPet'
    & $venvPython tools\prepare_windows_update.py $releaseDir --version 0.5.7
    if ($LASTEXITCODE -ne 0) { throw 'Update manifest generation failed.' }
    $zipPath = Join-Path $projectDir 'dist\GooglePiggy-0.5.7-windows-x64.zip'
    Remove-Item -LiteralPath $zipPath -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $zipPath
    Write-Host "Release: $releaseDir"
    Write-Host "ZIP: $zipPath"
} finally {
    Pop-Location
}
