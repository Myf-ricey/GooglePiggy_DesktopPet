param()

$ErrorActionPreference = 'Stop'

function Install-TaskCompleteWatcher {
    param([string]$StateDirectory)

    $watcherPath = Join-Path $StateDirectory 'codex-task-complete-watch.ps1'
    $watcherSource = @'
param(
    [string]$SessionId,
    [string]$TurnId,
    [string]$StateDirectory
)

$ErrorActionPreference = 'SilentlyContinue'

function Get-BridgeTimestamp {
    [DateTimeOffset]::UtcNow.ToString('o')
}

function New-BridgeToken {
    ('{0}-{1}' -f [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(), [Guid]::NewGuid().ToString('N'))
}

function Append-BridgeLog {
    param([object]$Entry)

    try {
        $eventLogPath = Join-Path $StateDirectory 'codex-hook-events.jsonl'
        [System.IO.File]::AppendAllText(
            $eventLogPath,
            (($Entry | ConvertTo-Json -Compress) + [Environment]::NewLine),
            (New-Object System.Text.UTF8Encoding($false))
        )
    } catch {
    }
}

function Read-BridgeState {
    try {
        $statePath = Join-Path $StateDirectory 'codex-status.json'
        if (-not (Test-Path -LiteralPath $statePath)) {
            return $null
        }
        return Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Find-CodexSessionFile {
    if ([string]::IsNullOrWhiteSpace($SessionId)) {
        return $null
    }

    $codexHome = if ($env:CODEX_HOME) {
        $env:CODEX_HOME
    } else {
        Join-Path $HOME '.codex'
    }
    $sessionsDirectory = Join-Path $codexHome 'sessions'
    if (-not (Test-Path -LiteralPath $sessionsDirectory)) {
        return $null
    }

    try {
        return Get-ChildItem -LiteralPath $sessionsDirectory -Recurse -Filter ("*{0}*.jsonl" -f $SessionId) -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    } catch {
        return $null
    }
}

function Test-TaskComplete {
    param([string]$SessionFile)

    if ([string]::IsNullOrWhiteSpace($SessionFile) -or -not (Test-Path -LiteralPath $SessionFile)) {
        return $false
    }

    try {
        foreach ($line in (Get-Content -LiteralPath $SessionFile -Tail 1000 -Encoding UTF8)) {
            try {
                $record = $line | ConvertFrom-Json
            } catch {
                continue
            }

            if ([string]$record.type -ne 'event_msg') {
                continue
            }
            if (-not $record.payload) {
                continue
            }
            if ([string]$record.payload.type -eq 'task_complete' -and [string]$record.payload.turn_id -eq $TurnId) {
                return $true
            }
        }
    } catch {
        return $false
    }

    return $false
}

function Write-TaskCompleteSuccess {
    $statePath = Join-Path $StateDirectory 'codex-status.json'
    $temporaryPath = Join-Path $StateDirectory 'codex-status.json.tmp'
    $updatedAt = Get-BridgeTimestamp
    $state = [ordered]@{
        status = 'success'
        token = New-BridgeToken
        updated_at = $updatedAt
        source = 'codex-task-complete-watch'
        event = 'TaskCompleteFallback'
        message = ''
        session_id = $SessionId
        turn_id = $TurnId
    }

    try {
        [System.IO.File]::WriteAllText(
            $temporaryPath,
            (($state | ConvertTo-Json) + [Environment]::NewLine),
            (New-Object System.Text.UTF8Encoding($false))
        )
        Move-Item -LiteralPath $temporaryPath -Destination $statePath -Force
        Append-BridgeLog ([ordered]@{
            updated_at = $updatedAt
            status = 'success'
            event = 'TaskCompleteFallback'
            session_id = $SessionId
            turn_id = $TurnId
        })
    } catch {
    }
}

if ([string]::IsNullOrWhiteSpace($SessionId) -or [string]::IsNullOrWhiteSpace($TurnId) -or [string]::IsNullOrWhiteSpace($StateDirectory)) {
    return
}

$deadline = (Get-Date).AddMinutes(10)
$sessionFile = $null

while ((Get-Date) -lt $deadline) {
    $currentState = Read-BridgeState
    if ($null -ne $currentState) {
        if ([string]$currentState.status -ne 'thinking') {
            return
        }
        if ([string]$currentState.session_id -ne $SessionId -or [string]$currentState.turn_id -ne $TurnId) {
            return
        }
    }

    if ([string]::IsNullOrWhiteSpace($sessionFile) -or -not (Test-Path -LiteralPath $sessionFile)) {
        $sessionFile = Find-CodexSessionFile
    }

    if (Test-TaskComplete -SessionFile $sessionFile) {
        $currentState = Read-BridgeState
        if ($null -eq $currentState -or (
            [string]$currentState.status -eq 'thinking' -and
            [string]$currentState.session_id -eq $SessionId -and
            [string]$currentState.turn_id -eq $TurnId
        )) {
            Write-TaskCompleteSuccess
        }
        return
    }

    Start-Sleep -Milliseconds 750
}

Append-BridgeLog ([ordered]@{
    updated_at = Get-BridgeTimestamp
    status = 'thinking'
    event = 'TaskCompleteFallbackTimeout'
    session_id = $SessionId
    turn_id = $TurnId
})
'@

    try {
        [System.IO.File]::WriteAllText(
            $watcherPath,
            $watcherSource,
            (New-Object System.Text.UTF8Encoding($false))
        )
    } catch {
    }

    return $watcherPath
}

function Start-TaskCompleteWatcher {
    param(
        [string]$SessionId,
        [string]$TurnId,
        [string]$StateDirectory
    )

    if ([string]::IsNullOrWhiteSpace($SessionId) -or [string]::IsNullOrWhiteSpace($TurnId)) {
        return
    }

    try {
        $watcherPath = Install-TaskCompleteWatcher -StateDirectory $StateDirectory
        if ([string]::IsNullOrWhiteSpace($watcherPath) -or -not (Test-Path -LiteralPath $watcherPath)) {
            return
        }

        $arguments = @(
            '-NoProfile',
            '-ExecutionPolicy',
            'Bypass',
            '-File',
            ('"{0}"' -f $watcherPath),
            '-SessionId',
            ('"{0}"' -f $SessionId),
            '-TurnId',
            ('"{0}"' -f $TurnId),
            '-StateDirectory',
            ('"{0}"' -f $StateDirectory)
        )
        Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList $arguments | Out-Null
    } catch {
    }
}

try {
    $raw = [Console]::In.ReadToEnd()
    $payload = $null
    if (-not [string]::IsNullOrWhiteSpace($raw)) {
        $payload = $raw | ConvertFrom-Json
    }

    $eventName = if ($payload -and $payload.hook_event_name) {
        [string]$payload.hook_event_name
    } else {
        ''
    }

    $status = switch ($eventName) {
        'SessionStart' { 'idle' }
        'UserPromptSubmit' { 'thinking' }
        'PreToolUse' { 'thinking' }
        'PostToolUse' { 'thinking' }
        'Stop' { 'success' }
        default { $null }
    }

    if ($status) {
        $stateDirectory = Join-Path $env:LOCALAPPDATA 'GifPigDesktopPet'
        $statePath = Join-Path $stateDirectory 'codex-status.json'
        $temporaryPath = Join-Path $stateDirectory 'codex-status.json.tmp'
        $eventLogPath = Join-Path $stateDirectory 'codex-hook-events.jsonl'
        New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null

        $sessionId = if ($payload -and $payload.session_id) {
            [string]$payload.session_id
        } else {
            ''
        }
        $turnId = if ($payload -and $payload.turn_id) {
            [string]$payload.turn_id
        } else {
            ''
        }
        if ($eventName -eq 'PostToolUse' -and (Test-Path -LiteralPath $statePath)) {
            try {
                $existingState = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
                $existingTime = [DateTimeOffset]::Parse([string]$existingState.updated_at)
                $ageSeconds = ([DateTimeOffset]::UtcNow - $existingTime.ToUniversalTime()).TotalSeconds
                if ([string]$existingState.status -eq 'success' -and $ageSeconds -ge 0 -and $ageSeconds -le 3) {
                    $ignoredState = [ordered]@{
                        updated_at = [DateTimeOffset]::UtcNow.ToString('o')
                        status = $status
                        event = $eventName
                        session_id = $sessionId
                        turn_id = $turnId
                        ignored = $true
                        reason = 'recent-success'
                    }
                    [System.IO.File]::AppendAllText(
                        $eventLogPath,
                        (($ignoredState | ConvertTo-Json -Compress) + [Environment]::NewLine),
                        (New-Object System.Text.UTF8Encoding($false))
                    )
                    Write-Output '{}'
                    return
                }
            } catch {
                # Fall through to the normal status write.
            }
        }
        $state = [ordered]@{
            status = $status
            token = ('{0}-{1}' -f [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(), [Guid]::NewGuid().ToString('N'))
            updated_at = [DateTimeOffset]::UtcNow.ToString('o')
            source = 'codex-hook'
            event = $eventName
            message = ''
            session_id = $sessionId
            turn_id = $turnId
        }
        $json = ($state | ConvertTo-Json) + [Environment]::NewLine
        [System.IO.File]::WriteAllText(
            $temporaryPath,
            $json,
            (New-Object System.Text.UTF8Encoding($false))
        )
        Move-Item -LiteralPath $temporaryPath -Destination $statePath -Force

        $logState = [ordered]@{
            updated_at = $state.updated_at
            status = $status
            event = $eventName
            session_id = $sessionId
            turn_id = $turnId
        }
        [System.IO.File]::AppendAllText(
            $eventLogPath,
            (($logState | ConvertTo-Json -Compress) + [Environment]::NewLine),
            (New-Object System.Text.UTF8Encoding($false))
        )

        if ($eventName -eq 'UserPromptSubmit') {
            Start-TaskCompleteWatcher -SessionId $sessionId -TurnId $turnId -StateDirectory $stateDirectory
        }
    }
} catch {
    # Hooks must never interrupt Codex if the decorative bridge cannot update.
}

Write-Output '{}'
