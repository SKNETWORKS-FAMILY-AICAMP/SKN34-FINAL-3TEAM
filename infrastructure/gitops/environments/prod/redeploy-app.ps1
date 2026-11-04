#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('core-service','learning-service','ai-service','scoring-service','report-api','report-worker')][string]$Service,
    [Parameter(Mandatory)][string]$Kubeconfig,
    [string]$Helm = 'helm',
    [string]$Profile = 'sagomungchi-provided',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$valuesPath = Join-Path $PSScriptRoot "$Service.json"
$chart = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../charts/app-service'))
$values = Get-Content -LiteralPath $valuesPath -Raw | ConvertFrom-Json
if ($values.image.repository -notlike '347161580747.dkr.ecr.ap-northeast-2.amazonaws.com/*' -or $values.image.digest -notmatch '^sha256:[a-f0-9]{64}$') {
    throw 'Expected the demo ECR account and a pinned image digest'
}
$account = & aws sts get-caller-identity --profile $Profile --query Account --output text
if ($LASTEXITCODE -ne 0 -or $account.Trim() -ne '347161580747') { throw 'Unexpected AWS account' }
$endpoint = & aws eks describe-cluster --name sagomungchi-demo-eks --region ap-northeast-2 --profile $Profile --query cluster.endpoint --output text
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve expected EKS endpoint' }
$configured = & kubectl --kubeconfig $Kubeconfig config view --minify -o json
if ($LASTEXITCODE -ne 0 -or ($configured | ConvertFrom-Json).clusters[0].cluster.server -ne $endpoint.Trim()) { throw 'Unexpected kubeconfig endpoint' }
$release = & $Helm status $Service -n app --kubeconfig $Kubeconfig -o json
if ($LASTEXITCODE -ne 0 -or ($release | ConvertFrom-Json).info.status -ne 'deployed') { throw 'Only an existing deployed app release can be redeployed' }
& $Helm lint $chart -f $valuesPath
if ($LASTEXITCODE -ne 0) { throw 'Helm lint failed' }
# No Secret values are supplied to this command. Dry-run does not apply resources.
if (-not $Apply) {
    & $Helm upgrade $Service $chart -n app --kubeconfig $Kubeconfig -f $valuesPath --dry-run=server --hide-secret
    if ($LASTEXITCODE -ne 0) { throw 'Helm server dry-run failed' }
    Write-Output 'Preview only. Review image, Pod changes, capacity and Secret readiness before using -Apply.'
    return
}
& kubectl --kubeconfig $Kubeconfig -n app wait --for=condition=Ready externalsecret --all --timeout=60s
if ($LASTEXITCODE -ne 0) { throw 'External Secrets are not ready' }
& $Helm upgrade $Service $chart -n app --kubeconfig $Kubeconfig -f $valuesPath --wait --timeout 10m
if ($LASTEXITCODE -ne 0) { throw 'Deployment failed; inspect the release before retrying. No automatic rollback was attempted.' }
& kubectl --kubeconfig $Kubeconfig -n app rollout status "deployment/$Service" --timeout=60s
if ($LASTEXITCODE -ne 0) { throw 'Deployment rollout did not complete' }
