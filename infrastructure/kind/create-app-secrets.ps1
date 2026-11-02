#requires -Version 7.0
[CmdletBinding()]
param([string]$EnvFile = (Join-Path $PSScriptRoot '../../.env'))

$ErrorActionPreference = 'Stop'
$contextName = 'kind-sagomungchi-local'
$nodeName = 'sagomungchi-local-control-plane'
$requiredKeys = @(
    'POSTGRES_USER', 'POSTGRES_PASSWORD', 'RABBITMQ_USER', 'RABBITMQ_PASSWORD',
    'MINIO_ROOT_USER', 'MINIO_ROOT_PASSWORD', 'INTERNAL_TOKEN', 'AUTH_JWT_SECRET'
)
$optionalKeys = @('OPENAI_API_KEY', 'GRAFANA_ADMIN_USER', 'GRAFANA_ADMIN_PASSWORD')

# Pass manifests through UTF-8 stdin so no credential appears in a command argument or temp file.
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
    foreach ($argument in @('--context', $contextName) + $KubectlArguments) {
        $startInfo.ArgumentList.Add($argument)
    }
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
    if ($process.ExitCode -ne 0) {
        throw "kubectl failed (exit $($process.ExitCode)). Check local context and permissions; credential details are suppressed."
    }
    return $output
}

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) { throw 'Environment file does not exist.' }
$credentials = @{}
foreach ($line in [System.IO.File]::ReadAllLines((Resolve-Path -LiteralPath $EnvFile).Path)) {
    if ($line -notmatch '^\s*([A-Z_]+)\s*=(.*)$') { continue }
    $key = $Matches[1]
    if ($key -notin ($requiredKeys + $optionalKeys)) { continue }
    if ($credentials.ContainsKey($key)) { throw "Duplicate environment key: $key" }
    $value = $Matches[2].Trim()
    if ($value.StartsWith("'") -and $value.EndsWith("'") -and $value.Length -ge 2) {
        $value = $value.Substring(1, $value.Length - 2)
        if ($value.Contains("'")) { throw "Use a literal value without embedded single quotes: $key" }
    } elseif ($value -match '[\$"\x27]' -or $value -match '\s#') {
        throw "Use an unquoted literal or single-quoted literal value: $key"
    }
    if ($value -match '[\r\n\x00]') { throw "Invalid environment value: $key" }
    $credentials[$key] = $value
}
foreach ($key in $requiredKeys) {
    if (-not $credentials.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($credentials[$key])) {
        throw "Missing environment key: $key"
    }
}
if ($credentials.RABBITMQ_USER.Contains(':')) { throw 'RABBITMQ_USER must not contain a colon.' }
if ($credentials.MINIO_ROOT_USER.Length -lt 3 -or $credentials.MINIO_ROOT_PASSWORD.Length -lt 8) {
    throw 'MinIO requires a username of at least 3 characters and password of at least 8 characters.'
}
if ($credentials.INTERNAL_TOKEN.Length -lt 16) { throw 'INTERNAL_TOKEN must have at least 16 characters.' }
try {
    if ([Convert]::FromBase64String($credentials.AUTH_JWT_SECRET).Length -lt 32) {
        throw 'AUTH_JWT_SECRET must decode to at least 32 bytes.'
    }
} catch [System.FormatException] {
    throw 'AUTH_JWT_SECRET must be valid base64.'
}
# Grafana credentials are needed only for the observability release; set both or neither.
$hasGrafanaUser = -not [string]::IsNullOrWhiteSpace($credentials.GRAFANA_ADMIN_USER)
$hasGrafanaPassword = -not [string]::IsNullOrWhiteSpace($credentials.GRAFANA_ADMIN_PASSWORD)
if ($hasGrafanaUser -ne $hasGrafanaPassword) { throw 'Set both GRAFANA_ADMIN_USER and GRAFANA_ADMIN_PASSWORD, or neither.' }

# Verify the selected context is the expected node before creating any resource.
$nodesJson = Invoke-LocalKubectl -KubectlArguments @('get', 'nodes', '-o', 'json')
$nodes = ($nodesJson | ConvertFrom-Json -AsHashtable).items
if ($nodes.Count -ne 1 -or $nodes[0].metadata.name -cne $nodeName) {
    throw 'Context does not point to the sagomungchi-local kind cluster.'
}

$dbUser = [Uri]::EscapeDataString($credentials.POSTGRES_USER)
$dbPassword = [Uri]::EscapeDataString($credentials.POSTGRES_PASSWORD)
$mqUser = [Uri]::EscapeDataString($credentials.RABBITMQ_USER)
$mqPassword = [Uri]::EscapeDataString($credentials.RABBITMQ_PASSWORD)
$reportDbUrl = "postgresql+psycopg://${dbUser}:${dbPassword}@postgres.platform.svc.cluster.local:5432/report_db"
$app = @{
    DB_USERNAME = $credentials.POSTGRES_USER
    DB_PASSWORD = $credentials.POSTGRES_PASSWORD
    RABBITMQ_USERNAME = $credentials.RABBITMQ_USER
    RABBITMQ_PASSWORD = $credentials.RABBITMQ_PASSWORD
    RABBITMQ_URL = "amqp://${mqUser}:${mqPassword}@rabbitmq.platform.svc.cluster.local:5672/"
    INTERNAL_TOKEN = $credentials.INTERNAL_TOKEN
    AUTH_JWT_SECRET = $credentials.AUTH_JWT_SECRET
    REPORT_DATABASE_URL = $reportDbUrl
    REPORT_ALEMBIC_DATABASE_URL = $reportDbUrl.Replace('%', '%%')
    MINIO_ROOT_USER = $credentials.MINIO_ROOT_USER
    MINIO_ROOT_PASSWORD = $credentials.MINIO_ROOT_PASSWORD
}
if ($credentials.OPENAI_API_KEY) { $app.OPENAI_API_KEY = $credentials.OPENAI_API_KEY }
# The platform Secret stays with create-platform-secret.ps1; both read the same .env.
$targets = @(@{Namespace = 'app'; Name = 'app-service-credentials'; Values = $app})
if ($hasGrafanaUser) {
    $targets += @{Namespace = 'observability'; Name = 'observability-credentials'; Values = @{
        GRAFANA_ADMIN_USER = $credentials.GRAFANA_ADMIN_USER
        GRAFANA_ADMIN_PASSWORD = $credentials.GRAFANA_ADMIN_PASSWORD
    }}
} else {
    Write-Output 'GRAFANA_ADMIN_USER is empty; observability/observability-credentials is skipped.'
}
foreach ($target in $targets) {
    $namespaceJson = Invoke-LocalKubectl -KubectlArguments @(
        'get', 'namespace', $target.Namespace, '--ignore-not-found', '-o', 'json'
    )
    if ([string]::IsNullOrWhiteSpace($namespaceJson)) {
        $manifest = @{apiVersion='v1'; kind='Namespace'; metadata=@{name=$target.Namespace}} |
            ConvertTo-Json -Depth 4 -Compress
        $null = Invoke-LocalKubectl -KubectlArguments @('create', '-f', '-') -InputJson $manifest
    }
}
# Compare every existing Secret before creating any new Secret.
foreach ($target in $targets) {
    $existingJson = Invoke-LocalKubectl -KubectlArguments @(
        '-n', $target.Namespace, 'get', 'secret', $target.Name, '--ignore-not-found', '-o', 'json'
    )
    if (-not [string]::IsNullOrWhiteSpace($existingJson)) {
        $existing = $existingJson | ConvertFrom-Json -AsHashtable
        foreach ($key in $target.Values.Keys) {
            $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($target.Values[$key]))
            if ($existing.data[$key] -cne $encoded) {
                throw "Existing $($target.Namespace)/$($target.Name) differs; no Secret was changed."
            }
        }
        $target.Existing = $true
    }
}
foreach ($target in $targets) {
    if ($target.Existing) {
        Write-Output "Secret $($target.Namespace)/$($target.Name) already matches."
        continue
    }
    $manifest = @{
        apiVersion = 'v1'
        kind = 'Secret'
        metadata = @{name=$target.Name; namespace=$target.Namespace}
        type = 'Opaque'
        stringData = $target.Values
    } | ConvertTo-Json -Depth 5 -Compress
    $null = Invoke-LocalKubectl -KubectlArguments @('create', '-f', '-') -InputJson $manifest
    Write-Output "Secret $($target.Namespace)/$($target.Name) created."
}
