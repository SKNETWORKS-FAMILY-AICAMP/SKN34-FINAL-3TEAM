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
| DLQ 적재 | 기본 집계에는 queue 라벨 없음 → 2026-11-03 opt-in `rabbitmq-dlq` job이 `/metrics/detailed` queue_coarse_metrics에서 `<큐>.dlq`의 `rabbitmq_detailed_queue_messages{vhost,queue}`만 수집; 메시지 건수 | 큐별 max > 규칙 임계값(2026-11-04부터 #185 `rules` 항목); 지속은 규칙 `for` | 지표 부재는 NoData, 0으로 치환하지 않음 | rabbitmq 인프라 신호, 큐별 경보 인스턴스; 규칙 준비(운영 임계값 미정) |
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

## 최신 develop 반영과 후속 대조 (2026-11-02)

작업 시작 시 `feature/infra-operational-alerts`는 clean이고 기존 기능 커밋 `24f5b9705efe112e0b546a7dff77e1ee05192e8e`가 보존돼 있었다.
origin의 기존 head 브랜치 PR 검색 결과는 없었고 #187은 open, 댓글 0개로 새 정책 결정이 등록되지 않았다.
fetch한 develop `26948215fa8c5e4b5308db26e2d5fbb378db57f9`와 이력이 분기되어
`git merge --no-edit origin/develop`으로 merge commit `e25ca04f3fe54c6a1b1416398fc9403c750a13db`를 만들었다.
충돌은 없었고 rebase·reset·force push 없이 기존 기능 커밋과 develop 변경을 보존했다.

이전 기준 `b35e381`부터 최신 develop까지 `infrastructure/gitops/`, AI Langfuse 설정·LLM 계측·사용량 publisher 변경은 없었다.
AI 메시징 연결 파일의 변경은 Pod별 exclusive 큐 선언 예외를 설명하는 주석 정정이며 경보 지표·trace backend를 추가하지 않았다.
architecture 4.6과 API 4.6을 다시 대조했으며 local traces=false, queue 라벨 부재,
업무별 오류율·지연 수집 공백, 비용 null/미산정 의미와 예산·담당 미확정 조건은 유지된다.
따라서 추가 운영 규칙이나 exporter·외부 서비스·AWS 자원·HTTPS egress·실채널 발송을 임의 추가하지 않았다.

승인 범위 내 독립 보완으로 검증기에 `--baseline`을 추가했다. 전달한 ref를 실제 commit SHA로 고정하고
현재 HEAD의 ancestor인지 검사한 뒤 해당 기준의 chart와 비활성 리소스를 비교한다.
최초 #171 기준은 기본값으로 유지하고, 이번 재검증에는 최신 develop SHA를 명시한다.
production chart·공개 계약·기존 앱 로직은 이번 재개 작업에서 추가 수정하지 않았다.

최종 명령은 `python infrastructure/gitops/operational-alerts/verify_chart.py --helm <Helm-4.3.1-실행파일> --baseline 26948215fa8c5e4b5308db26e2d5fbb378db57f9`이며 exit 0으로 완료됐다.
최신 develop의 default/local 비활성 리소스 동일성, 생성기→chart UID/mount/Secret 연결,
필수 입력 오류 시 Helm 실패, 실제 RabbitMQ 지표, Grafana/Prometheus 정상→발생→유지→회복,
로컬 대역 발생·회복/NoData/조회 오류 수신, 잘못된 datasource UID,
재적용 중복 방지, target 장애와 job 제거 경보를 모두 통과했다.
이번 검증은 앞 절과 같은 시험 전용 임계값·10초 lookback을 사용했다.
최종 `git diff --check`와 문서 상대 링크를 확인하며, 시험 container/network는 종료 후 남지 않았다.
기존 kind·다른 작업 자원·이전 익명 volume 후보는 변경하지 않았다.

예산·담당·운영 임계값·실제 Discord 수신 및 trace 저장/조회 결정 대기는 계속 유지한다.
실제 Kubernetes 적용·AWS 자원 생성·외부 전송·Langfuse 저장 검증·원격 CI는 이번 로컬 시험에 포함하지 않는다.
PR 생성이나 #187 종료는 수행하지 않았다.

## 담당 전환 후 최신 develop 반영과 DLQ 적재 규칙 (2026-11-03)

2026-11-03 담당 결정에 따라 #185를 제외한 인수인계 이슈를 이어서 진행한다. 기존 기능 커밋 `24f5b97`·`e25ca04`·`ab0f412`를 보존한 채
develop `e65c9726cb7cc78e59649e2489766f2bb8a6e4b9`를 `git merge --no-edit`로 반영했다(merge commit `706644f`, 충돌 없음, rebase·reset·force push 없음).

### 전제 재대조

| 전제 | 최신 develop 결과 |
|---|---|
| observability chart 기본 동작 | develop 쪽 변경 없음. 기본/local 렌더가 새 기준 SHA와 리소스 단위로 동일 |
| local traces=false, local Langfuse 없음 | 유지(`environments/local/observability.yaml`, chart values) |
| 업무별 오류율·지연 지표 | backend 변경에 Micrometer·OTel span·histogram 추가 없음. 공급 공백 유지 |
| 월 LLM 비용 공급 | #225 사용량 DB는 분석 대화 사용량 제한이며 Prometheus 공급·예산 결정 아님. 공백 유지 |
| 기본 RabbitMQ 집계의 queue 라벨 부재 | 유지. 대신 `/metrics/detailed`에는 큐 라벨이 있음을 kind에서 확인 |
| 큐 정의 | #208로 `core.event.audit` 계열이 추가되어 `<큐>.dlq`는 6개 |
| kind(#273·#236) | 같은 `sagomungchi-local` 클러스터에 관측 설치 절차가 있으나 `observability` namespace 미설치 |
| #187 이슈 | open, 예산·담당 확인 필요 항목 결정 등록 없음 |

### 구현

- observability chart `prometheus.rabbitmqDlqMetrics.enabled`(기본 false): 기존 `rabbitmq` job은 그대로 두고 같은 15692 포트의
  `/metrics/detailed?family=queue_coarse_metrics`를 `rabbitmq-dlq` job으로 수집한다. metric relabel로
  `rabbitmq_detailed_queue_messages` 중 `<큐>.dlq`만 남긴다. 기존 Prometheus→RabbitMQ 15692 NetworkPolicy 범위 안이다.
- 생성기 규칙 `ops187-rabbitmq-dlq`: `max by (vhost, queue)`로 큐마다 경보 인스턴스, 임계값 `dlq_messages`는 필수 입력(0 허용),
  지속·평가·알림 간격은 기존 공통 필수 입력을 따른다. 숨은 기본값이 없고 생략하면 생성기가 거부한다.
- 생성된 `helm-values.json`이 DLQ scrape를 함께 켠다. DLQ 규칙이 있는데 scrape가 꺼져 있으면 Helm 렌더가 실패한다.
- 메시지 수는 ready+unacked 합계다. 메시지 나이·재처리 지연을 뜻하지 않고 업무 ID·메시지 내용은 label에 넣지 않는다.
  quorum 큐의 다중 노드 보고 방식은 단일 노드 기준으로만 확인했으므로 다중 노드 확대 전 재확인한다.

### 검증

| 범위 | 방식 | 결과 |
|---|---|---|
| kind `sagomungchi-local`의 실제 RabbitMQ 4.3.7 | `rabbitmq-0`에서 읽기 전용 `wget`으로 `/metrics/detailed?family=queue_coarse_metrics` 조회 | 6개 DLQ와 retry 큐에 `vhost`·`queue` 라벨, `rabbitmq_detailed_queue_messages` gauge 확인. 값 변경 없음 |
| kind 관측 설치·규칙 평가 | 처음에는 미수행 | `.env`에 Grafana 관리자 값이 없었음. 값이 준비된 뒤 아래 절에서 수행 |
| Helm 4.3.1 | `verify_chart.py --baseline e65c9726…` | 기본/local 동일, DLQ job·relabel이 definitions의 6개 DLQ만 유지, scrape 꺼진 DLQ 규칙 렌더 실패 |
| 격리 Docker(실제 RabbitMQ 4.3.7·Prometheus 3.15.1·Grafana 13.3.0) | chart 모드와 단독 모드 각각 | 저장소 definitions를 import한 실제 detailed 출력→Prometheus relabel→6개 시계열만 유지, 한 DLQ만 발생·로컬 대역 수신·회복, 기존 적체·NoData·조회 오류·UID 오류·재적용·scrape 장애 분기 모두 통과 |
| 계약 테스트 | `-O -m unittest discover -s scripts/tests` | 100개 통과 |

DLQ 발생 시험의 값 변화는 실제 broker 출력을 캡처한 대역에서 만들었다. 실제 broker DLQ에 메시지를 넣는 시험,
kind에서의 Prometheus scrape·Grafana 평가, 팀 Discord 수신은 수행하지 않았다. 시험 container·network는 종료 후 남지 않았고
kind 클러스터·`kind236-web`·`pmw-*` container는 변경하지 않았다.

### 남은 결정·후속

- 운영 `dlq_messages`·지속·알림 간격과 severity 승인(시험값 0건/10초는 운영 정책 아님)
- kind 관측 설치를 위한 Grafana 관리자 값 `.env` 준비, 이후 실제 scrape·규칙 평가 확인
- A(월 LLM 비용)·B(담당·연락처·Discord Secret·HTTPS egress·실채널 시험 발송)·C(trace 저장·조회, #185)는 앞 절 그대로 유지
- 업무별 오류율·지연 규칙은 각 서비스의 endpoint/status 지표 공급 확정 후 추가

## kind 실제 경보 평가 (2026-11-03)

사용자가 루트 `.env`에 Grafana 관리자 값을 준비한 뒤 kind `sagomungchi-local`(context `kind-sagomungchi-local`)에서 확인했다.
자격 증명 값은 출력하지 않았고 Pod 환경 안에서만 사용했다. 시작 시 Docker 메모리 30GiB 중 kind 노드 사용 4.4GiB, 노드 요청 메모리 11%였다.

### 절차

1. `create-app-secrets.ps1`을 다시 실행: `app/app-service-credentials`는 값이 같아 그대로 두고 `observability/observability-credentials`만 생성.
2. `helm upgrade --install observability … -f environments/local/observability.yaml`(경보 비활성)로 설치, Collector·Prometheus·Grafana 1/1 Running.
3. Grafana API에서 기존 datasource UID를 조회해 시험 설정을 생성했다. 시험값은 적체 1건, DLQ 0건, 지속 10초, 평가 10초, 묶음 1/10초, 반복 300초다(운영 정책 아님).
   webhook Secret은 실제 Discord 주소가 아닌 클러스터 내부의 존재하지 않는 시험 주소로 만든 `ops187-discord-test`다.
4. 생성한 `helm-values.json`으로 upgrade.

### 발견과 수정

첫 upgrade 뒤 Prometheus Pod가 재시작되지 않아 `rabbitmq-dlq` job이 로드되지 않았다. Prometheus는 ConfigMap 변경을 다시 읽지 않고
chart에 reload 장치나 checksum annotation이 없기 때문이다. `prometheus.rabbitmqDlqMetrics.enabled`일 때만 Prometheus Pod template에
annotation을 붙이도록 수정해 켜고 끌 때 Pod가 다시 만들어지게 했다. 기본/local 렌더는 그대로이며 `verify_chart.py`가 annotation 존재를 검사한다.
local Prometheus는 `emptyDir`이라 이 재생성 때 수집 이력이 초기화된다.

### kind에서 직접 확인한 것

| 항목 | 결과 |
|---|---|
| `rabbitmq-dlq` target | 실제 NetworkPolicy를 거쳐 `rabbitmq.platform:15692/metrics/detailed?family=queue_coarse_metrics` up |
| 수집 시계열 | `rabbitmq_detailed_queue_messages` 6개(정의된 `<큐>.dlq` 전부)만 존재 |
| 규칙 4개 평가 | Prometheus 재생성 직후에는 `up` 부재로 RabbitMQ·Collector 수집 장애 규칙이 일시 발생/pending, 적체 규칙이 NoData 상태였다가 수집 시작 후 모두 Normal·health ok |
| DLQ 규칙 인스턴스 | 큐 6개마다 Normal 인스턴스 생성 |
| 실제 적재 | 비어 있던 `report.report.generate.dlq`에 표식 payload 2건 publish(management API, Pod 안 자격 증명 사용, 소비자 0) |
| 발생 | 약 40초 안에 DLQ 규칙이 해당 큐 하나만 Alerting, 전체 적체 규칙(2>1)도 Alerting. 나머지 5개 DLQ는 Normal |
| 알림 전송 경로 | Grafana가 `ops187-discord` contact point로 전송을 시도했고 시험 주소 DNS 조회 실패로 기록됨(실제 발송 아님) |
| 정리 | 표식 2건을 `ack_requeue_false`로 꺼내 payload 확인 후 제거, DLQ 6개 모두 0 |
| 회복 | 제거 후 약 30초 안에 4개 규칙 모두 Normal |
| 원상 복구 | 경보 비활성 local values로 다시 upgrade(revision 4), 시험 Secret 삭제. observability 스택은 local values 상태로 남김 |

### 대역으로만 확인한 것

- Discord protocol 수신과 회복 알림 수신, NoData·조회 오류 알림, 잘못된 datasource UID, 재provision 중복 방지, scrape job 제거: 격리 Docker 시험.
- 실제 팀 Discord 수신, Grafana의 HTTPS egress 허용(현재 NetworkPolicy에 없음), AWS·Langfuse trace 저장은 미검증이다.
  kind의 전송 시도는 시험 주소 조회 단계에서 끝났으므로 NetworkPolicy가 외부 443을 막는지도 이번에 따로 확인하지 않았다.

## #185 병합 반영과 경보 구조 통합 (2026-11-04)

#185(PR #333)가 develop `de8e225c30d1e156347379b59cb9c34b73dafe37`에 병합된 뒤 `git merge --no-edit origin/develop`을 실행했다.
observability chart 5개 파일(README·values·`alerting.yaml` add/add·configmaps·deployments)이 충돌했다.
#185는 같은 chart에 다른 방식의 Discord 경보를 이미 넣었고 prod에서 동작 중이었다.

| 항목 | #185 | 기존 #187 |
|---|---|---|
| 스위치·마운트 | `grafana.alerting.enabled`, `/etc/grafana/provisioning/alerting`, ConfigMap `grafana-alerting` | 같은 키·경로, ConfigMap `ops187-alerting` |
| 규칙 | values `rules`를 템플릿이 그림 | 생성기 출력 전체를 values로 받음 |
| webhook | `DISCORD_WEBHOOK_URL`, Secret `discord-alert-webhook` | `OPS_DISCORD_WEBHOOK_URL`, 빈 값 시작 차단 |
| 라우팅 | 조직 notification policy 소유 | 규칙별 직접 라우팅 |
| datasource UID | `prometheus` 고정 | 필수 입력 |

develop에 병합돼 prod에서 쓰이는 #185 구조를 기준으로 하기로 사용자가 결정했다. 처리 순서는 다음과 같다.

1. merge commit `a4fafa7`은 충돌한 chart 파일을 develop 버전으로 받았다(chart가 develop과 동일). rebase·force push는 없었다.
2. 다음 커밋에서 #187 생성기 `render.py`와 `ops187` 체계를 제거하고 #185 chart 위에 다음을 더했다.
   - 기본 비활성 DLQ 수집 job, 그 수집이 꺼진 상태의 DLQ 규칙 렌더 실패, Prometheus 재생성 annotation(앞 절의 kind 발견 유지)
   - `grafana.alerting.interval`·`groupWait`·`groupInterval`·`repeatInterval` values. 기본값은 #185 운영값과 같다.
3. 검증기를 #185 템플릿 기준으로 바꿨다. prod 규칙 3개를 가속한 사본과 DLQ 규칙을 렌더해 Docker에서 평가한다.

prod values(`environments/prod/observability.json`)에는 DLQ 수집·규칙을 넣지 않았다. AWS 적용(helm upgrade 등)도 하지 않았다.
prod에서 DLQ 경보를 쓰려면 운영 임계값을 정한 뒤 prod values에 수집과 규칙을 추가하고 별도 승인으로 적용한다.
적용하면 Prometheus Pod가 재생성되며 prod는 PVC라 수집 이력은 보존된다.

#185 구조에서 달라지는 의미는 다음과 같다.

- target 규칙은 `min(up{job=~"otel-collector|rabbitmq"})`다. job 자체가 사라지면 발생이 아니라 NoData로 보고된다(NoData 알림은 전송됨).
- 빈 webhook 값의 시작 차단은 없다. Secret·키 누락은 `secretKeyRef` 기본 동작으로 Pod 구성이 실패한다.
- 조직 notification policy를 chart가 덮어쓴다. 담당별 라우팅은 담당 확정 후 하위 route로 나눈다.
- 2026-11-03 kind 실측과 앞 절들의 격리 검증은 기존 #187 생성기 기준이다. 아래 재검증이 현재 구조의 결과다.

### 통합 구조 재검증 (2026-11-04)

| 범위 | 결과 |
|---|---|
| Helm 4.3.1 | default·local·prod 렌더가 `de8e225`과 바이트 단위로 동일, 세 values 모두 `helm lint --strict` 통과 |
| `verify_chart.py`(기본 기준 `de8e225`) | 29개 확인 exit 0. prod 규칙 3개 가속 사본+DLQ 규칙 렌더, DLQ relabel·annotation·Secret 참조, 수집 없는 DLQ 규칙 렌더 실패, 실제 RabbitMQ 4.3.7 출력→Prometheus→Grafana 13.3.0 평가(적체·DLQ 발생·회복·로컬 수신, NoData·조회 오류·UID 오류·재적용·수집 실패, job 제거 NoData) |
| 계약 테스트 | `-O -m unittest discover -s scripts/tests` 112개 통과 |
| kind `sagomungchi-local` | 같은 가속 사본(적체 임계값 1)으로 revision 5 적용 → 규칙 4개 Normal, DLQ 큐 6개 인스턴스 → `report.report.generate.dlq`에 표식 2건 → 약 30초 안에 그 큐만 Alerting·적체 Alerting → `discord-aws-alerts` 전송 시도(시험 주소 DNS 실패, 실제 발송 없음) → 표식 2건 확인 후 제거, DLQ 합계 0 → 약 30초 안에 모두 Normal → local values로 revision 6 복구, 시험 Secret 삭제 |

kind에서 직접 확인한 것은 실제 수집·평가·발생·회복과 contact point 전송 시도까지다. 수신 메시지 형식·회복 알림·NoData/오류 알림은 격리 Docker 대역으로만 확인했다.
실제 팀 Discord 수신은 #185가 prod에서 임시 규칙으로 확인한 결과이며, #187의 DLQ 규칙으로 prod Discord에 보낸 적은 없다.

## 월 LLM 비용·업무별 오류율·지연 경보 (2026-11-04)

사용자 결정: 월 LLM 예산 300 USD(80% = 240 USD), 담당은 동섭 1명·`aws-alerts` 한 채널. 월 경계는 KST 달력 월 1일 00:00(api-spec 4.6의 KST 기준과 같음).
PR은 아직 만들지 않고 이 브랜치에서 진행했다. AWS 적용은 하지 않았다.

### 구현

- core: `LlmUsageRepository.monthToDate`·`LlmUsageService.monthToDate`·`LlmCostMetrics`. 기존 `summarize`는 미산정 호출이 섞인 call type의 비용 전체를 null로 내므로
  예산용으로는 단가 있는 비용 합계와 미산정 호출 수를 따로 구한다. `io.opentelemetry:opentelemetry-api`(Boot BOM)와 테스트용 `opentelemetry-sdk-testing`을 추가했다.
- observability chart: 규칙별 `noDataState`(기본 NoData). prod values에 규칙 13개와 DLQ 수집 활성화를 추가해 총 16개.
- app-service chart: env의 `JAVA_TOOL_OPTIONS`를 agent 옵션 뒤에 합친다. 이전에는 prod의 `-XX:MaxRAMPercentage=60.0`이 agent 플래그를 덮어써
  agent를 켜도 실제로는 빠지는 상태였다(#185 README의 후속 항목).
- prod `core-service.json`·`learning-service.json`: `javaAgent.enabled`·`networkPolicy.egressToCollector`를 켰다.
- 모든 환경 파일 25개의 렌더를 develop과 비교해 prod observability(규칙 추가)·core·learning(agent 활성화) 외에는 리소스가 같음을 확인했다.

### 검증

| 범위 | 방식 | 결과 |
|---|---|---|
| core 단위·저장소 테스트 | JDK 21 Gradle 컨테이너, Testcontainers PostgreSQL | 새 테스트 2개 통과(KST 월 경계·미산정 분리, OTel SDK 메모리 reader로 gauge 값). 전체 506개 중 179개 실패는 develop 원본도 같은 환경에서 504개 중 179개 실패(`IntegrationTestSupport`가 core 밖 파일을 읽는 `NoSuchFileException`)로 실행 환경 문제이며 새 실패 없음 |
| kind 실제 core | `:issue187` 이미지를 kind에 로드해 core Deployment 이미지를 잠시 교체 | agent 2.33.1 → Collector → Prometheus에 `llm_usage_month_to_date_priced_cost`=0, `..._unpriced_calls`=5 수집. kind의 LLM stub 모델에 단가가 없어 미산정 경고가 실제로 발생 |
| kind 규칙 16개 | prod 규칙 가속 사본(지속 10초) | 모두 health ok. 미산정 호출 Alerting, 비용 Normal. ingress로 인증·리포트 요청을 보내자 해당 영역 5xx 비율·p95 규칙이 NoData→실제 값으로 Normal |
| kind 복구 | | observability local values(revision 8), core 이미지 `:local` 복구, 시험 Secret·kind의 `:issue187` 이미지 삭제 |
| 격리 Docker | `verify_chart.py` | 37개 확인 exit 0. 기존 항목에 더해 비용 80% 발생·회복, 미산정 발생·회복, 인증 5xx 비율·p95 지연 발생, HTTP 지표 부재 발생 |
| 계약 테스트 | `scripts/tests` | 112개 통과 |

kind에서 5xx·지연 초과를 실제로 일으키지는 않았다(대역으로만 발생 확인). `app-metrics-missing`은 처음에 `absent() or absent()`로 작성해 정상일 때 NoData가 되는 문제를 kind에서 발견했고,
`max(... or vector(0))`로 고쳐 정상일 때 0이 되게 했다.

### prod 적용 시 확인할 것 (main 병합 후, 승인 필요)

- Java agent initContainer 이미지(ghcr.io)를 prod 노드가 pull할 수 있는지, core·learning 재시작과 메모리(1Gi limit, heap 60%) 여유
- 적용 순서: core 이미지(비용 지표 포함) 배포 → core·learning agent 활성화 → observability values 적용(Prometheus 재생성, PVC 보존)
- 적용 직후 `app-metrics-missing`·비용 규칙 NoData가 정상화되는지, DLQ 시험 메시지로 `aws-alerts` 수신(완료 조건 1)

### 남은 것

- 실패 요청 단일 trace(완료 조건 2): 저장소 선택(Tempo 권장) 후 Collector traces·agent traces·Python OTel trace와 시나리오 검증
- ai·report(Python) 자체 HTTP 지표, 임계값 실측 조정

## 실패 요청 단일 trace (Tempo, 2026-11-04)

사용자 결정으로 trace 저장소는 Tempo다. PR 없이 이 브랜치에서 진행했고 AWS 적용은 하지 않았다.

### 구현

| 위치 | 내용 |
|---|---|
| observability chart | 선택 구성 `tempo.enabled`: Tempo 2.10.10 단일 바이너리, Collector `otlp/tempo` traces pipeline, Grafana datasource `Tempo`(uid `tempo`), NetworkPolicy(Collector→4317, Grafana→3200), 선택 PVC. Collector·Grafana는 Tempo를 켜고 끌 때 annotation으로 재생성(설정을 시작 시에만 읽음, kind에서 Grafana datasource 누락으로 발견) |
| app-service chart | `tracing.enabled`: Java agent는 `OTEL_TRACES_EXPORTER=otlp`, agent 없는 서비스는 같은 `OTEL_*` 값을 받아 자체 SDK에서 사용 |
| core | `TraceContexts`(OTel API): `OutboxWriter`가 저장 시점 활성 span(없으면 요청 헤더 값)을 봉투 `traceparent`에 넣고, `OutboxRelay`가 그 context 아래에서 발행해 agent가 AMQP 헤더를 만든다 |
| report-service | `app/tracing.py`(OTel SDK, `OTEL_TRACES_EXPORTER=otlp`일 때만 export). 소비 span의 부모를 봉투 `traceparent`로 두고 하위 HTTP·결과 이벤트에 소비 span을 넘긴다. 결과 이벤트에 AMQP `traceparent` 헤더. 실패는 `messaging.outcome`·`error.type`만 기록. 의존성 `opentelemetry-sdk`·`opentelemetry-exporter-otlp-proto-http` 1.45.2(ai-service와 같은 버전) |
| prod values(미적용) | observability `tempo`(72h, gp3 2Gi), core·learning·report-worker `tracing.enabled`, report-worker Collector egress |

### 검증

| 범위 | 결과 |
|---|---|
| core 테스트(JDK 21 Gradle 컨테이너, platform-data definitions·contracts 포함) | 전체 502개 실패 0. `TraceContextsTest` 3개, 비용 지표 2개, relay를 포함한 `MessagingIntegrationTest` 실행 확인. 앞 절의 179건 실패는 컨테이너에 core 밖 파일을 넣지 않아 생긴 것이었고 이번 실행에서 해소 |
| report-service 테스트(로컬 uv) | 새 `test_tracing.py` 7개 포함 consumer 테스트 통과, ruff 통과. 전체 344개 중 PDF 렌더 10건은 이 PC에 Playwright Chromium이 없어 실패(develop 원본도 같은 원인으로 실패) |
| Helm | 모든 환경 파일 25개 렌더를 develop과 비교해 의도한 prod 4개(observability·core·learning·report-worker) 외 동일. `verify_chart.py` 38개 확인 exit 0(Tempo·trace 렌더 검사 추가) |
| kind 단일 trace | 아래 |

kind 시나리오(2026-11-04 14:25~14:46 KST): Tempo와 core·learning(agent trace)·report-worker(새 이미지·OTLP env, 임시 NetworkPolicy)를 켠 뒤,
존재하지 않는 학생·작업 ID로 `report.generate`를 `cmd.direct`에 1건 발행했다. 봉투와 AMQP 헤더에 같은 `traceparent`를 넣어 core outbox relay가 발행하는 형태를 흉내 냈다.
trace `e08ac021…` 하나에 span 67개가 모였다.

1. core 감사 소비자와 report-worker 소비 span(비동기)
2. worker → core `GET /internal/students/{studentId}/profile`(동기, core SERVER span이 worker span의 자식)
3. worker가 발행한 `report.started`·`report.failed`를 core가 소비(비동기, AMQP 헤더로 연결)
4. core가 "Unknown report job"으로 처리 실패 → 재시도 큐 발행 → 1·5·15분 뒤 재소비 3회 → 마지막에 `core.report.events.dlq`로 이동(2건)

첫 발행만 core relay 대신 직접 했다. relay가 저장된 trace 아래에서 발행하는 부분은 단위·통합 테스트로 확인했고 kind에서는 실행하지 않았다.
로그인한 사용자의 HTTP 요청에서 시작하는 경로(리포트 재생성 등)는 kind에 리포트·관리자 계정이 없어 실행하지 못했다.
span 상태는 core 재시도 처리기·worker 업무 실패가 예외를 밖으로 내지 않아 ERROR가 아니라 재시도 발행·DLQ 이동으로 드러난다.

정리: DLQ 2건(제 학생·작업 ID 확인 후 제거), report DB의 해당 학생 `weekly_report` 1행·발행 완료 `outbox_event` 2행 삭제,
core·learning `OTEL_TRACES_EXPORTER=none`·report-worker 원래 이미지와 env 복구, 임시 NetworkPolicy·kind 시험 이미지 삭제, observability local values(revision 11).
core `event_log`에는 이 시험 이벤트의 감사 메타데이터 3행이 남아 있다(감사 기록이라 지우지 않음). 학생·작업 ID는 실제 데이터와 무관한 임의 UUID다.

### 완료 조건 상태

- 실패 요청 추적(동기·비동기 한 trace): kind에서 비동기 명령 → worker → 동기 HTTP → 결과 이벤트 → 실패·재시도·DLQ가 한 trace로 저장·조회됨. 사용자 HTTP 요청 시작점과 prod 실행은 남음
- 경보 디스코드 수신: prod 적용 후 확인 필요(main 병합·배포 승인)

## kind 경보 디스코드 수신 (2026-11-04)

사용자 결정으로 #187은 kind 근거로 마무리한다. 사용자가 루트 `.env`에 `DISCORD_WEBHOOK_URL`(`aws-alerts` 채널)을 넣고 시험 발송을 허락했다.
값은 형식만 확인했고(Discord webhook URL 형식, 출력 없음) stdin으로 시험 Secret `observability/issue187-discord`에만 넣었다. `.env.example`에 항목을 추가했다.

| 시각(KST) | 내용 |
|---|---|
| 15:18 | 경보 활성화(revision 12): 규칙은 DLQ 1개, 제목 `[kind test #187] RabbitMQ dead letter queue depth`, 요약에 로컬 시험·운영 장애 아님을 명시. 지속 10초·평가 10초·묶음 1초/10초 |
| 15:18:03 | 실제 kind DLQ 6개마다 Normal 인스턴스 |
| 15:18:15 | `report.report.generate.dlq`에 표식 메시지 1건 적재 |
| 15:18:41 | 해당 큐 인스턴스만 Alerting |
| 15:18:54 | contact point `discord-aws-alerts` 전송, Grafana 기록 오류 없음(Discord 응답 성공) |
| 15:20:00 | 표식 메시지 확인 후 제거, DLQ 합계 0 |
| 15:20:24 | 회복(Resolved) 전송, 오류 없음 |
| 15:21 | local values(revision 13, 경보 꺼짐)로 복구, 시험 Secret 삭제 |

Grafana NetworkPolicy는 경보 활성화 시 공인 IPv4 443만 추가로 열며 kind Calico에서 실제 Discord로 나갔다.
템플릿의 `environment: demo` 라벨은 #185 고정값이라 kind 메시지에도 그대로 붙는다.

### 완료 조건 최종 상태(kind 기준)

- 경보 발생 테스트(디스코드 수신): kind에서 실제 RabbitMQ DLQ 적재 → Grafana 규칙 발생 → `aws-alerts` 전송·회복 전송 성공
- 실패 요청 추적 테스트(동기·비동기 한 trace): kind에서 명령 소비 → 동기 HTTP → 결과 이벤트 → 실패·재시도·DLQ가 한 trace(앞 절). 로그인 사용자 요청 시작점은 kind 데이터 부재로 미실행
- prod 적용(규칙 16개, Java agent, Tempo, trace)은 values에만 반영됐고 main 릴리스 배포 때 승인 후 적용한다
