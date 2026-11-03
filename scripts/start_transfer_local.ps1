param([switch]$SkipBuild)
$ErrorActionPreference='Stop'
$trialRoot=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$composeArgs=@('compose','-p','guardian-transfer-289','--env-file',(Join-Path $trialRoot 'infrastructure/stubs/e2e.env'),'-f',(Join-Path $trialRoot 'compose.yaml'),'-f',(Join-Path $trialRoot 'compose.minio.yaml'),'-f',(Join-Path $trialRoot 'compose.e2e.yaml'),'-f',(Join-Path $trialRoot 'compose.transfer-local.yaml'))
$configJson=& docker @composeArgs config --format json
if($LASTEXITCODE -ne 0){throw 'Compose 설정 검사 실패'}
$config=$configJson|ConvertFrom-Json
if($config.name -ne 'guardian-transfer-289'){throw '격리 프로젝트 이름 불일치'}
foreach($property in $config.volumes.PSObject.Properties){
 if($property.Value.external -or -not $property.Value.name.StartsWith('guardian-transfer-289_')){throw '공유 볼륨 사용 금지'}
}
foreach($property in $config.services.PSObject.Properties){
 foreach($port in $property.Value.ports){if($port.host_ip -ne '127.0.0.1'){throw '테스트 포트는 loopback에만 공개해야 합니다.'}}
}
$up=@('up','-d','--wait','--wait-timeout','240')
if(-not $SkipBuild){$up+='--build'}
& docker @composeArgs @up core-service learning-service ai-service report-api report-worker
if($LASTEXITCODE -ne 0){throw '격리 테스트 환경 시작 실패'}
Write-Output 'API 준비: http://127.0.0.1:18095/actuator/health/readiness'
Write-Output '프론트 실행: scripts/start_transfer_web.ps1'
