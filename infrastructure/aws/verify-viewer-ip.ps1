#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Kubeconfig,
    [Parameter(Mandatory)][string]$ViewerIp
)
$ErrorActionPreference = 'Stop'
$null = [System.Net.IPAddress]::Parse($ViewerIp)
$expectedCluster = 'sagomungchi-demo-eks'
$context = & kubectl --kubeconfig $Kubeconfig config current-context
if ($LASTEXITCODE -ne 0 -or $context.Trim() -ne $expectedCluster) { throw 'Unexpected Kubernetes context' }
function Get-Counter([string]$Ip) {
    $hash = [Convert]::ToBase64String([Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($Ip))).TrimEnd('=').Replace('+','-').Replace('/','_')
    $value = & kubectl --kubeconfig $Kubeconfig -n platform exec redis-0 -- redis-cli --raw GET "student-device:attempt:ip:$hash"
    if ($LASTEXITCODE -ne 0) { throw 'Redis counter query failed' }
    if ([string]::IsNullOrWhiteSpace(($value -join ''))) { return 0L }
    return [long]($value -join '')
}
$spoofedIp = '203.0.113.185'
$before = Get-Counter $ViewerIp
$spoofedBefore = Get-Counter $spoofedIp
if ($before -ge 18) { throw 'Existing registration limit is near exhaustion; retry after its 10-minute window' }
foreach ($spoof in @($false, $true)) {
    $headers = @{'Origin'='https://d3jf0rnm6vhd9v.cloudfront.net'; 'X-Requested-With'='XMLHttpRequest'}
    if ($spoof) { $headers['X-Forwarded-For'] = $spoofedIp }
    # An invalid-format code cannot consume a real pairing or create a device.
    # Each request uses one real rate-limit attempt; let its existing TTL expire.
    $response = Invoke-WebRequest 'https://d3jf0rnm6vhd9v.cloudfront.net/api/v1/auth/student/devices' -Method Post -Headers $headers -ContentType 'application/json' -Body '{"pairingCode":"!issue185!","label":"issue185-viewer-ip-check"}' -SkipHttpErrorCheck
    $body = if ($response.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($response.Content) } else { $response.Content }
    if ($response.StatusCode -ne 400 -or ($body | ConvertFrom-Json).code -ne 'PAIRING_CODE_INVALID') {
        throw "Unexpected registration response (HTTP $($response.StatusCode)); no success inferred"
    }
}
$after = Get-Counter $ViewerIp
$spoofedAfter = Get-Counter $spoofedIp
if ($after -ne $before + 2 -or $spoofedAfter -ne $spoofedBefore) {
    throw 'Viewer counter did not increase exactly twice, or spoofed counter changed; investigate egress IP, concurrency and TTL'
}
[pscustomobject]@{ViewerCounterDelta=$after-$before; SpoofedCounterDelta=$spoofedAfter-$spoofedBefore; DevicesCreated=0}
