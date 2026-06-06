param()

$ErrorActionPreference = 'Stop'

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
        New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null

        $sessionId = if ($payload -and $payload.session_id) {
            [string]$payload.session_id
        } else {
            ''
        }
        $state = [ordered]@{
            status = $status
            token = ('{0}-{1}' -f [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(), [Guid]::NewGuid().ToString('N'))
            updated_at = [DateTimeOffset]::UtcNow.ToString('o')
            source = 'codex-hook'
            event = $eventName
            message = ''
            session_id = $sessionId
        }
        $json = ($state | ConvertTo-Json) + [Environment]::NewLine
        [System.IO.File]::WriteAllText(
            $temporaryPath,
            $json,
            (New-Object System.Text.UTF8Encoding($false))
        )
        Move-Item -LiteralPath $temporaryPath -Destination $statePath -Force
    }
} catch {
    # Hooks must never interrupt Codex if the decorative bridge cannot update.
}

Write-Output '{}'
