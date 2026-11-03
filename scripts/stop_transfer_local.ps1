$ErrorActionPreference='Stop'
$trialRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$trialWebRoot=Join-Path $trialRoot 'frontend\web\node_modules'
$trialWebOwners=Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 5195 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
foreach($trialWebOwner in $trialWebOwners){
 $trialWebProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$trialWebOwner"
 if($trialWebProcess.Name -eq 'node.exe' -and $trialWebProcess.CommandLine -and $trialWebProcess.CommandLine.IndexOf($trialWebRoot,[StringComparison]::OrdinalIgnoreCase) -ge 0){
  Stop-Process -Id $trialWebOwner
 } else { Write-Warning '5195 포트의 실행 경로가 이 테스트 저장소와 달라 해당 프로세스는 유지합니다.' }
}
& docker compose -p guardian-transfer-289 --env-file (Join-Path $trialRoot 'infrastructure/stubs/e2e.env') -f (Join-Path $trialRoot 'compose.yaml') -f (Join-Path $trialRoot 'compose.minio.yaml') -f (Join-Path $trialRoot 'compose.e2e.yaml') -f (Join-Path $trialRoot 'compose.transfer-local.yaml') stop
if($LASTEXITCODE -ne 0){throw '격리 환경 중지 실패'}
Write-Output '이관 테스트 웹과 컨테이너를 중지했습니다. 테스트 볼륨과 기존 sagomungchi 환경은 보존됩니다.'
