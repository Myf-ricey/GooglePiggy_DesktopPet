# Shared by the packaged app and installer. All registry operations are performed
# by the Windows registry provider against the caller's explicit user SID.
function Invoke-GooglePiggyAutostart {
    param($Request)
    $ErrorActionPreference = 'Stop'
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $userHive = [uint32]2147483651
    $run = if ($Request.run_key) { [string]$Request.run_key } else { 'Software\Microsoft\Windows\CurrentVersion\Run' }
    $prefs = if ($Request.preference_key) { [string]$Request.preference_key } else { 'Software\GooglePiggy\Preferences' }
    $approved = if ($Request.approved_key) { [string]$Request.approved_key } else { 'Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run' }
    $name = if ($Request.value_name) { [string]$Request.value_name } else { 'GifPigDesktopPet' }
    $expected = [string]$Request.command
    $target = [string]$Request.target
    function Invoke-RegistryMethod($method, $arguments) {
        Invoke-CimMethod -Namespace root/default -ClassName StdRegProv -MethodName $method -Arguments $arguments -ErrorAction Stop
    }
    function Read-RegistryValue($key, $valueName, $method, $field, $hive = $userHive) {
        $sub = if ($hive -eq $userHive) { $sid + '\' + $key } else { $key }
        $args = @{ hDefKey=$hive; sSubKeyName=$sub; sValueName=$valueName }
        $r = Invoke-RegistryMethod $method $args
        if ($r.ReturnValue -eq 0) { return $r.$field }
        if ($r.ReturnValue -eq 2) { return $null }
        # StdRegProv can return 1 for an absent value. Confirm absence, never
        # confuse access-denied/provider errors with a disabled startup setting.
        if ($r.ReturnValue -eq 1) {
            $values = Invoke-RegistryMethod 'EnumValues' @{hDefKey=$hive; sSubKeyName=$sub}
            if ($values.ReturnValue -eq 2 -or ($values.ReturnValue -eq 0 -and $valueName -notin $values.sNames)) { return $null }
        }
        throw "Cannot read startup registration (Windows error $($r.ReturnValue))."
    }
    function Write-RegistryValue($key, $valueName, $method, $field, $value) {
        $sub = $sid + '\' + $key
        $r = Invoke-RegistryMethod 'CreateKey' @{hDefKey=$userHive; sSubKeyName=$sub}
        if ($r.ReturnValue -ne 0) { throw "Cannot create startup key (Windows error $($r.ReturnValue))." }
        $args = @{hDefKey=$userHive; sSubKeyName=$sub; sValueName=$valueName}
        $args[$field] = $value
        $r = Invoke-RegistryMethod $method $args
        if ($r.ReturnValue -ne 0) { throw "Cannot save startup setting (Windows error $($r.ReturnValue))." }
    }
    function Remove-RegistryValue($key, $valueName) {
        $sub = $sid + '\' + $key
        $values = Invoke-RegistryMethod 'EnumValues' @{hDefKey=$userHive; sSubKeyName=$sub}
        if ($values.ReturnValue -eq 2 -or ($values.ReturnValue -eq 0 -and $valueName -notin $values.sNames)) { return }
        if ($values.ReturnValue -ne 0) { throw "Cannot inspect startup key (Windows error $($values.ReturnValue))." }
        $r = Invoke-RegistryMethod 'DeleteValue' @{hDefKey=$userHive; sSubKeyName=$sub; sValueName=$valueName}
        if ($r.ReturnValue -ne 0) { throw "Cannot remove startup setting (Windows error $($r.ReturnValue))." }
    }
    function Get-StartupStatus {
        $command = Read-RegistryValue $run $name 'GetStringValue' 'sValue'
        $preference = Read-RegistryValue $prefs 'AutostartEnabled' 'GetDWORDValue' 'uValue'
        $approval = @(Read-RegistryValue $approved $name 'GetBinaryValue' 'uValue')
        $disabled = $approval.Count -gt 0 -and $approval[0] -in @(3,7)
        $policyKey = 'Software\Microsoft\Windows\CurrentVersion\Policies\Explorer'
        $userPolicy = Read-RegistryValue $policyKey 'DisableCurrentUserRun' 'GetDWORDValue' 'uValue'
        $machinePolicy = Read-RegistryValue $policyKey 'DisableCurrentUserRun' 'GetDWORDValue' 'uValue' ([uint32]2147483650)
        $blocked = $userPolicy -eq 1 -or $machinePolicy -eq 1
        $matches = -not [string]::IsNullOrWhiteSpace($command) -and [string]::Equals($command.Trim(),$expected.Trim(),[StringComparison]::OrdinalIgnoreCase)
        $exists = -not [string]::IsNullOrWhiteSpace($target) -and (Test-Path -LiteralPath $target -PathType Leaf)
        [pscustomobject]@{ command=$command; registered=($null -ne $command); command_matches=$matches; target_exists=$exists; preference=$preference; system_disabled=$disabled; policy_blocked=$blocked; enabled=($matches -and $exists -and -not $disabled -and -not $blocked); backend='Windows StdRegProv' }
    }
    $state = Get-StartupStatus
    $action = [string]$Request.action
    if ($action -notin @('inspect','enable','disable','reconcile','remove')) { throw 'Unsupported startup action.' }
    if ($action -eq 'inspect') { return $state }
    if ($action -eq 'remove') {
        # An old installation must not unregister a newer installation.
        if (-not $state.command_matches) { return $state }
        $action = 'disable'
    }
    if ($action -eq 'reconcile') {
        if ($state.system_disabled -or $state.policy_blocked) { return $state }
        $intent = $state.preference
        if ($null -eq $intent -and $null -ne $Request.legacy_preference) { $intent = $Request.legacy_preference }
        if ($null -eq $intent) { $intent = [int]($state.registered -or -not $Request.previous_install) }
        if ($intent -notin @(0,1)) { throw 'Invalid saved startup preference.' }
        if ($intent -eq 1 -and $state.enabled -and $state.preference -eq 1) { return $state }
        if ($intent -eq 0 -and -not $state.registered -and $state.preference -eq 0) { return $state }
        $action = if ($intent -eq 1) { 'enable' } else { 'disable' }
    }
    if ($action -eq 'enable') {
        if ($state.policy_blocked) { throw 'Windows policy prevents startup registration. No policy was changed.' }
        if (-not $state.target_exists -or [string]::IsNullOrWhiteSpace($expected) -or $expected.Length -gt 260) { throw 'Startup executable is missing or the startup command exceeds 260 characters.' }
        Write-RegistryValue $run $name 'SetStringValue' 'sValue' $expected
        # Only explicit enabling can override a user's Startup Apps switch.
        if ($Request.action -eq 'enable') { Remove-RegistryValue $approved $name }
        $actual = Get-StartupStatus
        if (-not $actual.enabled) { throw 'Windows did not confirm the startup command; startup was not reported as enabled.' }
        Write-RegistryValue $prefs 'AutostartEnabled' 'SetDWORDValue' 'uValue' ([uint32]1)
    } else {
        Remove-RegistryValue $run $name
        if ((Get-StartupStatus).registered) { throw 'Windows still reports a startup command after removal.' }
        Write-RegistryValue $prefs 'AutostartEnabled' 'SetDWORDValue' 'uValue' ([uint32]0)
    }
    $result = Get-StartupStatus
    if (($action -eq 'enable' -and (-not $result.enabled -or $result.preference -ne 1)) -or ($action -eq 'disable' -and ($result.registered -or $result.preference -ne 0))) { throw 'Startup read-back verification failed.' }
    return $result
}

if ($MyInvocation.InvocationName -ne '.') {
    [Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
    [Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
    try {
        $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
        Invoke-GooglePiggyAutostart $request | ConvertTo-Json -Compress -Depth 5
    } catch {
        [Console]::Error.WriteLine($_.Exception.Message)
        exit 1
    }
}
