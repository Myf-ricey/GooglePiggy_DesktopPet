param(
    [int]$Seconds = 10,
    [string]$Message = 'Permission preview: click Allow or Deny on the pig bubble.',
    [string]$StateDirectory = ''
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($StateDirectory)) {
    $StateDirectory = Join-Path $env:LOCALAPPDATA 'GifPigDesktopPet'
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Payload
    )

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    [System.IO.File]::WriteAllText(
        $Path,
        (($Payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
        (New-Object System.Text.UTF8Encoding($false))
    )
}

$requestDirectory = Join-Path $StateDirectory 'permission-requests'
New-Item -ItemType Directory -Force -Path $requestDirectory | Out-Null

$requestId = 'preview-{0}' -f ([Guid]::NewGuid().ToString('N'))
$now = [DateTimeOffset]::UtcNow
$expiresAt = $now.AddSeconds([Math]::Max(5, $Seconds + 5))
$requestPath = Join-Path $requestDirectory ($requestId + '.request.json')
$responsePath = Join-Path $requestDirectory ($requestId + '.response.json')
$statusPath = Join-Path $StateDirectory 'codex-status.json'

$request = [ordered]@{
    request_id = $requestId
    created_at = $now.ToString('o')
    expires_at = $expiresAt.ToString('o')
    session_id = 'permission-preview'
    turn_id = 'permission-preview'
    tool_name = 'Permission preview'
    summary = $Message
}
Write-JsonFile -Path $requestPath -Payload $request

$status = [ordered]@{
    status = 'permission'
    token = $requestId
    updated_at = $now.ToString('o')
    source = 'permission-preview'
    event = 'PermissionRequest'
    message = $Message
    session_id = 'permission-preview'
    turn_id = 'permission-preview'
    permission_request_id = $requestId
}
Write-JsonFile -Path $statusPath -Payload $status

Write-Host "Permission preview is active for $Seconds seconds."
Write-Host "Request: $requestId"

$deadline = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $responsePath) {
        $response = Get-Content -LiteralPath $responsePath -Raw | ConvertFrom-Json
        Write-Host ("Pig bubble decision: {0}" -f $response.decision)
        exit 0
    }
    Start-Sleep -Milliseconds 200
}

$currentStatus = $null
try {
    $currentStatus = Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
} catch {
    $currentStatus = $null
}

if (
    $null -ne $currentStatus -and
    [string]$currentStatus.status -eq 'permission' -and
    [string]$currentStatus.permission_request_id -eq $requestId
) {
    $idle = [ordered]@{
        status = 'idle'
        token = ('preview-clear-{0}' -f ([Guid]::NewGuid().ToString('N')))
        updated_at = [DateTimeOffset]::UtcNow.ToString('o')
        source = 'permission-preview'
        event = 'PreviewTimeout'
        message = 'Permission preview timed out.'
        session_id = 'permission-preview'
        turn_id = 'permission-preview'
    }
    Write-JsonFile -Path $statusPath -Payload $idle
}

Write-Host 'Permission preview finished without a decision.'
