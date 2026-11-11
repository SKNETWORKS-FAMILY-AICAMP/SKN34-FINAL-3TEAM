# core 부하 시험 (#361)

AWS 데모 환경(CloudFront → ALB → core)에 k6로 부하를 주어 core·NAT 중 먼저 한계에 닿는 지점을 찾는다. 결과와 판단은 `docs/report/`에 기록한다.

| 파일 | 내용 |
|---|---|
| `core-load.js` | k6 시나리오. 한 번 실행이 VU 단계 하나다 |
| `prepare_accounts.py` | ID·비밀번호 시험 계정 준비(가입·동의·자녀·기기·PIN)와 비밀 파일 작성 (#415) |
| `run-stage.ps1` | 한 단계 실행: k6 → 같은 시간대 서버 지표 수집. 로그·결과를 결과 폴더에 남긴다 |
| `collect_metrics.py` | Prometheus(core·learning JVM, DB 풀, HTTP, RabbitMQ)·CloudWatch(RDS, ALB, NAT)·Pod 재시작 수집 |
| `llm-stub.k8s.yaml` | 데모 `app` 네임스페이스용 LLM 스텁 Deployment·Service·NetworkPolicy |

1차 결과와 해석은 [`docs/report/load-test.md`](../../docs/report/load-test.md)에 있다.

## 시나리오

| 이름 | 비중 | 흐름 | 비고 |
|---|---|---|---|
| browse | VU의 55% | 보호자 `/me`·리포트 목록·리포트 상세(있을 때)·알림·대화 목록, 학생 미션 목록·상세·홈·학습 기록 | 요청 사이 1~3초 대기. 유료 리포트 상세는 볼 때마다 이용 기록을 쓴다 |
| learn | VU의 20% | 시도 시작 → 첫 답변 제출 → 판정 SSE 완료 → 마무리 → 돌아보기 | 자녀별로 받은 `MISSION_INPUT_TYPES` 미션의 (자녀, 미션) 칸을 VU마다 하나씩 맡아 반복. 경합을 만나면 다음 칸으로 옮긴다 |
| notify | VU의 15% | 알림 SSE를 `NOTIFY_HOLD_S`(기본 120초)만큼 붙잡고 다시 연결 | 화면을 켜 둔 보호자 |
| analyze | VU의 `ANALYZE_RATIO`(기본 10%) | VU마다 대화 생성 → 질문 SSE를 결과까지 → 30~60초 생각 반복 | 유료 구독 자녀가 필요하다. `409`·`429`는 `analysis_limited`로 집계 |

- k6 기본 `http` 모듈은 SSE를 스트림이 끝날 때까지 기다렸다가 한 번에 받는다. 그래서 판정·분석은 요청부터 완료까지의 시간만 재고, 첫 이벤트까지의 시간은 재지 않는다. 알림 SSE는 k6 시간 초과(오류 코드 1050)를 "그만큼 연결이 유지됨"으로 보고 성공으로 센다.
- 같은 자녀·미션을 여러 VU가 동시에 잡으면 진행 중 시도를 함께 받는다. 이 경합(`learn_conflict`)은 오류율에서 빼고 따로 센다.
- 미션은 학년 범위로 공개되므로 자녀마다 받는 미션이 다르다. 판정 동시성 상한은 칸 수(계정 × 자녀 × 미션)이고, 학습 VU(전체의 20%)가 칸 수보다 많으면 넘치는 VU는 경합만 만든다. 보호자당 자녀는 최대 3명이므로, 5학년 자녀 3명이면 계정 하나에 15칸이다.

## 유료 기능

분석 대화·유료 리포트 상세는 시험 자녀에게 활성 구독이 있어야 열린다. 데모의 토스 공용 위젯 키가 2026-11-05 기준 실패(`widget-groups/keys` 500)해 결제로 구독을 만들 수 없어, `infrastructure/aws/add-demo-test-subscription.sql`로 결제 없는 시험 구독(이 구독만 하루 분석 5,000회)을 넣었다. 시험 뒤 같은 파일 주석의 원복 SQL로 해지한다.

## 비밀 파일 준비 (담당자)

토큰·비밀번호·PIN은 **저장소 밖** 파일에만 둔다. 출력하지 않고 커밋하지 않는다.

### 기본: ID·비밀번호 시험 계정 (#415)

`prepare_accounts.py`가 공개 API로 계정을 만든다. 순서는 ID·비밀번호 가입 → 약관·처리방침 동의 → 자녀(법정대리인 동의) → 학생 기기 등록 → 자녀 PIN이다. 비밀번호·PIN·기기 쿠키는 비밀 파일에만 쓴다.

```powershell
python evaluation/load/prepare_accounts.py --base-url https://d3jf0rnm6vhd9v.cloudfront.net `
  --count 4 --prefix load --wait --secrets 'C:\Users\<사용자>\sagomungchi-load\secrets.json'
```

- 판정 경로까지 보려면 계정 수 × 자녀 3 × 미션 5 ≥ 학습 VU(전체의 20%)가 필요하다(`docs/report/load-test.md` 4장). 300 VU는 4개다.
- AWS 데모는 `AUTH_NEW_ACCOUNT_DEMO=true`라서 가입한 계정이 `is_demo=true`로 저장되어 운영 집계에서 빠진다. 로컬은 이 값을 켠 core에서 만든다.
- 가입은 같은 IP에서 10분에 5회까지다(`AUTH_SIGNUP_LIMIT_PER_IP`·`AUTH_SIGNUP_LIMIT_WINDOW`). `--wait`를 주면 한도에 걸릴 때 1분씩 기다렸다 다시 시도한다. 로컬 compose는 `.env`에서 두 값을 바꾸면 core에 전달된다(#517).
- 같은 `--prefix`·`--secrets`로 다시 실행하면 파일에 없는 계정만 더 만든다. ID는 `<prefix><번호>`(영문 소문자·숫자)다.
- k6 `setup()`은 실행할 때마다 계정마다 `POST /auth/parent/login`으로 보호자 access를 새로 받는다. 회전하는 refresh 토큰이 없으므로 비밀 파일을 다시 쓰지 않고, 시크릿 창·로그아웃 주의도 필요 없다.

```json
{
  "accounts": [
    {
      "loginId": "load1",
      "password": "<생성된 비밀번호>",
      "deviceCookie": "<student_device 값>",
      "children": [{ "childId": "<자녀 UUID>", "pin": "<PIN>" }]
    }
  ]
}
```

### 옛 방식: Google 계정 refresh 토큰

`loginId`가 없는 계정은 이전처럼 refresh 토큰을 쓴다. 같은 파일에 섞어도 된다.

1. 브라우저 **시크릿 창**에서 CloudFront 주소로 시험 계정(`is_demo=true`)에 로그인한다.
2. 같은 창에서 학생 기기를 등록하고, 자녀 PIN을 설정한다.
3. 개발자 도구 → Application → Cookies에서 두 값을 복사한다.
   - `sagomungchi_refresh`: 보호자 refresh 토큰 (경로 `/api/v1/auth`)
   - `student_device`: 학생 기기 자격 증명 (경로 `/api/v1/auth/student`)
4. **로그아웃하지 말고 시크릿 창을 닫는다.** 로그아웃하면 세션이 폐기된다. 창을 열어 둔 채 브라우저가 옛 refresh 토큰을 다시 쓰면 `REFRESH_REUSED`로 세션 전체가 폐기된다.
5. 계정 항목에 `loginId`·`password` 대신 `"refreshToken": "<sagomungchi_refresh 값>"`을 넣는다.

계정·자녀가 여러 개면 `accounts`·`children`에 더한다. VU 번호 순서대로 나눠 쓴다.

**refresh 토큰 회전:** 보호자 refresh 토큰은 한 번 쓰면 새 값으로 바뀐다. `setup()`이 한 번 갱신한 access 토큰(15분)을 모든 VU가 함께 쓰고, `handleSummary`가 바뀐 refresh 토큰을 같은 비밀 파일에 되돌려 쓴다(ID·비밀번호 계정은 그대로 둔다). 그래서 다음 단계를 그대로 이어 실행할 수 있다. 실행이 비정상 종료되어 파일이 갱신되지 않았으면 1~5를 다시 한다. 학생 토큰은 매 실행 `setup()`에서 기기 쿠키와 PIN으로 새로 받는다.

## 실행

PowerShell, 저장소 루트에서 실행한다. 단계마다 한 번씩 실행한다. 한 번 실행은 올리기 30초, 유지 5분, 내리기로 약 6분이며, 단계 사이에 지표를 확인한다.

```powershell
pwsh -NoProfile -File evaluation/load/run-stage.ps1 -Vus 10 `
  -Secrets 'C:\Users\<사용자>\sagomungchi-load\secrets.json' `
  -ResultDir 'C:\Users\<사용자>\sagomungchi-load\results' `
  -Kubeconfig '<AWS 데모 kubeconfig>'
```

결과 폴더에 `k6-vus{N}.log`(k6 요약 + 서버 지표), `server-vus{N}.json`, k6 요약 JSON이 남는다. `$env:DEBUG='1'`을 주면 학습 실패·경합·마무리 응답을 한 줄씩 남긴다.

| 변수 | 기본값 | 뜻 |
|---|---|---|
| `BASE_URL` | `https://d3jf0rnm6vhd9v.cloudfront.net` | 진입 주소 |
| `VUS` | 10 | 이번 단계의 총 VU (55/20/15/10으로 나눔) |
| `HOLD` / `RAMP` | `5m` / `30s` | 유지 시간 / 올리는 시간 |
| `P95_API_MS` | 1000 | 일반 API p95 목표. 넘으면 자동 중단 |
| `P95_JUDGMENT_MS` | 30000 | 판정 SSE 완료 p95 목표. 넘어도 보고만 하고 중단하지 않음 |
| `ANALYZE_RATIO` | 0.1 | 분석 대화 VU 비율. 0이면 분석 시나리오 끔 |
| `P95_ANALYSIS_MS` | 60000 | 분석 SSE 완료 p95 목표. 넘어도 보고만 함 |
| `NOTIFY_HOLD_S` | 120 | 알림 SSE를 붙잡는 시간 (서버는 5분에 닫음) |
| `MISSION_INPUT_TYPES` | `NARRATIVE,ESSAY,SOLUTION_STEPS` | 학습 시나리오가 쓰는 미션 입력 방식. 판정 동시성 상한은 자녀 수 × 미션 수 |

처음에는 `-e VUS=1 -e HOLD=30s`로 한 번 돌려 흐름이 맞는지 확인한다.

## 중단 기준

| 기준 | 감시 방법 |
|---|---|
| API 오류율 1% 초과 | k6 임계값 `http_req_failed{kind:api}` (1분 뒤부터 자동 중단) |
| API p95 목표 초과 | k6 임계값 `http_req_duration{kind:api}` (자동 중단) |
| Pod 재시작 | `kubectl --kubeconfig <AWS kubeconfig> get pods -n app -w`의 RESTARTS (사람이 Ctrl+C) |
| RDS CPU 80% 초과 | CloudWatch `AWS/RDS CPUUtilization` (`sagomungchi-demo-db`, 1분) (사람이 Ctrl+C) |

## 함께 볼 지표

| 출처 | 지표 |
|---|---|
| k6 요약 | 경로별 p95·p99, `judgment_duration`, `analysis_duration`, `learn_ok`, `notify_ok`, `learn_conflict`, `analysis_limited` |
| Prometheus (core) | HTTP 경로별 지연·5xx, JVM CPU·힙·스레드, `hikaricp_connections_pending`·`active`, pinning 로그(`-Djdk.tracePinnedThreads` 적용 시) |
| CloudWatch | RDS CPU·`DatabaseConnections`, ALB `HTTPCode_ELB_5XX`·`TargetResponseTime`, NAT `ActiveConnectionCount`·`BytesOutToDestination`·`ErrorPortAllocation` |
| RabbitMQ | 큐 적체(ready·unacked) |
| 노드 | `kubectl describe nodes`의 할당량, 노드별 메모리 압박 |

## LLM 스텁

실제 LLM 비용·지연 편차를 빼기 위해 시험 동안 ai-service를 `infrastructure/stubs/llm-stub`으로 돌린다. `LLM_STUB_DELAY_MS`·`LLM_STUB_JITTER_MS`로 응답 지연(기본값 + 0~지터 균등)을 준다. 데모 클러스터 배포·ai-service 전환·원복은 승인을 받은 뒤 하나씩 실행하고, 실행한 명령과 결과는 `docs/report/`에 남긴다. 시험 중에는 데모의 AI 답변이 시험용 문장으로 바뀌므로 팀에 공지한 시간대에만 한다.

## 시험 뒤 정리

- LLM 스텁·core JVM 옵션 원복
- 시험 계정 자녀의 시도·답변·판정은 시험 데이터다. 삭제 범위와 방법은 실행 전에 확인받는다.
- ID·비밀번호 시험 계정(`load<번호>`)은 `is_demo=true`라 집계에서 빠진다. 계정 탈퇴 여부는 시험 데이터 삭제와 함께 실행 전에 확인받는다.
- 비밀 파일은 시험이 끝나면 지운다. 보호자 화면의 기기 목록에서 시험용 학생 기기를 해제한다. k6가 이어 쓰던 보호자 세션은 refresh 만료로 끝난다.
