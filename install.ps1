param(
    [switch]$NoAutostart,
    [switch]$NoCodexHooks,
    [switch]$NoDesktopShortcut,
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$appDir = $PSScriptRoot
$exePath = Join-Path $appDir 'pig_pet.exe'
$launcherPath = Join-Path $appDir 'start-pig-pet.cmd'
$hookPath = Join-Path $appDir 'hooks\codex-pig-hook.ps1'
$autostartKey = 'Software\Microsoft\Windows\CurrentVersion\Run'
$autostartName = 'GifPigDesktopPet'

if (Test-Path -LiteralPath $exePath) {
    $launchTarget = $exePath
    $autostartCommand = '"{0}"' -f $exePath
} elseif (Test-Path -LiteralPath $launcherPath) {
    $launchTarget = $launcherPath
    $autostartCommand = 'cmd.exe /c ""{0}""' -f $launcherPath
} else {
    throw 'No pig_pet.exe or launcher script was found.'
}

if (-not $NoAutostart) {
    $runKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($autostartKey)
    try {
        $runKey.SetValue($autostartName, $autostartCommand, [Microsoft.Win32.RegistryValueKind]::String)
    } finally {
        $runKey.Dispose()
    }
}

if (-not $NoDesktopShortcut) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutPath = Join-Path $desktop 'GIF Pig Desktop Pet.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launchTarget
    $shortcut.WorkingDirectory = $appDir
    $shortcut.Description = 'GIF Pig Desktop Pet'
    $shortcut.Save()
}

if (-not $NoCodexHooks) {
    if (-not (Test-Path -LiteralPath $hookPath)) {
        throw "Codex hook script is missing: $hookPath"
    }
    $codexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
    New-Item -ItemType Directory -Force -Path $codexHome | Out-Null
    $hooksPath = Join-Path $codexHome 'hooks.json'
    if (Test-Path -LiteralPath $hooksPath) {
        Copy-Item -LiteralPath $hooksPath -Destination ($hooksPath + '.bak-pig-pet') -Force
        $config = Get-Content -LiteralPath $hooksPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        $config = [pscustomobject]@{ hooks = [pscustomobject]@{} }
    }
    if (-not $config.hooks) {
        $config | Add-Member -NotePropertyName hooks -NotePropertyValue ([pscustomobject]@{})
    }

    foreach ($eventProperty in @($config.hooks.PSObject.Properties)) {
        $keptGroups = @()
        foreach ($group in @($eventProperty.Value) | Where-Object { $null -ne $_ }) {
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

    $normalizedHookPath = $hookPath.Replace('\', '/')
    $command = '& "powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "{0}"' -f $normalizedHookPath
    $events = @('SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'Stop')
    foreach ($eventName in $events) {
        $existing = @($config.hooks.$eventName) | Where-Object { $null -ne $_ }
        $newGroup = [pscustomobject]@{
            hooks = @(
                [pscustomobject]@{
                    type = 'command'
                    command = $command
                    timeout = 10
                }
            )
        }
        $updated = @($existing) + $newGroup
        if ($config.hooks.PSObject.Properties.Name -contains $eventName) {
            $config.hooks.$eventName = $updated
        } else {
            $config.hooks | Add-Member -NotePropertyName $eventName -NotePropertyValue $updated
        }
    }
    $temporaryHooksPath = $hooksPath + '.tmp'
    $hooksJson = ($config | ConvertTo-Json -Depth 12) + [Environment]::NewLine
    [System.IO.File]::WriteAllText(
        $temporaryHooksPath,
        $hooksJson,
        (New-Object System.Text.UTF8Encoding($false))
    )
    Move-Item -LiteralPath $temporaryHooksPath -Destination $hooksPath -Force

    if (Get-Command codex -ErrorAction SilentlyContinue) {
        cmd.exe /d /c "codex features enable hooks >nul 2>nul" | Out-Null
    }
}

if (-not $NoStart) {
    Start-Process -FilePath $launchTarget -WorkingDirectory $appDir
}
Write-Host 'GIF Pig Desktop Pet installed. Codex hooks take effect after Codex restarts.'
