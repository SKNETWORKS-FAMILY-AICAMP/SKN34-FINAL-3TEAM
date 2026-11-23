# 추억 검색 평가셋 memory@2 (#853)

기록이 많을 때 "기간 + 소재"·"기간만" 질문에 정답 기간 밖 회차(다른 미션)가 섞이는 비율을 재는 합성 평가셋. 기준·결과는 [retention-expansion.md 18.5](../../../docs/report/retention-expansion.md), 기간 필터 규칙은 16.3, memory@1은 [../memory/README.md](../memory/README.md)

- memory@1과 자료가 달라 결과를 섞지 않는다(결과 파일 이름 `memory@2__<이름>`)
- 가상 학생·자체 작성 테마·자체 작성 미션만 사용. AI Hub 글·실제 아동 정보 없음(NFR-SEC-07). 문장은 평가용 Claude 초안이고 실제 학생 글이 아님
- 기록은 SQL INSERT 없이 #624 시험 시계 방식으로 공개 API를 불러 만든다(memory@1과 같은 스크립트 `../memory/load_via_api.py --dataset ../memory@2`)
- 정답표는 사람이 확인한 질문만 채점한다(`checkedBy`, 러너 `--min-checkers` 기본 1)

## memory@1과 다른 점

| 항목 | memory@1 | memory@2 |
|---|---|---|
| 미션 | 시드 미션 5개를 매주 같이 씀 | 주마다 새 미션 5개(52주 × 5 = 260개)를 관리자 API로 작성·게시. 시드 초5 DEMO-11~15를 틀로 생각 유형·입력 방식·교과·학년·성취기준·기준표 요소를 복사하고 제목·질문만 그 주 소재로 바꿈(`ThemePublishCheck` 다섯 생각 유형 조건을 그대로 채움) |
| 주 | 7주 | 2025-10-13 주 ~ 2026-11-09 주 중 방학 5주(`gapWeeks`)를 뺀 52주(W01~W52) |
| 학생 | 초3·초5 9명(조정용·평가용·삭제) | 초5 6명, 모두 평가용. 최근 6주·20주·52주만 푸는 학생 2명씩(기록 30·100·260개) |
| 답 | 학생마다 다름 | 주마다 변형 A·B 두 가지(학생 `variant`), 같은 기록 수의 두 학생이 다른 변형 |
| 질문 | 제목·다른 표현·답 내용 등 | 기간 질문 20종 × 학생 6명 = 120개 |
| 기준일 | 실행 날짜 | `evalToday` 2026-11-18(수) 고정. 수집 때 learning 시계를 이 날로 맞춤("지난달" 정답이 실행 날짜에 따라 바뀌지 않게) |
| 범위 시험 | W7·EXTRA·실행 주·삭제 | 없음(memory@1에서 잼). 다른 학생 기록이 나오는지만 범위 위반으로 셈 |

## 파일

| 파일 | 내용 |
|---|---|
| `students.json` | 주 표·방학 주·기준일, 시드 틀 미션, 소재 반복 표, 주별 미션(제목·질문·풀이 단계 정답·답 변형 A·B), 학생 6명 |
| `themes.json` | 자체 테마 52개(T01~T52, 주마다 1개): 제목, 월~금 문제 전 대화 |
| `queries.jsonl` | 질문 120개. 한 줄에 질문·기간·소재·정답 회차·경계 회차 |

검사는 `python -I ../memory/check_dataset.py .`(정답·경계를 기간 규칙으로 다시 계산해 맞춰 봄, 소재 낱말이 태그한 주에만 있는지 봄)

## 소재 반복

소재 8개(자석·고양이·화분·별자리·다리·재활용·빗물·연날리기)를 1년 중 서로 다른 달 4주씩에 넣었다(`subjects`). 나머지 20주는 한 번만 나오는 소재다. 소재 낱말은 태그한 주의 글에만 들어 있다(검사함). 그래서 "10월에 자석으로 한 활동"은 10/12 주만 정답이고, 3·7월과 작년 11월의 자석 주는 나오면 섞임이다. 최근 6주(10/5~11/9)는 모두 반복 소재 주라 6주 학생도 소재 질문에 답이 있다.

## 질문 (학생마다 같은 20개, 정답은 학생이 푼 주에 따라 다름)

| 종류 | 개수 | 예 | 기대 |
|---|---|---|---|
| `PERIOD_TOPIC` | 10 | "10월에 자석으로 한 활동 찾아줘", "9월에 다리 만든 거" | 기간 안 + 그 소재 주. 6주 학생은 9월·8월·4월 질문의 기록이 없어 `NO_RESULTS` |
| `PERIOD_ONLY` | 6 | "지난달에 푼 문제", "11월 첫째 주에 한 거" | 기간 안 주 모두(카드가 최대 3개라 Recall 분모 min(3, 정답 수)) |
| `PERIOD_EMPTY` | 4 | "8월 첫째 주에 한 문제", "작년 9월에 쓴 글" | 모든 학생 `NO_RESULTS`(방학 주·적재 전 기간) |

- `period`: 사람이 정한 반열림 기간 `[from, to)`. "N월 첫째 주"는 그달 1일부터 첫 월요일 주 끝까지(예: 10월 첫째 주 = 10/1~10/11), "이번 달"은 진행 주 월요일(11/16)에서 자름
- 정답·경계 규칙(담당자 결정 2026-11-20): 회차 주 월~금 중 기간 안 날이 3일 이상이면 정답 기간 안, 1~2일이면 경계(`boundary`, 정답도 섞임도 아님), 0일이면 섞임. 서비스 필터는 하루라도(주말 포함) 겹치면 넣으므로 경계·주말 겹침 카드는 "겹침 규칙" 원인으로 따로 셈. #879 뒤 기간만 질문 경로만은 회차 주 월~금 중 기간 안 날이 1일 이상인 회차를 넣는다(주말만 겹친 주 제외, retention-expansion.md 16.9)
- 기록 수별 기대 개수: 6주 학생 결과 있음 10·없음 10, 20주 15·5, 52주 16·4

## 만드는 순서 (PC compose)

memory@1 README "PC(compose)로 실행"의 0)~3) 공통·이미지·띄우기·계정을 그대로 한다. 학부모는 `m2a`·`m2b` 두 칸(로그인 ID `DEMO_PARENT_LOGIN` + `m2a`)이라 memory@1 학부모와 겹치지 않는다. memory@1의 4) 준비 SQL(`is_demo`·시험 구독)은 하지 않는다: 초3·초5 짝용이라 맞지 않고, EXTRA를 풀지 않으며, 평가 스택은 끝나면 지운다.

```powershell
$L = "evaluation/datasets/memory/load_via_api.py"; $M = "--dataset", "evaluation/datasets/memory@2"
python -I $L @M parent-signup
python -I $L @M children
# E2E 스택은 성취기준 표가 비어 있어 새 미션 게시가 422(achievementStandards)로 막힘 → 참조 데이터 시드를 먼저 넣음
Get-Content backend/learning-service/db/seed/achievement_standards.sql -Raw -Encoding utf8 | docker compose @C exec -T postgres sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d learning_db'
# 실제 시각(W52 다음 주 이후): 주별 미션 260개 작성·게시 → 테마 52개 게시. 같은 주에 다른 게시 테마가 있으면 멈춤
python -I $L @M missions
python -I $L @M themes
# 주마다 시계를 그 주 토요일 14:00 KST(05:00 UTC)로 옮겨 풀이(52번, 주마다 재기동 1~2분 + 풀이)
foreach ($line in (python -I $L @M weeks)) {
  $w = $line -split " "
  $env:EVAL_LD_PRELOAD = $FT; $env:EVAL_FAKETIME = "@$($w[1]) 05:00:00"
  docker compose @C up -d --wait --no-deps core-service learning-service
  python -I $L @M solve --week $w[0]
}
python -I $L @M manifest   # 학생별 주 수 6·20·52 확인
```

- 적재 표 기본 위치 `evaluation/results/memory/load-manifest__memory@2.json`(커밋 안 함). 학생·테마·미션·시도 ID만 있다
- 다시 실행해도 된다. `missions`는 작성한 미션 ID를 바로 적재 표에 남겨, 게시 안 된 것만 이어서 끝낸다. `solve`는 끝낸 요일을 건너뛴다
- 앞쪽 주는 52주 학생 2명만 풀고, W33(6/8 주)부터 20주 학생, W47(10/5 주)부터 6주 학생도 푼다

## 평가 실행

수집 때 learning 시계를 기준일 2026-11-18로 고정한다(검색 문서는 이미 `READY`여야 함 — 마지막 `solve` 뒤 1~2분).

```powershell
$env:EVAL_LD_PRELOAD = $FT; $env:EVAL_FAKETIME = "@2026-11-18 03:00:00"   # 12:00 KST, 아래 learning 재기동에도 그대로 쓰임
docker compose @C up -d --wait --no-deps core-service learning-service
$env:T = ((Get-Content infrastructure/stubs/e2e.env | Select-String '^INTERNAL_TOKEN_CORE=').Line -split '=',2)[1]
$TA = ((Get-Content infrastructure/stubs/e2e.env | Select-String '^INTERNAL_TOKEN_LEARNING=').Line -split '=',2)[1]   # ai가 받는 learning 호출자 토큰
$R = "evaluation/runners/memory_search_eval.py"; $D = "--dataset", "evaluation/datasets/memory@2"
$PL = "docker compose $($C -join ' ') exec -T postgres psql -U sagomungchi -d learning_db"
# 1) 벡터만(V)·K1·K2: 질의 변환 끄고 기준값 -1로 모음 → score가 서비스 기준값 0.35로 채점(조정용 나누기 없음)
$env:EVAL_MIN_SIMILARITY = "-1"; $env:EVAL_QUERY_REWRITE = "false"; docker compose @C up -d --wait --no-deps learning-service
python -I $R collect @D --learning-url http://127.0.0.1:8081 --token $env:T --psql $PL --label pc-<날짜> --environment "PC compose(E2E), 벡터만, 기준일 2026-11-18"
python -I $R score @D --raw "evaluation/results/memory/memory@2__pc-<날짜>.raw.json"
# 2) 하이브리드(H): ai 실제 LLM, 질의 변환 켬, 기준값 0.35 → 받은 그대로 채점. 끝난 뒤 질문마다 ai를 한 번 더 불러 해석 기간 저장
$env:EVAL_LLM_BASE_URL = "https://api.openai.com/v1"; $env:EVAL_LLM_MODEL = "gpt-6-luna"; docker compose @C up -d --wait --no-deps ai-service
$env:EVAL_MIN_SIMILARITY = "0.35"; $env:EVAL_QUERY_REWRITE = "true"; docker compose @C up -d --wait --no-deps learning-service
python -I $R collect @D --learning-url http://127.0.0.1:8081 --token $env:T --psql $PL --label pc-<날짜>-hybrid --warmup 2 --repeats 1 --capture-period --ai-url http://127.0.0.1:8000 --ai-token $TA --environment "PC compose(E2E), 하이브리드, 기준일 2026-11-18"
python -I $R score @D --raw "evaluation/results/memory/memory@2__pc-<날짜>-hybrid.raw.json" --as-served
# 3) 되돌림·지우기는 memory@1 README 8-3과 같음. 끝나면 docker compose @C down -v
```

- 결과 요약에 방식별 `mixing`(카드 섞임 비율·질문 단위 섞임 발생률과 Wilson 95% 구간·경계 카드 비율·원인), 기록 수별 `bySize`, 하이브리드 `periodAccuracy`(해석 기간이 사람이 정한 기간과 같은 비율)가 더해진다. Recall@3·거절률·범위 위반·p95도 memory@1과 같은 식으로 나온다
- 통과 기준(담당자 결정 2026-11-20): H 질문 단위 섞임 발생률 ≤ 0.10(경계 제외). V·K는 기간을 쓰지 않아 비교용
- H 원인은 검색 때와 별개로 부른 질의 변환으로 추정한다(LLM 결과가 조금씩 다를 수 있음). 해석 기간 없음 = 기간 해석 실패, 해석이 사람이 정한 기간과 다름 = 기간 해석 다름, 해석은 맞는데 주말·경계로 겹침 = 겹침 규칙, 해석 기간과 겹치지 않는데 나옴 = 필터 누락(확인 필요)

### 다시 재기: #877·#878·#879 뒤 H (`memory-query@2`)

몇째 주 계산(#877)·변환 실패 503(#878)·기간만 질문 최신 회차(#879)의 효과를 18.5와 같은 절차로 잰다. 돈이 드는 실행이라 따로 승인받은 뒤 한 번만 한다(재측정 결과는 retention-expansion.md 18.6).

1. 세 이슈가 들어간 브랜치로 ai·learning 이미지를 빌드한다. 평가 스택은 18.5 뒤 지워졌으므로 위 "만드는 순서"부터 다시 적재한다
2. H만 모은다. V(질의 변환 끔)·K1·K2(SQL)는 이번 변경과 무관해 다시 재지 않고 `pc-1121` 값과 비교한다. 위 2)의 `collect`·`score --as-served`를 새 라벨 `pc-<날짜>-hybrid`로 그대로 실행한다. 수집 시작 시각(KST ISO)을 적어 둔다
3. 503 처리: learning은 기간을 말한 질문의 질의 변환이 한 번 다시 시도한 뒤에도 실패하면 503 `AI_UNAVAILABLE`을 준다. 러너는 멈추지 않고 그 질문을 `state: UNAVAILABLE`(카드 없음)로 남긴다. 채점은 결과 질문 Recall 0, 기록 없음 질문은 거절 성공으로 세지 않고, 요약에 `unavailable` 건수를 더한다. 그 밖의 HTTP 오류는 지금처럼 멈춘다
4. `--capture-period`는 해석 기간과 함께 `keywordCount`(키워드 개수, 원문 없음)를 남긴다. 기간만 질문이 실제로 키워드 0개로 변환됐는지 본다
5. 내리기 전에 실패 사유를 남긴다(커밋하지 않는 파일, 원문 없음):

```powershell
docker compose @C logs ai-service > "evaluation/results/memory/ai-log__memory@2__pc-<날짜>-hybrid.txt"        # reason= 사유 코드
docker compose @C logs learning-service > "evaluation/results/memory/learning-log__memory@2__pc-<날짜>-hybrid.txt"  # failureCode·attempt, result=UNAVAILABLE|VECTOR_ONLY
docker compose @C exec -T postgres psql -U sagomungchi -d core_db -c "SELECT success, error_code, output_tokens >= 512 AS capped, count(*) FROM llm_usage WHERE call_type = 'MEMORY_QUERY' AND occurred_at >= '<수집 시작>' GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
```

- `llm_usage`로 502·503 원인을 가른다: `LLM_INVALID_OUTPUT`이면서 출력 512토큰(잘림)·`LLM_TIMEOUT`·성공인데 learning 쪽 실패(칸 검사 502)
- 멈춤 기준(제안): 처음 20개 검색에서 503이 3개 이상이거나 200·503 밖의 응답이 나오면 멈추고 로그·`llm_usage`부터 본다. 같은 실행을 고쳐 가며 반복하지 않는다
- 끝나면 `docker compose @C down -v`

## 정답 확인

`python -I evaluation/datasets/memory/answer_check.py --dataset evaluation/datasets/memory@2 page`로 확인 페이지(`answer-check__memory@2__eval.html`, 커밋 안 함)를 만들어 확인자에게 준다. 화면 위에 기준일과 3일 규칙이 나온다. 돌려받은 json은 같은 `--dataset`으로 `compare --answers <json> [--apply 이름]`
