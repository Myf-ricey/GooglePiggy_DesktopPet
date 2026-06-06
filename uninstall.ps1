param()

$ErrorActionPreference = 'Stop'
$appDir = $PSScriptRoot
$autostartKey = 'Software\Microsoft\Windows\CurrentVersion\Run'

$runKey = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($autostartKey, $true)
if ($runKey) {
    try {
        $runKey.DeleteValue('GifPigDesktopPet', $false)
    } finally {
        $runKey.Dispose()
    }
}

$desktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'GIF Pig Desktop Pet.lnk'
Remove-Item -LiteralPath $desktopShortcut -Force -ErrorAction SilentlyContinue

$codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
$hooksPath = Join-Path $codexHome 'hooks.json'
if (Test-Path -LiteralPath $hooksPath) {
    Copy-Item -LiteralPath $hooksPath -Destination ($hooksPath + '.bak-pig-pet-uninstall') -Force
    $config = Get-Content -LiteralPath $hooksPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($config.hooks) {
        foreach ($eventProperty in @($config.hooks.PSObject.Properties)) {
            $groups = @($eventProperty.Value) | Where-Object { $null -ne $_ }
            $keptGroups = @()
            foreach ($group in $groups) {
                $remainingHooks = @(
                    @($group.hooks) | Where-Object {
                        $null -ne $_ -and
                        [string]$_.command -notlike '*codex-pig-hook.ps1*'
                    }
                )
                if ($remainingHooks.Count -gt 0) {
                    $groupCopy = [ordered]@{}
                    foreach ($property in @($group.PSObject.Properties)) {
                        if ($property.Name -ne 'hooks') {
                            $groupCopy[$property.Name] = $property.Value
                        }
                    }
                    $groupCopy['hooks'] = @($remainingHooks)
                    $keptGroups += [pscustomobject]$groupCopy
                }
            }
            $config.hooks.($eventProperty.Name) = @($keptGroups)
        }
        $temporaryHooksPath = $hooksPath + '.tmp'
        $hooksJson = ($config | ConvertTo-Json -Depth 12) + [Environment]::NewLine
        [System.IO.File]::WriteAllText(
            $temporaryHooksPath,
            $hooksJson,
            (New-Object System.Text.UTF8Encoding($false))
        )
        Move-Item -LiteralPath $temporaryHooksPath -Destination $hooksPath -Force
    }
}

Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -in @('pig_pet.exe', 'pythonw.exe') -and
        $_.CommandLine -like ('*' + $appDir + '*')
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host 'Autostart, desktop shortcut, and Codex hooks were removed. Program files remain.'
