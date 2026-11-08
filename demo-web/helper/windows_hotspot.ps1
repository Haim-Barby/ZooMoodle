# Local Mobile Hotspot attempt. This file is part of the repo.
# It does not download or invoke remote code, and it does not call the legacy hosted-network command.
param([switch]$OptIn)

if (-not $OptIn) {
    Write-Output '{"started":false,"reason":"opt_in_required"}'
    exit 2
}

try {
    $profile = [Windows.Networking.Connectivity.NetworkInformation,Windows.Networking.Connectivity,ContentType=WindowsRuntime]::GetInternetConnectionProfile()
    if (-not $profile) {
        Write-Output '{"started":false,"reason":"no_upstream_profile"}'
        exit 3
    }
    $manager = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]::CreateFromConnectionProfile($profile)
    $type = [Windows.Networking.NetworkOperators.NetworkOperatorTetheringManager,Windows.Networking.NetworkOperators,ContentType=WindowsRuntime]
    $capability = [string]$type::GetTetheringCapabilityFromConnectionProfile($profile)
    if ($capability -ne "Enabled") {
        Write-Output ('{"started":false,"reason":"adapter_' + $capability + '"}')
        exit 4
    }
    $operation = $manager.StartTetheringAsync()
    $operation.AsTask().Wait()
    Write-Output '{"started":true,"reason":"api_reported_started"}'
    exit 0
}
catch {
    Write-Output '{"started":false,"reason":"api_failed"}'
    exit 5
}
