param(
    [switch]$SelfTest
)

$ErrorActionPreference = 'Stop'
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

function Get-BridgeTimestamp {
    [DateTimeOffset]::UtcNow.ToString('o')
}

function New-BridgeToken {
    ('{0}-{1}' -f [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(), [Guid]::NewGuid().ToString('N'))
}

function Get-BridgeStateDirectory {
    if ($env:GOOGLEPIGGY_STATE_DIR) { return $env:GOOGLEPIGGY_STATE_DIR }
    Join-Path $env:LOCALAPPDATA 'GifPigDesktopPet'
}

function Get-ActorStatePath {
    param([string]$StateDirectory)
    if ([string]::IsNullOrWhiteSpace($script:hookActorId)) {
        return (Join-Path $StateDirectory 'codex-status.json')
    }
    $key = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($script:hookActorId)).Replace('/', '_')
    return (Join-Path (Join-Path $StateDirectory 'actors') ($key + '.json'))
}

function Write-AtomicJson {
    param([string]$Path, [object]$Value)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllText($temporary, (($Value | ConvertTo-Json -Depth 12) + [Environment]::NewLine), (New-Object Text.UTF8Encoding($false)))
        for ($attempt = 0; $attempt -lt 8; $attempt++) {
            try {
                if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temporary, $Path, [NullString]::Value) }
                else { [IO.File]::Move($temporary, $Path) }
                return
            } catch {
                if ($attempt -eq 7) { throw }
                Start-Sleep -Milliseconds (10 * ($attempt + 1))
            }
        }
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}

function Append-BridgeEvent {
    param(
        [string]$StateDirectory,
        [object]$Entry
    )

    try {
        New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
        $eventLogPath = Join-Path $StateDirectory 'codex-hook-events.jsonl'
        for ($attempt = 0; $attempt -lt 8; $attempt++) {
            try {
                [System.IO.File]::AppendAllText($eventLogPath, (($Entry | ConvertTo-Json -Compress -Depth 8) + [Environment]::NewLine), (New-Object System.Text.UTF8Encoding($false)))
                break
            } catch { Start-Sleep -Milliseconds (10 * ($attempt + 1)) }
        }
    } catch {
    }
}

function Read-BridgeStateFile {
    param([string]$StateDirectory)

    try {
        $statePath = Get-ActorStatePath -StateDirectory $StateDirectory
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
    $statePath = Get-ActorStatePath -StateDirectory $StateDirectory
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
        received_at = [double]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()) / 1000
    }
    foreach ($name in @('agent_id','agent_type','cwd','transcript_path','trigger','tool_name','tool_use_id')) {
        $value = Get-ObjectPropertyValue -Object $script:hookPayload -Names @($name)
        if ($null -ne $value) { $state[$name] = $value }
    }
    if ($script:hookPayload.prompt) {
        $preview = [string]$script:hookPayload.prompt
        $state.prompt_preview = $preview.Substring(0, [Math]::Min(100, $preview.Length))
        $normalizedPrompt = $preview.Replace("`r`n", "`n")
        if ($normalizedPrompt.StartsWith("User's request:`n" + '"""' + "`n") -and $normalizedPrompt.EndsWith("`n" + '"""' + "`n`nGenerate a title for this conversation:")) {
            $state.internal_request_kind = 'conversation_title'
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($PermissionRequestId)) {
        $state.permission_request_id = $PermissionRequestId
    }
    Write-AtomicJson -Path $statePath -Value $state
    if (-not [string]::IsNullOrWhiteSpace($script:hookActorId)) {
        $eventDirectory = Join-Path $StateDirectory 'family-events'
        $eventFile = ('{0:D20}-{1}.json' -f ([long]($state.received_at * 1000000)), [Guid]::NewGuid().ToString('N'))
        Write-AtomicJson -Path (Join-Path $eventDirectory $eventFile) -Value $state
    }

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
    param([string]$Text, [int]$MaxLength = 260)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ''
    }
    $value = $Text -replace '(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*["'']?[^"''\s,;]+', '$1=[redacted]'
    $value = $value -replace '(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+', '$1[redacted]'
    $value = $value -replace '[A-Za-z0-9_\-]{72,}', '[redacted-token]'
    if ($MaxLength -gt 0 -and $value.Length -gt $MaxLength) {
        $value = $value.Substring(0, $MaxLength - 3) + '...'
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
        if ($Object -is [Collections.IDictionary] -and $Object.Contains($name) -and $null -ne $Object[$name]) { return $Object[$name] }
        $property = $Object.PSObject.Properties[$name]
        if ($null -ne $property -and $null -ne $property.Value) {
            return $property.Value
        }
    }
    return $null
}

function Resolve-PermissionPath {
    param(
        [string]$Path,
        [string]$BaseDirectory = ''
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return ''
    }
    $value = $Path.Trim().Trim('"').Trim("'")
    if ($value -eq '~') {
        $value = $HOME
    } elseif ($value.StartsWith('~\') -or $value.StartsWith('~/')) {
        $value = Join-Path $HOME $value.Substring(2)
    }
    $value = [Environment]::ExpandEnvironmentVariables($value)
    if (-not [System.IO.Path]::IsPathRooted($value)) {
        $base = if ([string]::IsNullOrWhiteSpace($BaseDirectory)) {
            (Get-Location).Path
        } else {
            $BaseDirectory
        }
        $value = Join-Path $base $value
    }
    try {
        $value = [System.IO.Path]::GetFullPath($value)
    } catch {
    }
    return (Protect-PermissionText -Text $value)
}

function New-SinglePatchPermissionSummary {
    param(
        [string]$Verb,
        [string]$Path
    )

    switch ($Verb) {
        '创建' { return ('Codex 准备创建文件“{0}”并写入内容，是否允许？' -f $Path) }
        '删除' { return ('Codex 准备删除文件“{0}”，是否允许？' -f $Path) }
        '移动' { return ('Codex 准备把文件移动到“{0}”，是否允许？' -f $Path) }
        default { return ('Codex 准备修改文件“{0}”，是否允许执行本次修改？' -f $Path) }
    }
}

function Get-PatchPermissionSummary {
    param(
        [string]$Patch,
        [string]$BaseDirectory = ''
    )

    if ([string]::IsNullOrWhiteSpace($Patch)) {
        return $null
    }
    $markers = @(
        [pscustomobject]@{ Prefix = '*** Update File:'; Verb = '修改' },
        [pscustomobject]@{ Prefix = '*** Add File:'; Verb = '创建' },
        [pscustomobject]@{ Prefix = '*** Delete File:'; Verb = '删除' },
        [pscustomobject]@{ Prefix = '*** Move to:'; Verb = '移动' }
    )
    $operations = @()
    foreach ($line in ($Patch -split "`r?`n")) {
        foreach ($marker in $markers) {
            if (-not $line.StartsWith($marker.Prefix)) {
                continue
            }
            $path = Resolve-PermissionPath `
                -Path $line.Substring($marker.Prefix.Length) `
                -BaseDirectory $BaseDirectory
            if (-not [string]::IsNullOrWhiteSpace($path)) {
                $operations += [pscustomobject]@{
                    Verb = $marker.Verb
                    Path = $path
                }
            }
            break
        }
    }
    if ($operations.Count -eq 0) {
        return $null
    }
    if ($operations.Count -eq 1) {
        return (New-SinglePatchPermissionSummary `
            -Verb $operations[0].Verb `
            -Path $operations[0].Path)
    }
    $details = ($operations | ForEach-Object {
        '{0}文件“{1}”' -f $_.Verb, $_.Path
    }) -join '；'
    return "Codex 准备$details，是否允许？"
}

function Get-PermissionSummary {
    param([object]$Payload)

    $toolInput = Get-ObjectPropertyValue -Object $Payload -Names @('tool_input', 'input')
    foreach ($object in @($Payload, $toolInput)) {
        $reason = Get-ObjectPropertyValue -Object $object -Names @('justification', 'description', 'reason')
        if (-not [string]::IsNullOrWhiteSpace([string]$reason)) { return (Protect-PermissionText -Text ([string]$reason) -MaxLength 0) }
    }
    $matchedInput = Find-MatchingPermissionInput -Payload $Payload -ToolInput $toolInput
    if ($matchedInput) {
        $reason = Get-ObjectPropertyValue -Object $matchedInput -Names @('justification', 'description', 'reason')
        if (-not [string]::IsNullOrWhiteSpace([string]$reason)) { return (Protect-PermissionText -Text ([string]$reason) -MaxLength 0) }
    }
    $toolName = [string](Get-ObjectPropertyValue -Object $Payload -Names @('tool_name', 'toolName', 'name'))
    $command = [string](Get-ObjectPropertyValue -Object $toolInput -Names @(
        'command',
        'cmd',
        'input',
        'patch',
        'patch_text',
        'text',
        'content'
    ))
    $inputDirectory = [string](Get-ObjectPropertyValue -Object $toolInput -Names @(
        'workdir',
        'cwd',
        'working_directory'
    ))
    $payloadDirectory = [string](Get-ObjectPropertyValue -Object $Payload -Names @(
        'workdir',
        'cwd',
        'working_directory'
    ))
    $baseDirectory = if (-not [string]::IsNullOrWhiteSpace($inputDirectory)) {
        $inputDirectory
    } else {
        $payloadDirectory
    }
    if ($toolName -like '*apply_patch*' -or $command.Contains('*** Begin Patch')) {
        $patchSummary = Get-PatchPermissionSummary `
            -Patch $command `
            -BaseDirectory $baseDirectory
        if (-not [string]::IsNullOrWhiteSpace($patchSummary)) {
            return $patchSummary
        }
    }
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

function Find-MatchingPermissionInput {
    param([object]$Payload, [object]$ToolInput)
    $path = [string]$Payload.transcript_path
    $turn = [string]$Payload.turn_id
    $actor = if ($Payload.agent_id) { [string]$Payload.agent_id } else { [string]$Payload.session_id }
    $name = [string]$Payload.tool_name
    $command = [string](Get-ObjectPropertyValue -Object $ToolInput -Names @('cmd', 'command', 'input', 'patch', 'text'))
    if (-not $path -or -not $turn -or -not $actor -or -not $command -or -not (Test-Path -LiteralPath $path)) { return $null }
    try {
        $reader = New-Object IO.StreamReader($path, [Text.Encoding]::UTF8)
        try { $first = $reader.ReadLine() } finally { $reader.Dispose() }
        if ($first.Length -gt 1048576) { return $null }
        $meta = $first | ConvertFrom-Json
        if ([string]$meta.type -ne 'session_meta' -or [string]$meta.payload.id -ne $actor) { return $null }
        $stream = [IO.File]::Open($path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            $offset = [Math]::Max(0, $stream.Length - 16777216)
            $stream.Seek($offset, [IO.SeekOrigin]::Begin) | Out-Null
            $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)
            $text = $reader.ReadToEnd()
            $reader.Dispose()
        } finally { $stream.Dispose() }
        $lines = $text -split "`n"
        if ($offset -gt 0) { $lines = $lines | Select-Object -Skip 1 }
        $currentTurn = ''
        $matched = $null
        foreach ($line in $lines) {
            try { $record = $line | ConvertFrom-Json } catch { continue }
            $item = $record.payload
            if ([string]$record.type -eq 'turn_context') {
                $currentTurn = if ($item.turn_id) { [string]$item.turn_id } else { [string]$item.id }
            }
            if ([string]$record.type -eq 'event_msg' -and [string]$item.type -eq 'task_started') { $currentTurn = [string]$item.turn_id }
            if ($currentTurn -ne $turn -or [string]$record.type -ne 'response_item' -or [string]$item.type -ne 'function_call' -or [string]$item.name -ne $name) { continue }
            try { $arguments = $item.arguments | ConvertFrom-Json } catch { continue }
            $priorCommand = [string](Get-ObjectPropertyValue -Object $arguments -Names @('cmd', 'command', 'input', 'patch', 'text'))
            if ($priorCommand -eq $command) { $matched = $arguments }
        }
        return $matched
    } catch { return $null }
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
        agent_id = [string]$Payload.agent_id
        hook_pid = $PID
        details = (Protect-PermissionText -Text ($Payload.tool_input | ConvertTo-Json -Depth 12) -MaxLength 0)
    }

    Write-AtomicJson -Path $requestPath -Value $requestBody
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
                if ([string]$response.request_id -eq $requestId -and ($decision -eq 'allow' -or $decision -eq 'deny')) {
                    $message = if ($decision -eq 'deny') { [string]$response.message } else { '' }
                    Remove-Item -LiteralPath $requestPath -Force -ErrorAction SilentlyContinue
                    Remove-Item -LiteralPath $responsePath -Force -ErrorAction SilentlyContinue
                    $nextStatus = if ($decision -eq 'allow') { 'working' } else { 'idle' }
                    Write-BridgeStateFile `
                        -StateDirectory $StateDirectory `
                        -Status $nextStatus `
                        -EventName 'PermissionDecision' `
                        -SessionId $SessionId `
                        -TurnId $TurnId `
                        -Message $message | Out-Null
                    return (New-CodexPermissionOutput -Decision $decision -Message $message)
                }
                return (Complete-PermissionNoDecision -StateDirectory $StateDirectory -RequestPath $requestPath -ResponsePath $responsePath -SessionId $SessionId -TurnId $TurnId -Reason 'invalid or mismatched permission response')
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
            if ([string]$state.event -in @('Interrupt', 'SessionEnd', 'Stop', 'SubagentStop') -or ([string]$state.turn_id -and $TurnId -and [string]$state.turn_id -ne $TurnId)) {
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

if ($SelfTest) {
    $currentApplyPatchPayload = [pscustomobject]@{
        hook_event_name = 'PermissionRequest'
        tool_name = 'apply_patch'
        cwd = 'C:\Users\Test\project'
        tool_input = [pscustomobject]@{
            command = @'
*** Begin Patch
*** Update File: C:\Users\Test\Desktop\1.txt
@@
-test
+678
*** End Patch
'@
        }
    }
    $expectedSummary = 'Codex 准备修改文件“C:\Users\Test\Desktop\1.txt”，是否允许执行本次修改？'
    $actualSummary = Get-PermissionSummary -Payload $currentApplyPatchPayload
    if ($actualSummary -ne $expectedSummary) {
        throw "Current apply_patch summary mismatch.`nExpected: $expectedSummary`nActual: $actualSummary"
    }

    $relativeApplyPatchPayload = [pscustomobject]@{
        hook_event_name = 'PermissionRequest'
        tool_name = 'apply_patch'
        cwd = 'C:\Users\Test\project'
        tool_input = [pscustomobject]@{
            command = @'
*** Begin Patch
*** Add File: generated/new.txt
+hello
*** End Patch
'@
        }
    }
    $expectedRelativeSummary = 'Codex 准备创建文件“C:\Users\Test\project\generated\new.txt”并写入内容，是否允许？'
    $actualRelativeSummary = Get-PermissionSummary -Payload $relativeApplyPatchPayload
    if ($actualRelativeSummary -ne $expectedRelativeSummary) {
        throw "Relative apply_patch summary mismatch.`nExpected: $expectedRelativeSummary`nActual: $actualRelativeSummary"
    }

    $allowOutput = New-CodexPermissionOutput -Decision 'allow' | ConvertFrom-Json
    if ([string]$allowOutput.hookSpecificOutput.decision.behavior -ne 'allow') {
        throw 'PermissionRequest allow output does not use decision.behavior.'
    }

    $testTranscript = [IO.Path]::GetTempFileName()
    try {
        $records = @(
            [ordered]@{ type = 'session_meta'; payload = @{ id = 'self-test' } },
            [ordered]@{ type = 'event_msg'; payload = @{ type = 'task_started'; turn_id = 't1' } },
            [ordered]@{ type = 'response_item'; payload = @{ type = 'function_call'; name = 'exec_command'; arguments = (@{ cmd = 'echo exact'; justification = '同命令的中文理由' } | ConvertTo-Json -Compress) } }
        )
        $text = ($records | ForEach-Object { $_ | ConvertTo-Json -Compress -Depth 8 }) -join "`n"
        [IO.File]::WriteAllText($testTranscript, $text, (New-Object Text.UTF8Encoding($false)))
        $probe = [pscustomobject]@{ session_id = 'self-test'; turn_id = 't1'; transcript_path = $testTranscript; tool_name = 'exec_command'; tool_input = @{ cmd = 'echo exact' } }
        if ((Get-PermissionSummary -Payload $probe) -ne '同命令的中文理由') { throw 'Matching permission reason recovery failed.' }
        $probe.tool_input.cmd = 'echo different'
        if ((Get-PermissionSummary -Payload $probe) -eq '同命令的中文理由') { throw 'Permission reason leaked across different commands.' }
        $probe.tool_input.cmd = 'echo exact'
        $probe.turn_id = 't2'
        if ((Get-PermissionSummary -Payload $probe) -eq '同命令的中文理由') { throw 'Permission reason leaked across turns.' }
    } finally { [IO.File]::Delete($testTranscript) }

    Write-Output 'windows_hook_self_test=ok'
    return
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
    $script:hookPayload = $payload
    $script:hookActorId = if ($payload.agent_id) { [string]$payload.agent_id } else { $sessionId }

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
        'PreToolUse' { 'working' }
        'PostToolUse' { 'working' }
        'Stop' { 'success' }
        'Interrupt' { 'interrupted' }
        'PreCompact' { 'compacting' }
        'PostCompact' { 'success' }
        'SubagentStart' { 'working' }
        'SubagentStop' { 'success' }
        'SessionEnd' { 'idle' }
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

        # The running GUI observes actor-scoped rollout lifecycle events. No
        # global completion watcher may overwrite another actor's state.
    }
} catch {
    # Hooks must never interrupt Codex if the decorative bridge cannot update.
}

Write-Output '{}'
