#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('core-service','learning-service','ai-service','scoring-service','report-api','report-worker')][string]$Service,
    [Parameter(Mandatory)][string]$Kubeconfig,
    [string]$Helm = 'helm',
    [string]$Kubectl = 'kubectl',
    [string]$Aws = 'aws',
    [string]$Profile = 'sagomungchi-provided',
    # #186 승인된 배포: 저장소 이미지 파일(images/<Service>.json)은 두고 이 digest로 바꾼 임시 사본을 사용한다
    [ValidatePattern('^sha256:[a-f0-9]{64}$')][string]$ImageDigest,
    # migration Job(설정 파일의 migration.enabled=true인 서비스)만 다룬다. 앱 release는 바꾸지 않는다
    [switch]$Migration,
    # migration Job 이름 접미사(cd-release는 main-<SHA 12자리>). 생략하면 저장소 값
    [ValidatePattern('^[a-z0-9]([a-z0-9-]{0,38}[a-z0-9])?$')][string]$Revision,
    # 결과를 남길 JSON 경로. migration은 release·Job·digest·상태, 앱은 release·digest·install/upgrade·전후 revision·상태.
    # 로그·비밀은 넣지 않는다
    [string]$ResultPath,
    [int]$MigrationTimeoutSeconds = 660,
    # #760 빈 클러스터 첫 배포: 앱 release가 없을 때만 helm install(미리보기)·upgrade --install(적용)로 올린다.
    # 이 스위치가 없으면 지금처럼 기존 deployed release만 다룬다(cd-release는 계획 currentRelease가 "none"일 때만 준다)
    [switch]$AllowInstall,
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
# #857 값은 설정 파일 <Service>.json + 이미지 파일 images/<Service>.json(Argo CD ApplicationSet과 같은 조합)
$valuesPath = Join-Path $PSScriptRoot "$Service.json"
$imagesPath = Join-Path $PSScriptRoot "images/$Service.json"
$chart = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../../charts/app-service'))
$values = Get-Content -LiteralPath $valuesPath -Raw | ConvertFrom-Json
$images = Get-Content -LiteralPath $imagesPath -Raw | ConvertFrom-Json

function Write-TempValues($Object, $Name) {
    $path = Join-Path ([IO.Path]::GetTempPath()) "cd-$Name-$([guid]::NewGuid()).json"
    $Object | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $path -Encoding utf8
    return $path
}

if ($Migration) {
    if ($AllowInstall) { throw '-AllowInstall is only for app releases' }
    if (-not $values.migration.enabled -or -not $images.migration) { throw "No migration values for $Service" }
    if ($ImageDigest) { $images.migration.image.digest = $ImageDigest }
    if ($Revision) { $images.migration.revision = $Revision }
    $image = $images.migration.image
} else {
    if ($Revision) { throw '-Revision is only for -Migration' }
    if ($ImageDigest) { $images.image.digest = $ImageDigest }
    $image = $images.image
}
if ($ImageDigest -or $Revision) { $imagesPath = Write-TempValues $images "$Service-images" }
# 앱 release에는 migration Job·정책을 넣지 않는다(Helm은 PreSync 훅을 모르므로 일반 리소스가 된다). Job은 -Migration으로 먼저 돈다
$appValues = @('-f', $valuesPath, '-f', $imagesPath, '--set', 'migration.enabled=false')
if ($image.repository -notlike '347161580747.dkr.ecr.ap-northeast-2.amazonaws.com/*' -or $image.digest -notmatch '^sha256:[a-f0-9]{64}$') {
    throw 'Expected the demo ECR account and a pinned image digest'
}
$account = & $Aws sts get-caller-identity --profile $Profile --query Account --output text
if ($LASTEXITCODE -ne 0 -or "$account".Trim() -ne '347161580747') { throw 'Unexpected AWS account' }
$endpoint = & $Aws eks describe-cluster --name sagomungchi-demo-eks --region ap-northeast-2 --profile $Profile --query cluster.endpoint --output text
if ($LASTEXITCODE -ne 0) { throw 'Cannot resolve expected EKS endpoint' }
$configured = & $Kubectl --kubeconfig $Kubeconfig config view --minify -o json
if ($LASTEXITCODE -ne 0 -or (($configured -join "`n") | ConvertFrom-Json).clusters[0].cluster.server -ne "$endpoint".Trim()) { throw 'Unexpected kubeconfig endpoint' }

if ($Migration) {
    # Argo PreSync 대신 NetworkPolicy(wave -2)와 Job(wave -1)만 그 순서로 렌더링해 앱보다 먼저 적용한다(prod README 3절).
    # 앱 release가 아직 없는 빈 클러스터에서도 쓸 수 있도록 release 상태는 보지 않는다.
    & $Helm lint $chart -f $valuesPath -f $imagesPath
    if ($LASTEXITCODE -ne 0) { throw 'Helm lint failed' }
    $rendered = & $Helm template $Service $chart -n app -f $valuesPath -f $imagesPath `
        --show-only templates/migration-networkpolicy.yaml --show-only templates/migration-job.yaml
    if ($LASTEXITCODE -ne 0) { throw 'Migration render failed' }
    $manifest = Join-Path ([IO.Path]::GetTempPath()) "cd-$Service-migration-$([guid]::NewGuid()).yaml"
    $rendered | Set-Content -LiteralPath $manifest -Encoding utf8
    $jobMatch = [regex]::Match(($rendered -join "`n"), '(?m)^kind: Job\s*\r?\nmetadata:\s*\r?\n\s+name: (\S+)')
    if (-not $jobMatch.Success) { throw 'Migration Job is not rendered (migration.enabled?)' }
    $job = $jobMatch.Groups[1].Value
    $result = [ordered]@{
        release = $Service; job = $job; revision = $images.migration.revision
        image = "$($image.repository)@$($image.digest)"; status = 'pending'
    }
    function Save-Result($Status) {
        $result.status = $Status
        if ($ResultPath) { [pscustomobject]$result | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding utf8 }
    }
    function Get-JobState {
        $json = & $Kubectl --kubeconfig $Kubeconfig -n app get job $job -o json --ignore-not-found
        if ($LASTEXITCODE -ne 0) { throw "Cannot read job/$job" }
        if (-not $json) { return 'absent' }
        $conditions = @((($json -join "`n") | ConvertFrom-Json).status.conditions | Where-Object { $_.status -eq 'True' })
        if ($conditions.type -contains 'Failed') { return 'failed' }
        if ($conditions.type -contains 'Complete') { return 'complete' }
        return 'running'
    }
    # Job 이름은 revision마다 하나다. 같은 SHA 재실행은 성공한 Job을 다시 만들지 않는다
    $state = Get-JobState
    if ($state -eq 'complete') {
        Save-Result 'already-complete'
        Write-Output "job/$job already completed. Nothing to apply."
        return
    }
    if ($state -eq 'failed') {
        Save-Result 'failed'
        throw "job/$job already failed. Inspect it on the operator PC (kubectl -n app logs job/$job) before retrying with a new plan."
    }
    if (-not $Apply) {
        if ($state -eq 'absent') {
            & $Kubectl --kubeconfig $Kubeconfig -n app apply --dry-run=server -f $manifest
            if ($LASTEXITCODE -ne 0) { throw 'Migration server dry-run failed' }
        }
        Save-Result "preview-$state"
        Write-Output "Preview only. job/$job ($state) runs before the app release."
        return
    }
    & $Kubectl --kubeconfig $Kubeconfig -n app wait --for=condition=Ready externalsecret --all --timeout=60s
    if ($LASTEXITCODE -ne 0) { Save-Result 'failed'; throw 'External Secrets are not ready' }
    if ($state -eq 'absent') {
        & $Kubectl --kubeconfig $Kubeconfig -n app apply -f $manifest
        if ($LASTEXITCODE -ne 0) { Save-Result 'failed'; throw "Cannot create job/$job" }
    }
    # backoffLimit 1, activeDeadlineSeconds 600(chart). 실패 조건을 바로 보려고 직접 기다린다
    $deadline = (Get-Date).AddSeconds($MigrationTimeoutSeconds)
    do {
        Start-Sleep -Seconds 5
        $state = Get-JobState
    } while ($state -eq 'running' -and (Get-Date) -lt $deadline)
    if ($state -ne 'complete') {
        Save-Result $(if ($state -eq 'running') { 'timeout' } else { 'failed' })
        # Job 로그는 공개 Actions 로그에 남기지 않는다. 작업자 PC에서 확인한다
        throw "job/$job did not complete ($state). Inspect it on the operator PC (kubectl -n app logs job/$job). The app release was not changed and the DB is not rolled back."
    }
    Save-Result 'complete'
    Write-Output "job/$job completed."
    return
}

function Get-AppRelease {
    # helm status는 release가 없을 때와 접속 실패를 같은 종료 코드로 돌려주므로 목록에서 찾는다.
    # 상태 필터는 Helm 3·4 공통 플래그로 명시한다(Helm 4에는 -a가 없음). 실패·진행 중 release도 보이게 한다
    $json = & $Helm list -n app --kubeconfig $Kubeconfig --deployed --failed --pending --uninstalling -o json --filter "^$Service$"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot read app releases' }
    return @(($json -join "`n") | ConvertFrom-Json) | Where-Object { $_.name -eq $Service } | Select-Object -First 1
}
$current = Get-AppRelease
$install = -not $current
if ($install -and -not $AllowInstall) {
    throw "No app release $Service in namespace app. A first install on an empty cluster needs -AllowInstall (cd-release: plan currentRelease ""none"")."
}
if (-not $install -and $current.status -ne 'deployed') { throw 'Only an existing deployed app release can be redeployed' }
$action = if ($install) { 'install' } else { 'upgrade' }
$appResult = [ordered]@{
    release = $Service; digest = $image.digest; action = $action
    previousRevision = $(if ($install) { $null } else { [int]$current.revision }); revision = $null; status = 'pending'
}
function Save-AppResult($Status) {
    $appResult.status = $Status
    if ($ResultPath) { [pscustomobject]$appResult | ConvertTo-Json | Set-Content -LiteralPath $ResultPath -Encoding utf8 }
}
& $Helm lint $chart @appValues
if ($LASTEXITCODE -ne 0) { throw 'Helm lint failed' }
# No Secret values are supplied to this command. Dry-run does not apply resources.
if (-not $Apply) {
    if ($install) {
        & $Helm install $Service $chart -n app --kubeconfig $Kubeconfig @appValues --dry-run=server --hide-secret
    } else {
        & $Helm upgrade $Service $chart -n app --kubeconfig $Kubeconfig @appValues --dry-run=server --hide-secret
    }
    if ($LASTEXITCODE -ne 0) { throw 'Helm server dry-run failed' }
    Save-AppResult "preview-$action"
    if ($install) { Write-Output "First install: no $Service release yet. -Apply installs it (cd-release does it after the migrations)." }
    Write-Output 'Preview only. Review image, Pod changes, capacity and Secret readiness before using -Apply.'
    return
}
& $Kubectl --kubeconfig $Kubeconfig -n app wait --for=condition=Ready externalsecret --all --timeout=60s
if ($LASTEXITCODE -ne 0) { Save-AppResult 'failed'; throw 'External Secrets are not ready' }
if ($install) {
    # 미리보기와 적용 사이에 같은 release가 먼저 생겼더라도 같은 values로 수렴하도록 upgrade --install을 쓴다
    & $Helm upgrade --install $Service $chart -n app --kubeconfig $Kubeconfig @appValues --wait --timeout 10m
} else {
    & $Helm upgrade $Service $chart -n app --kubeconfig $Kubeconfig @appValues --wait --timeout 10m
}
$deployed = $LASTEXITCODE -eq 0
$after = Get-AppRelease
if ($after) { $appResult.revision = [int]$after.revision }
if (-not $deployed) { Save-AppResult 'failed'; throw 'Deployment failed; inspect the release before retrying. No automatic rollback was attempted.' }
& $Kubectl --kubeconfig $Kubeconfig -n app rollout status "deployment/$Service" --timeout=60s
if ($LASTEXITCODE -ne 0) { Save-AppResult 'failed'; throw 'Deployment rollout did not complete' }
Save-AppResult $after.status
if ($install) { Write-Output "First install of $Service completed (revision $($appResult.revision))." }
