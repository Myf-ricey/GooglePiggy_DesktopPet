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
$codexCliPath = $null

function Get-CodexCliPath {
    $desktopBinRoot = Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin'
    if (Test-Path -LiteralPath $desktopBinRoot) {
        $desktopCli = Get-ChildItem -LiteralPath $desktopBinRoot -Directory -ErrorAction SilentlyContinue |
            ForEach-Object {
                $candidate = Join-Path $_.FullName 'codex.exe'
                if (Test-Path -LiteralPath $candidate) {
                    Get-Item -LiteralPath $candidate
                }
            } |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1
        if ($null -ne $desktopCli) {
            return $desktopCli.FullName
        }
    }

    $pathCommand = Get-Command codex -ErrorAction SilentlyContinue
    if ($null -ne $pathCommand) {
        return $pathCommand.Source
    }
    return $null
}

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
    $eventTimeouts = [ordered]@{
        SessionStart = 10
        UserPromptSubmit = 10
        PreToolUse = 10
        PostToolUse = 10
        Stop = 10
        PermissionRequest = 600
    }
    foreach ($eventName in $eventTimeouts.Keys) {
        $existing = @($config.hooks.$eventName) | Where-Object { $null -ne $_ }
        $newGroup = [pscustomobject]@{
            hooks = @(
                [pscustomobject]@{
                    type = 'command'
                    command = $command
                    timeout = $eventTimeouts[$eventName]
                }
            )
        }
        $updated = @($newGroup) + @($existing)
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

    $codexCliPath = Get-CodexCliPath
    if (-not [string]::IsNullOrWhiteSpace($codexCliPath)) {
        & $codexCliPath features enable hooks *> $null
    }
}

if (-not $NoStart) {
    Start-Process -FilePath $launchTarget -WorkingDirectory $appDir
}
Write-Host 'GIF Pig Desktop Pet installed.'
if (-not $NoCodexHooks) {
    Write-Host ''
    Write-Host 'Codex hook trust review is still required:'
    if (-not [string]::IsNullOrWhiteSpace($codexCliPath)) {
        Write-Host ('1. Open PowerShell and run: & "{0}"' -f $codexCliPath)
    } else {
        Write-Host '1. Open PowerShell and run: codex'
    }
    Write-Host '2. Enter: /hooks'
    Write-Host '3. Review the six GooglePiggy hooks and trust them. Use Trust all only when every listed hook is known.'
    Write-Host '4. Start a new Codex task or fully restart Codex Desktop. Existing tasks keep their previous hook snapshot.'
    Write-Host 'Restarting alone does not trust new or changed hooks.'
}
