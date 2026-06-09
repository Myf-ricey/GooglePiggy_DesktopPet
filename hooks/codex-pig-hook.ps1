param()

$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

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

function Get-BridgeTimestamp {
    [DateTimeOffset]::UtcNow.ToString('o')
}

function New-BridgeToken {
    ('{0}-{1}' -f [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(), [Guid]::NewGuid().ToString('N'))
}

function Get-BridgeStateDirectory {
    Join-Path $env:LOCALAPPDATA 'GifPigDesktopPet'
}

function Append-BridgeEvent {
    param(
        [string]$StateDirectory,
        [object]$Entry
    )

    try {
        New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
        $eventLogPath = Join-Path $StateDirectory 'codex-hook-events.jsonl'
        [System.IO.File]::AppendAllText(
            $eventLogPath,
            (($Entry | ConvertTo-Json -Compress -Depth 8) + [Environment]::NewLine),
            (New-Object System.Text.UTF8Encoding($false))
        )
    } catch {
    }
}

function Read-BridgeStateFile {
    param([string]$StateDirectory)

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

function Write-BridgeStateFile {
    param(
        [string]$StateDirectory,
        [string]$Status,
        [string]$EventName,
        [string]$SessionId,
        [string]$TurnId,
        [string]$Message = '',
        [string]$PermissionRequestId = '',
        [string]$Source = 'codex-hook'
    )

    New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
    $statePath = Join-Path $StateDirectory 'codex-status.json'
    $temporaryPath = Join-Path $StateDirectory 'codex-status.json.tmp'
    $updatedAt = Get-BridgeTimestamp
    $state = [ordered]@{
        status = $Status
        token = New-BridgeToken
        updated_at = $updatedAt
        source = $Source
        event = $EventName
        message = $Message
        session_id = $SessionId
        turn_id = $TurnId
    }
    if (-not [string]::IsNullOrWhiteSpace($PermissionRequestId)) {
        $state.permission_request_id = $PermissionRequestId
    }
    [System.IO.File]::WriteAllText(
        $temporaryPath,
        (($state | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
        (New-Object System.Text.UTF8Encoding($false))
    )
    Move-Item -LiteralPath $temporaryPath -Destination $statePath -Force

    $logState = [ordered]@{
        updated_at = $updatedAt
        status = $Status
        event = $EventName
        session_id = $SessionId
        turn_id = $TurnId
    }
    if (-not [string]::IsNullOrWhiteSpace($PermissionRequestId)) {
        $logState.permission_request_id = $PermissionRequestId
    }
    Append-BridgeEvent -StateDirectory $StateDirectory -Entry $logState
    return $state
}

function Test-PigPetHeartbeat {
    param([string]$StateDirectory)

    try {
        $heartbeatPath = Join-Path $StateDirectory 'pig-heartbeat.json'
        if (-not (Test-Path -LiteralPath $heartbeatPath)) {
            return $false
        }
        $heartbeat = Get-Content -LiteralPath $heartbeatPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $updatedAt = [DateTimeOffset]::Parse([string]$heartbeat.updated_at)
        $ageSeconds = ([DateTimeOffset]::UtcNow - $updatedAt.ToUniversalTime()).TotalSeconds
        if ($ageSeconds -lt 0 -or $ageSeconds -gt 180) {
            return $false
        }
        $pidText = [string]$heartbeat.pid
        if (-not [string]::IsNullOrWhiteSpace($pidText)) {
            $pidValue = 0
            if ([int]::TryParse($pidText, [ref]$pidValue)) {
                if (-not (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
                    return $false
                }
            }
        }
        return $true
    } catch {
        return $false
    }
}

function Protect-PermissionText {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ''
    }
    $value = $Text -replace '(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*["'']?[^"''\s,;]+', '$1=[redacted]'
    $value = $value -replace '(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+', '$1[redacted]'
    $value = $value -replace '[A-Za-z0-9_\-]{72,}', '[redacted-token]'
    if ($value.Length -gt 260) {
        $value = $value.Substring(0, 257) + '...'
    }
    return $value
}

function Get-ObjectPropertyValue {
    param(
        [object]$Object,
        [string[]]$Names
    )

    if ($null -eq $Object) {
        return $null
    }
    foreach ($name in $Names) {
        $property = $Object.PSObject.Properties[$name]
        if ($null -ne $property -and $null -ne $property.Value) {
            return $property.Value
        }
    }
    return $null
}

function Get-PermissionSummary {
    param([object]$Payload)

    $toolInput = Get-ObjectPropertyValue -Object $Payload -Names @('tool_input', 'input')
    $candidate = Get-ObjectPropertyValue -Object $toolInput -Names @(
        'description',
        'justification',
        'reason',
        'command',
        'path',
        'file_path',
        'query'
    )
    if ($null -eq $candidate) {
        $candidate = Get-ObjectPropertyValue -Object $Payload -Names @('description', 'command')
    }
    if ($null -eq $candidate -and $null -ne $toolInput) {
        try {
            $candidate = $toolInput | ConvertTo-Json -Compress -Depth 5
        } catch {
            $candidate = ''
        }
    }
    $summary = Protect-PermissionText -Text ([string]$candidate)
    if ([string]::IsNullOrWhiteSpace($summary)) {
        $summary = 'Codex is asking for permission.'
    }
    return $summary
}

function New-CodexPermissionOutput {
    param(
        [string]$Decision,
        [string]$Message = ''
    )

    if ($Decision -ne 'allow' -and $Decision -ne 'deny') {
        return '{}'
    }
    $decisionBody = [ordered]@{ behavior = $Decision }
    if ($Decision -eq 'deny' -and -not [string]::IsNullOrWhiteSpace($Message)) {
        $decisionBody.message = $Message
    }
    $body = [ordered]@{
        hookSpecificOutput = [ordered]@{
            hookEventName = 'PermissionRequest'
            decision = $decisionBody
        }
    }
    return ($body | ConvertTo-Json -Compress -Depth 8)
}

function Complete-PermissionNoDecision {
    param(
        [string]$StateDirectory,
        [string]$RequestPath,
        [string]$ResponsePath,
        [string]$SessionId,
        [string]$TurnId,
        [string]$Reason
    )

    Remove-Item -LiteralPath $RequestPath -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ResponsePath -Force -ErrorAction SilentlyContinue
    Write-BridgeStateFile `
        -StateDirectory $StateDirectory `
        -Status 'idle' `
        -EventName 'PermissionNoDecision' `
        -SessionId $SessionId `
        -TurnId $TurnId `
        -Message $Reason | Out-Null
    return '{}'
}

function Invoke-PigPermissionRequest {
    param(
        [object]$Payload,
        [string]$StateDirectory,
        [string]$SessionId,
        [string]$TurnId
    )

    if (-not (Test-PigPetHeartbeat -StateDirectory $StateDirectory)) {
        Append-BridgeEvent -StateDirectory $StateDirectory -Entry ([ordered]@{
            updated_at = Get-BridgeTimestamp
            status = 'permission'
            event = 'PermissionRequest'
            session_id = $SessionId
            turn_id = $TurnId
            ignored = $true
            reason = 'no-fresh-pig-heartbeat'
        })
        return '{}'
    }

    $requestDirectory = Join-Path $StateDirectory 'permission-requests'
    New-Item -ItemType Directory -Force -Path $requestDirectory | Out-Null
    $requestId = [Guid]::NewGuid().ToString('N')
    $requestPath = Join-Path $requestDirectory ($requestId + '.request.json')
    $responsePath = Join-Path $requestDirectory ($requestId + '.response.json')
    $toolName = [string](Get-ObjectPropertyValue -Object $Payload -Names @('tool_name', 'toolName', 'name'))
    if ([string]::IsNullOrWhiteSpace($toolName)) {
        $toolName = 'Codex'
    }
    $createdAt = [DateTimeOffset]::UtcNow
    $expiresAt = $createdAt.AddMinutes(10)
    $requestBody = [ordered]@{
        request_id = $requestId
        created_at = $createdAt.ToString('o')
        expires_at = $expiresAt.ToString('o')
        session_id = $SessionId
        turn_id = $TurnId
        tool_name = Protect-PermissionText -Text $toolName
        summary = Get-PermissionSummary -Payload $Payload
    }

    [System.IO.File]::WriteAllText(
        $requestPath,
        (($requestBody | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
        (New-Object System.Text.UTF8Encoding($false))
    )
    Write-BridgeStateFile `
        -StateDirectory $StateDirectory `
        -Status 'permission' `
        -EventName 'PermissionRequest' `
        -SessionId $SessionId `
        -TurnId $TurnId `
        -PermissionRequestId $requestId | Out-Null

    $deadline = (Get-Date).AddMinutes(10)
    while ((Get-Date) -lt $deadline) {
        if (Test-Path -LiteralPath $responsePath) {
            try {
                $response = Get-Content -LiteralPath $responsePath -Raw -Encoding UTF8 | ConvertFrom-Json
                $decision = [string]$response.decision
                if ($decision -eq 'allow' -or $decision -eq 'deny') {
                    $message = if ($decision -eq 'deny') { [string]$response.message } else { '' }
                    Remove-Item -LiteralPath $requestPath -Force -ErrorAction SilentlyContinue
                    Remove-Item -LiteralPath $responsePath -Force -ErrorAction SilentlyContinue
                    $nextStatus = if ($decision -eq 'allow') { 'thinking' } else { 'idle' }
                    Write-BridgeStateFile `
                        -StateDirectory $StateDirectory `
                        -Status $nextStatus `
                        -EventName 'PermissionDecision' `
                        -SessionId $SessionId `
                        -TurnId $TurnId `
                        -Message $message | Out-Null
                    return (New-CodexPermissionOutput -Decision $decision -Message $message)
                }
            } catch {
                return (Complete-PermissionNoDecision `
                    -StateDirectory $StateDirectory `
                    -RequestPath $requestPath `
                    -ResponsePath $responsePath `
                    -SessionId $SessionId `
                    -TurnId $TurnId `
                    -Reason 'invalid permission response')
            }
        }

        $state = Read-BridgeStateFile -StateDirectory $StateDirectory
        if ($null -ne $state) {
            if ([string]$state.status -ne 'permission' -or [string]$state.permission_request_id -ne $requestId) {
                return (Complete-PermissionNoDecision `
                    -StateDirectory $StateDirectory `
                    -RequestPath $requestPath `
                    -ResponsePath $responsePath `
                    -SessionId $SessionId `
                    -TurnId $TurnId `
                    -Reason 'permission handled elsewhere')
            }
        }

        Start-Sleep -Milliseconds 150
    }

    return (Complete-PermissionNoDecision `
        -StateDirectory $StateDirectory `
        -RequestPath $requestPath `
        -ResponsePath $responsePath `
        -SessionId $SessionId `
        -TurnId $TurnId `
        -Reason 'permission timeout')
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

    $stateDirectory = Get-BridgeStateDirectory
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

    if ($eventName -eq 'PermissionRequest') {
        Write-Output (Invoke-PigPermissionRequest `
            -Payload $payload `
            -StateDirectory $stateDirectory `
            -SessionId $sessionId `
            -TurnId $turnId)
        return
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
        New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null
        if ($eventName -eq 'PostToolUse') {
            try {
                $existingState = Read-BridgeStateFile -StateDirectory $stateDirectory
                $existingTime = [DateTimeOffset]::Parse([string]$existingState.updated_at)
                $ageSeconds = ([DateTimeOffset]::UtcNow - $existingTime.ToUniversalTime()).TotalSeconds
                if ([string]$existingState.status -eq 'success' -and $ageSeconds -ge 0 -and $ageSeconds -le 3) {
                    Append-BridgeEvent -StateDirectory $stateDirectory -Entry ([ordered]@{
                        updated_at = Get-BridgeTimestamp
                        status = $status
                        event = $eventName
                        session_id = $sessionId
                        turn_id = $turnId
                        ignored = $true
                        reason = 'recent-success'
                    })
                    Write-Output '{}'
                    return
                }
            } catch {
                # Fall through to the normal status write.
            }
        }
        Write-BridgeStateFile `
            -StateDirectory $stateDirectory `
            -Status $status `
            -EventName $eventName `
            -SessionId $sessionId `
            -TurnId $turnId | Out-Null

        if ($eventName -eq 'UserPromptSubmit') {
            Start-TaskCompleteWatcher -SessionId $sessionId -TurnId $turnId -StateDirectory $stateDirectory
        }
    }
} catch {
    # Hooks must never interrupt Codex if the decorative bridge cannot update.
}

Write-Output '{}'
