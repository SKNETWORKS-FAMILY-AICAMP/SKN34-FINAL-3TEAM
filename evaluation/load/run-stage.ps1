# 부하 시험 한 단계 실행 (#361): k6 실행 → 같은 시간대의 서버 지표 수집. 결과는 RESULT_DIR에 저장한다.
# 사용: pwsh -File evaluation/load/run-stage.ps1 -Vus 10 -Secrets <비밀 파일> -ResultDir <결과 폴더> -Kubeconfig <AWS kubeconfig>
param(
    [Parameter(Mandatory)][int]$Vus,
    [Parameter(Mandatory)][string]$Secrets,
    [Parameter(Mandatory)][string]$ResultDir,
    [Parameter(Mandatory)][string]$Kubeconfig,
    [string]$Hold = '5m'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
New-Item -ItemType Directory -Force $ResultDir | Out-Null
$log = Join-Path $ResultDir ("k6-vus{0}.log" -f $Vus)
$start = Get-Date
# k6 출력에는 비밀 값이 없지만, 혹시 모를 헤더·쿠키 줄은 남기지 않는다.
& k6 run --no-usage-report -q -e LOAD_SECRETS=$Secrets -e RESULT_DIR=$ResultDir -e VUS=$Vus -e HOLD=$Hold (Join-Path $root 'core-load.js') 2>&1 |
    Where-Object { "$_" -notmatch 'Bearer|refresh=|student_device=|request timeout' } | Out-File -Encoding utf8 $log
$k6Exit = $LASTEXITCODE
$end = Get-Date
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
& python -I (Join-Path $root 'collect_metrics.py') --kubeconfig $Kubeconfig --start $start.ToString('o') --end $end.ToString('o') `
    --json (Join-Path $ResultDir ("server-vus{0}.json" -f $Vus)) | Out-File -Encoding utf8 -Append $log
"k6 exit $k6Exit  start $($start.ToString('o'))  end $($end.ToString('o'))" | Out-File -Encoding utf8 -Append $log
exit $k6Exit
