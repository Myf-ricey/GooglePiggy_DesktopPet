param(
    [switch]$NoAutostart,
    [switch]$NoCodexHooks,
    [switch]$NoDesktopShortcut,
    [switch]$NoEnableHookFeature,
    [switch]$NoStart
)

$ErrorActionPreference = 'Stop'
$installMutex = New-Object Threading.Mutex($false, 'Local\GooglePiggy-Install')
if (-not $installMutex.WaitOne(10000)) { throw 'Another GooglePiggy installer is running.' }
try {
$appDir = $PSScriptRoot
$exePath = Join-Path $appDir 'pig_pet.exe'
$launcherPath = Join-Path $appDir 'start-pig-pet.cmd'
$hookPath = Join-Path $appDir 'hooks\codex-pig-hook.ps1'
$autostartKey = 'Software\Microsoft\Windows\CurrentVersion\Run'
$autostartName = 'GifPigDesktopPet'
$codexCliPath = $null

function Test-GooglePiggyHookCommand {
    param([string]$Command)
    $match = [regex]::Match($Command, '(?i)-File\s+"([^"]+)"')
    if (-not $match.Success) { return $false }
    $path = $match.Groups[1].Value.Replace('/', '\')
    if ([IO.Path]::GetFileName($path) -ne 'codex-pig-hook.ps1') { return $false }
    if ($path -eq $hookPath) { return $true }
    if (-not (Test-Path -LiteralPath $path)) { return $false }
    $content = [IO.File]::ReadAllText($path)
    return $content.Contains('function Invoke-PigPermissionRequest') -and $content.Contains('GifPigDesktopPet')
}

function Get-HooksHash {
    param([string]$Path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash([IO.File]::ReadAllBytes($Path))) }
    finally { $sha.Dispose() }
}

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

# Read the old local preference only for migration; Windows' system registry
# provider is authoritative for the effective Run entry and startup switch.
$preferencePath = 'Software\GooglePiggy\Preferences'
$legacyPreference = $null
$oldPreference = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($preferencePath)
if ($oldPreference) {
    try { $legacyPreference = $oldPreference.GetValue('AutostartEnabled', $null) }
    finally { $oldPreference.Dispose() }
}
. (Join-Path $appDir 'tools\autostart_registry.ps1')
$startupRequest = @{
    action = $(if ($NoAutostart) { 'disable' } else { 'reconcile' })
    command = $autostartCommand
    target = $launchTarget
    run_key = $autostartKey
    preference_key = $preferencePath
    legacy_preference = $legacyPreference
    previous_install = (Test-Path -LiteralPath (Join-Path $env:LOCALAPPDATA 'GifPigDesktopPet\pig-heartbeat.json'))
}
$startupStatus = Invoke-GooglePiggyAutostart $startupRequest
Write-Host ('Windows startup verified: ' + $startupStatus.enabled)

if (-not $NoDesktopShortcut) {
    $desktop = [Environment]::GetFolderPath('Desktop')
    $shortcutName = ([string][char]0x732A) + [char]0x732A + [char]0x684C + [char]0x5BA0 + '.lnk'
    $shortcutPath = Join-Path $desktop $shortcutName
    $shell = New-Object -ComObject WScript.Shell
    $archiveRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'GifPigDesktopPet\shortcut-backups'))
    foreach ($linkFile in @(Get-ChildItem -LiteralPath $desktop -Filter '*.lnk' -File)) {
        if ($linkFile.FullName -eq $shortcutPath) { continue }
        $oldLink = $shell.CreateShortcut($linkFile.FullName)
        if ([string]::IsNullOrWhiteSpace($oldLink.TargetPath)) { continue }
        $targetName = [IO.Path]::GetFileName($oldLink.TargetPath)
        if ($targetName -notin @('pig_pet.exe', 'start-pig-pet.cmd')) { continue }
        $targetDirectory = [IO.Path]::GetDirectoryName($oldLink.TargetPath)
        if (-not $targetDirectory -or -not (Test-Path -LiteralPath (Join-Path $targetDirectory 'hooks\codex-pig-hook.ps1'))) { continue }
        $archivePath = [IO.Path]::GetFullPath((Join-Path $archiveRoot (([Guid]::NewGuid().ToString('N')) + '-' + $linkFile.Name)))
        if (-not $archivePath.StartsWith($archiveRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid shortcut archive path.' }
        New-Item -ItemType Directory -Force -Path $archiveRoot | Out-Null
        Move-Item -LiteralPath $linkFile.FullName -Destination $archivePath
        Write-Host ('Archived old shortcut: ' + $linkFile.Name)
    }
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $launchTarget
    $shortcut.WorkingDirectory = $appDir
    $shortcut.Description = 'GooglePiggy - current installation: ' + $appDir
    $iconPath = Join-Path $appDir 'assets\icons\piggy-idle-v2.ico'
    if (Test-Path -LiteralPath $iconPath) { $shortcut.IconLocation = $iconPath + ',0' }
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
        $originalHooksHash = Get-HooksHash -Path $hooksPath
        Copy-Item -LiteralPath $hooksPath -Destination ($hooksPath + '.bak-pig-pet-' + [DateTime]::Now.ToString('yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N'))
        $config = Get-Content -LiteralPath $hooksPath -Raw -Encoding UTF8 | ConvertFrom-Json
    } else {
        $originalHooksHash = ''
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
                    -not (Test-GooglePiggyHookCommand -Command ([string]$_.command))
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
        Interrupt = 3
        PreCompact = 10
        PostCompact = 10
        SubagentStart = 10
        SubagentStop = 10
        SessionEnd = 10
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
    $temporaryHooksPath = $hooksPath + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $hooksJson = ($config | ConvertTo-Json -Depth 12) + [Environment]::NewLine
    [System.IO.File]::WriteAllText(
        $temporaryHooksPath,
        $hooksJson,
        (New-Object System.Text.UTF8Encoding($false))
    )
    $currentHooksHash = if (Test-Path -LiteralPath $hooksPath) { Get-HooksHash -Path $hooksPath } else { '' }
    if ($originalHooksHash -ne $currentHooksHash) {
        Remove-Item -LiteralPath $temporaryHooksPath
        throw 'Codex hooks changed during installation. Run the installer again to preserve those changes.'
    }
    if (Test-Path -LiteralPath $hooksPath) { [IO.File]::Replace($temporaryHooksPath, $hooksPath, [NullString]::Value) }
    else { [IO.File]::Move($temporaryHooksPath, $hooksPath) }

    $codexCliPath = Get-CodexCliPath
    if (-not $NoEnableHookFeature -and -not [string]::IsNullOrWhiteSpace($codexCliPath)) {
        try { & $codexCliPath features enable hooks *> $null }
        catch { Write-Host 'Hooks were registered. Enable the hooks feature manually if your Codex client requires it.' }
    }
}

if (-not $NoStart) {
    Start-Process -FilePath $launchTarget -WorkingDirectory $appDir -WindowStyle Hidden
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
    Write-Host '3. Review the twelve GooglePiggy hooks and trust them. Use Trust all only when every listed hook is known.'
    Write-Host '4. Start a new Codex task or fully restart Codex Desktop. Existing tasks keep their previous hook snapshot.'
    Write-Host 'Restarting alone does not trust new or changed hooks.'
}
} finally {
    $installMutex.ReleaseMutex()
    $installMutex.Dispose()
}
