#requires -Version 7.0
[CmdletBinding()]
param([string]$EnvFile = (Join-Path $PSScriptRoot '../../.env'))

$ErrorActionPreference = 'Stop'
$contextName = 'kind-sagomungchi-local'
$namespaceName = 'platform'
$secretName = 'platform-data-credentials'
$requiredKeys = @('POSTGRES_USER', 'POSTGRES_PASSWORD', 'RABBITMQ_USER', 'RABBITMQ_PASSWORD', 'MINIO_ROOT_USER', 'MINIO_ROOT_PASSWORD')

# Use UTF-8 stdin: no credential is put on kubectl's command line or in a temp file.
function Invoke-LocalKubectl {
    param([string[]]$KubectlArguments, [string]$InputJson)
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = (Get-Command kubectl -ErrorAction Stop).Source
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.RedirectStandardInput = $true
    $startInfo.StandardInputEncoding = [System.Text.UTF8Encoding]::new($false)
    foreach ($argument in @('--context', $contextName) + $KubectlArguments) { $startInfo.ArgumentList.Add($argument) }
    $process = [System.Diagnostics.Process]::Start($startInfo)
    if ($InputJson) { $process.StandardInput.Write($InputJson) }
    $process.StandardInput.Close()
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    $errorTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(30000)) {
        $process.Kill($true)
        throw 'kubectl timed out. Check the local cluster and retry.'
    }
    $output = $outputTask.GetAwaiter().GetResult()
    $null = $errorTask.GetAwaiter().GetResult()
    if ($process.ExitCode -ne 0) { throw "kubectl failed (exit $($process.ExitCode)). Check local context and permissions; credential details are suppressed." }
    return $output
}

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { throw 'Environment file does not exist.' }
$credentials = @{}
foreach ($line in [System.IO.File]::ReadAllLines((Resolve-Path -LiteralPath $EnvFile).Path)) {
    if ($line -notmatch '^\s*([A-Z_]+)\s*=(.*)$') { continue }
    $key = $Matches[1]
    if ($key -notin $requiredKeys) { continue }
    if ($credentials.ContainsKey($key)) { throw "Duplicate environment key: $key" }
    $value = $Matches[2].Trim()
    if ($value.StartsWith("'") -and $value.EndsWith("'") -and $value.Length -ge 2) {
        $value = $value.Substring(1, $value.Length - 2)
        if ($value.Contains("'")) { throw "Use a literal value without embedded single quotes: $key" }
    } elseif ($value -match '[\$"\x27]' -or $value -match '\s#') {
        throw "Use an unquoted literal or single-quoted literal value: $key"
    }
    if ([string]::IsNullOrWhiteSpace($value) -or $value -match '[\r\n\x00]') { throw "Missing or invalid environment value: $key" }
    $credentials[$key] = $value
}
foreach ($key in $requiredKeys) { if (-not $credentials.ContainsKey($key)) { throw "Missing environment key: $key" } }
if ($credentials.RABBITMQ_USER.Contains(':')) { throw 'RABBITMQ_USER must not contain a colon.' }
if ($credentials.MINIO_ROOT_USER.Length -lt 3 -or $credentials.MINIO_ROOT_PASSWORD.Length -lt 8) { throw 'MinIO requires a username of at least 3 characters and password of at least 8 characters.' }

$existingJson = Invoke-LocalKubectl -KubectlArguments @('-n', $namespaceName, 'get', 'secret', $secretName, '--ignore-not-found', '-o', 'json')
if (-not [string]::IsNullOrWhiteSpace($existingJson)) {
    $existing = $existingJson | ConvertFrom-Json -AsHashtable
    foreach ($key in $requiredKeys) {
        $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($credentials[$key]))
        if ($existing.data[$key] -cne $encoded) { throw 'Existing Secret values differ. Do not replace credentials without coordinating stored data and account rotation.' }
    }
    Write-Output "Secret $namespaceName/$secretName already matches."
    return
}
$namespaceJson = Invoke-LocalKubectl -KubectlArguments @('get', 'namespace', $namespaceName, '--ignore-not-found', '-o', 'json')
if ([string]::IsNullOrWhiteSpace($namespaceJson)) {
    $manifest = @{apiVersion='v1'; kind='Namespace'; metadata=@{name=$namespaceName}} | ConvertTo-Json -Depth 4
    $null = Invoke-LocalKubectl -KubectlArguments @('create', '-f', '-') -InputJson $manifest
}
$manifest = @{apiVersion='v1'; kind='Secret'; metadata=@{name=$secretName; namespace=$namespaceName}; type='Opaque'; stringData=$credentials} | ConvertTo-Json -Depth 5 -Compress
$null = Invoke-LocalKubectl -KubectlArguments @('create', '-f', '-') -InputJson $manifest
Write-Output "Secret $namespaceName/$secretName created."
