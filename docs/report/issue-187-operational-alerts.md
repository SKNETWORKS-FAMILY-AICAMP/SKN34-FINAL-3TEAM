# #187 운영 경보와 요청·오류 추적

## 기준과 구현 범위

2026-11-01, develop `9fbda174f4ea76218cd3b2a4f315b624f12a2884`에서 분리한
`feature/infra-operational-alerts`. #171 PR #204는 open, head
`4787b523828883c6cb2dd4c5732133cb94dd3952`를 읽기 전용으로 대조했다.
#171 worktree/index/cluster는 수정하지 않았다. 미병합 #171 head를 merge/cherry-pick하지 않았다.
이후 2026-11-01 19:10 KST에 PR #204가 병합되어 `origin/develop`을 fetch한 뒤
`git merge --no-edit origin/develop`으로 `b35e381aa37cf22b5816d2750b46d18f2c11fa5c`까지 fast-forward했다.
별도 cherry-pick·rebase·이력 재작성은 없으며 #171 변경은 base와 동일하다.
현재 추가 파일은 [설계](../design/operational-alerts.md)와 독립 경보 생성기·검증기다.
이후 사용자에게 기반영 chart의 opt-in 연결 범위와 영향을 설명하고 명시 허락을 받아
기존 observability chart의 values·ConfigMap·Deployment와 README만 최소 수정했다.
앱·공개 계약·사용자 공지·NetworkPolicy는 변경하지 않았다.

#171 values/templates 기준: Collector 0.164.0 OTLP 4317/4318→8889,
Prometheus 3.15.1의 15초 scrape job `otel-collector`·`rabbitmq`, RabbitMQ 4.3.7의 15692 `/metrics`,
Grafana 13.3.0의 이름 Prometheus datasource. UID는 고정되지 않았다.
local trace=false, Prometheus retention=1d, Grafana/Prometheus emptyDir다.
보고서 마지막 완료 기록의 JVM/HTTP 집계 수집·Argo Healthy는 인정하되,
업무별 라벨·지연 histogram·실제 Langfuse 저장 또는 #203 learning 이미지 재검증으로 확대 해석하지 않는다.

## 요구사항·지표·판정 대조

| 요구 | 실제 공급/라벨·범위·단위 | 조건·지속 | NoData/오류 | 대상·상태 |
|---|---|---|---|---|
| NFR-OPS-04 수집 장애 | Prometheus `up`, job/instance; target별 0/1 | `1-up` 또는 job 부재 `absent` >0; 지속 필수 입력 | NoData/Error 별도 상태 | rabbitmq→service=rabbitmq, Collector→observability; 독립 규칙 준비 |
| 작업 적체 | `rabbitmq_queue_messages_ready{job="rabbitmq"}`, 기본 endpoint의 전체 집계 gauge; 메시지 건수 | sum > 필수 입력 임계값; 지속 필수 입력 | 지표 부재는 NoData, query 실패 Error | rabbitmq 인프라 신호; 독립 규칙 준비 |
| DLQ 적재 | 현재 기본 집계에는 queue 라벨 없음 | 현재 구현 불가 | 0으로 치환하지 않음 | 후속 detailed scrape+큐 목록 대조 |
| 인증/학습 저장/AI/리포트/결제 오류율·지연 | core·learning JVM 및 HTTP 집계 수집 기록만 존재; endpoint/status/단위/histogram 실측 미확정, 나머지 공급 공백 | 업무별 분모·오류 정의·bucket·최소 표본·지속 미정 | 결측을 정상 처리하지 않음 | 각 생산 서비스 계측 확인 후 추가; JVM으로 대체하지 않음 |
| FN-ADM-19/P13 월 비용 80% | core usage HTTP API, 비용 USD/null·unpricedCalls; 현재 Prometheus 공급 없음 | 80%만 확정; 예산/월 경계 미정 | null을 0으로 합산하지 않음 | 비활성·별도 설계/승인 대기 |
| NFR-OPS-05 실패 요청 추적 | HTTP·event traceparent 전달 코드; 실제 저장 backend 미검증 | 실패 요청→업무 ID→동기/비동기 span 조회 필요 | 저장 실패를 trace 완료로 취급하지 않음 | #171/#185 환경 후속 |

운영 임계값·지속시간·알림 간격은 문서에 없다. 모두 설정 필수 입력이며 숨겨진 기본값이 없다.
규칙의 warning severity는 초안 분류이며 운영 활성화 전 담당자 검토 대상이다.
시험 backlog 10건/10초 지속·10초 평가/1초 wait/10초 grouping/300초 repeat는 빠른 분기 검증용이다.
운영 제안은 실제 적체량·처리속도·장애 탐지 목표를 측정한 후 결정해야 한다.
전체 ready 메시지는 retry/DLQ도 포함하고 수평 노드 합산은 현재 단일 RabbitMQ target 기준이다.
향후 cluster/queue 유형별 중복 집계 여부를 확인하기 전 다중 노드에 그대로 확대하지 않는다.

## 별도 결정·후속 목록

### A. 월 LLM 비용

- 확정 필요: 예산 금액·통화·월 경계·시간대·승인 담당. 80%만 정책으로 확정돼 있다.
- api-spec 4.6: KST 양끝 날짜 포함, calls/failures/평균 latencyMs/토큰/costUsd/unpricedCalls.
  미산정 비용이 하나라도 있으면 costUsd=null, 빈 결과 items=[]이며 0 비용으로 치환하지 않는다.
- 저장된 소비 시점 USD 비용과 이벤트 멱등 처리의 합계다. best-effort 발행 유실은 현재 완전성 보장이 없다.
  환율·미등록 단가·누락·중복 보정·뒤늦은 수집·월 rollover를 정의해야 한다.
- 새 exporter/주기 실행 계층을 만들지 않았다. 필요 시 core usage 소유 경계에서 공급 방식·권한·의존성을
  별도 설계하고 production 변경 승인을 받아야 한다. 관리자 API를 무인 polling하는 계층을 임의 추가하지 않는다.

### B. 담당·연락처·라우팅

- 인프라 1명+서비스별 담당 구조만 확정. 실명·Discord 멘션·온콜·승인자는 미확정이다.
- 현재 규칙은 service/environment로 분류하고 전용 contact point에 직접 라우팅한다.
  조직 전체 policy tree를 덮어쓰지 않는다. 담당 확정 후 service별 연락처를 연결한다.
- 실제 Secret 이름/키·Discord 채널, HTTPS egress 허용 범위·운영 interval 승인이 필요하다.
  webhook 값은 Git·설정 입력·문서·명령 인자에 저장하지 않는다.
- 팀 채널 시험 발송은 대상과 시험 발송에 대한 명시 허락 후 별도 수행한다.

### C. 실패 요청 trace

- core PublicAuthFilter→UserContext→InternalRestClientFactory, Python security.UserContext→clients/base에서
  HTTP traceparent를 전달한다. EventEnvelope에 nullable traceparent가 있고 report generation consumer→context→
  service→codec에서 결과 이벤트까지 전달한다. 전달 가능성과 실제 모든 생산자가 채운다는 보장은 구분한다.
- core Problems/Python errors는 헤더가 없을 때 오류 trace ID를 생성한다. 오류 ID 생성만으로
  incoming context 시작·outgoing parent span·OTLP export·영구 저장이 완성되지 않는다.
- #171은 Java agent·AI Langfuse SDK를 제공하지만 local trace=false이고 실제 저장·조회는 #185/#171 후속이다.
  병합 코드를 재대조하면 AI LlmClient는 유효한 traceparent를 SDK trace_id/parent_span_id에 연결하고,
  UsagePublisher도 현재 UserContext의 traceparent를 이벤트에 넣는다. context가 없으면 nullable이며,
  ai 보고서의 과거 '공통 UsagePublisher가 받지 않아 null' 기록을 현재 구현으로 해석하지 않는다.
- 필요 확인: 학습 attempt/answer, conversation/job, report job, payment transaction의 내부 상관 키와
  span 연결, 비동기 consumer context 복원·실패 span 상태·export 재시도·저장 권한/보존 기간.
  원문·결제 정보·Secret은 span/alert label에 넣지 않는다. 고카디널리티 업무 ID를 alert label에 넣지 않는다.
- 시나리오: 합성 업무 ID로 HTTP 실패→관련 작업→메시지 소비 실패→DLQ를 유발하고
  동일 trace 및 부모/자식 또는 명시적 link를 backend에서 조회한다. 결제 외부 경계와 SSE 종료,
  헤더 없는 요청·재시도·저장 장애·민감 정보 비포함도 각각 검증한다. 지금 단일 trace 완료를 주장하지 않는다.

### #171 연결

최신 develop 병합과 사용자 허락에 따른 기존 chart의 ConfigMap·mount·Secret 참조·빈 값 guard·datasource UID 입력 연결을 완료했다.
활성화 values는 생성기 CLI가 동일 provisioning·UID·Secret 참조로 만든다. 기본 비활성이고 local/Argo는 활성화하지 않았다.
실제 datasource UID와 namespace, Grafana 시작 명령,
NetworkPolicy DNS/Prometheus 보존 및 Discord 443 egress를 확인한다.
DLQ는 `/metrics/detailed`의 필요한 queue family만 별도 job으로 scrape하고
queue/vhost 라벨·definitions.json의 명시 큐 목록·시계열 비용을 확인한 후 추가한다.
#171 기본 scrape 변경이나 전체 per-object 활성화를 몰래 수행하지 않는다.
Helm render·실제 Pod Secret 누락·반복 sync·규칙 평가·운영 수신을 통합 검증해야 한다.
chart의 선택 연결만 추가한 상태이며 배포/운영 경보 활성화 상태가 아니다.

## 최종 검증 (2026-11-01)

환경: Python 3.12.10, 검증용 PyYAML 6.0.3, Helm `v4.3.1+gc0d08d0`.
실행 명령: `python infrastructure/gitops/operational-alerts/verify_chart.py --helm <Helm-4.3.1-실행파일>`.
이 명령은 exit 0으로 완료됐고, 뒤이어 `git diff --check`가 통과했다.
신규 파일을 포함한 staged diff check와 최종 Git 상태는 커밋 직전 별도로 확인한다.

| 실제 실행 범위 | 결과 |
|---|---|
| Helm lint, default/local 비활성 리소스와 병합 #171 SHA의 의미적 비교 | 통과, 기존 리소스 동일 |
| 생성기 CLI→helm-values→ConfigMap/mount/Secret/UID 연결 | 통과 |
| Helm Secret 참조/provisioning 누락, datasource UID 불일치 | 의도대로 렌더 실패 |
| RabbitMQ 4.3.7 실제 endpoint gauge/type 및 queue 라벨 부재 | 확인 |
| chart가 렌더한 실제 provisioning/datasource로 Grafana 13.3.0 기동·Prometheus 3.15.1 평가 | 통과 |
| 정상→pending→발생→유지→회복 | 통과 |
| Discord integration의 로컬 protocol 대역 발생·회복 수신 | 통과, 팀 채널 수신과 구분 |
| 20초 유지 중 반복 억제 | 통과, 300초 repeat 전체 기간 시험은 아님 |
| NoData·잘못된 query의 별도 상태와 로컬 오류 알림 수신 | 통과 |
| 잘못된 datasource UID의 새 평가 오류 | 통과 |
| webhook 환경 누락 시작 차단 | 통과, Kubernetes 실제 Secret 누락 Pod 시험은 아님 |
| provisioning 반복 reload 후 규칙 3개/contact UID 1개 유지 | 통과 |
| 실제 target 접속 실패와 job 제거 시 absent 분기 | 통과 |

job 제거 시험은 Prometheus lookback을 시험 전용 10초로 지정했다.
#171 운영 기본 설정에서는 기본 5분 lookback의 잔존값과 pending·알림 대기가 더해질 수 있다.
이는 운영 탐지 시간 보장이나 응답시간 측정 결과가 아니다.

초기 시험은 내부 network의 호스트 port 조회, 시험 Grafana min_interval, datasource 파일 확장자,
rules API의 NoData 상태 기대값, Windows UTF-8 출력 처리와 job 제거 대기 설정 문제로 실패했다.
시험기를 수정하고 실패 범위를 재검증한 뒤 최종 chart 통합 명령 전체를 통과했다.
규칙 평가 전 초기 health=ok만으로 정상 판정하지 않고 실제 lastEvaluation도 확인한다.

현재 시험은 고유 container/internal network, host 포트 미노출, Prometheus tmpfs와 container `rm -v`를 사용한다.
기존 kind·다른 작업 container·Secret·PVC는 변경하지 않았다. 마지막 실행의 본인 container/network는 정리됐다.
초기 실패 실행 시각에 생성된 dangling 익명 volume 후보 8개는 소유 이벤트가 남아 있지 않아 삭제하지 않았다.
mount 이벤트로 본인 소유가 확인된 별도 시험 volume 1개만 정확한 ID로 제거했다. 대량 prune은 수행하지 않았다.

실제 Kubernetes 적용·Secret 누락 Pod 상태·NetworkPolicy 허용 검증·팀 Discord 수신·AWS·Langfuse는 미검증이다.
local/Argo 경보는 비활성이고 원격 CI·배포 결과로 해석하지 않는다.
#187 전체 완료 조건과 이슈 종료는 보류한다. 예산·담당·업무별 지표·DLQ 라벨·trace 저장/조회·운영 발송은 위 후속 목록을 따른다.
