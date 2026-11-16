# 추억 검색 평가셋 memory@1 (#568)

추억 검색(P27, #563)이 "말로 지난 기록 찾기"를 얼마나 맞히는지, 범위 밖 기록을 내지 않는지 재는 합성 평가셋. 기준안은 [retention-expansion.md 17장](../../../docs/report/retention-expansion.md)(질의 변환·하이브리드 설계는 16장), 러너는 [`evaluation/runners/memory_search_eval.py`](../../runners/memory_search_eval.py)

- 가상 학생·자체 테마 이야기·저장소 시드 미션만 사용. AI Hub 글·실제 아동 정보 없음(NFR-SEC-07)
- 학생 답은 평가용 자체 작성 예시(Claude 초안, 실제 학생 글 아님)
- 기록은 SQL INSERT 없이 #624 시험 시계 방식(infra.md 9.7)으로 공개 API를 불러 만든다
- 정답표는 사람이 확인한 질문만 평가에 쓴다. 담당자가 122개 모두 확인, 평가용 60개는 다른 2명도 정답을 가린 채 따로 확인(2026-11-16, 아래 "정답 확인")
- 자료를 바꾸면 `memory@2`로 올리고 이전 결과와 섞지 않는다

## 파일

| 파일 | 내용 |
|---|---|
| `themes.json` | 자체 테마 16개(학년·주마다 1개, W1~W7 14개 + 실행 주 T15·T16): 제목, 월~금 문제 전 대화. 문제는 `students.json`의 시드 미션 |
| `students.json` | 주 7개, 학년별 요일 미션, 가상 학생 9명의 회차별 답·추가 문제(EXTRA)·실행 주 기록 |
| `queries.jsonl` | 질문 122개. 한 줄에 질문 하나와 정답 회차·근거 |
| `check_dataset.py` | 형식·참조·개수·정답 근거 검사(표준 라이브러리만). `python -I check_dataset.py` |
| `load_via_api.py` | 공개 API로 기록 적재(아래 "만드는 순서"), 적재 표(학생·테마·시도 ID) 저장 |
| `answer_check.py` | 정답 확인 도구(표준 라이브러리만). `page --split eval`로 정답을 뺀 확인 페이지(HTML), `compare --answers <json> [--apply 이름]`으로 정답표와 맞춰 보고 같은 질문의 `checkedBy`에 이름 추가 |

## 구성

| 항목 | 값 |
|---|---|
| 주 | W1~W6 = 9/28·10/5·10/12·10/19·10/26·11/2(완주, 액자 있음), W7 = 11/9(3문제만, 액자 없음). 실행 주(CURRENT) = 평가를 돌리는 실제 주 |
| 학생 | 초3 `E3A`~`E3D` 조정용(tune), 초5 `E5A`~`E5D` 평가용(eval), 초3 `E3X` 삭제 확인용(W1만 풀고 자녀 프로필 삭제) |
| 테마 | 초3 T01·T03·T04·T02·T06·T07(W1~W6)·T13(W7)·T15(실행 주), 초5 T05·T08·T09·T10·T11·T12(W1~W6)·T14(W7)·T16(실행 주). 실행 주에 이미 게시 테마가 있으면(kind 시연 테마 등) T15·T16은 건너뛰고 그것을 씀. T01~T10은 11/13 초안 대화 재사용 |
| 미션 | 초3 월~금 DEMO-01~05, 초5 월~금 DEMO-11~15(시드 게시 미션, 생각 유형 하나씩) |
| 글이 있는 요일 | 초3 화·수·금(서술), 초5 월·수·금(서술)·화(논술). 초3 월·목은 선택·순서, 초5 목은 풀이 단계라 학생 간 차이가 거의 없음 |
| 검색 문서 | 학생당 완주 30개 + W7 3개 + 실행 주 1개 = 34개, 8명 272개(EXTRA는 검색 문서가 생기지 않음) |
| EXTRA | 프리미엄 전용이라 초5 4명만(시험 구독). 초3 범위 시험은 W7·실행 주로 함 |

### 미션을 시드로 고정한 까닭

테마를 게시하려면 다섯 요일에 생각 유형이 하나씩 다른 게시 미션이 들어가야 한다(`ThemePublishCheck`). 시드의 게시 미션은 학년마다 5개뿐이라 어느 주든 같은 미션이 들어간다. 답을 미리 써 두려면 미션이 정해져 있어야 해서, 환경에 상관없이 있는 시드 미션 ID로 고정했다

- 결과: 한 학생의 6회차 문서에 미션 질문이 매주 똑같이 들어간다. 회차를 가르는 것은 테마 제목·대화와 학생 답이다
- 그래서 미션 질문 내용("피구 규칙 만든 거" 등)으로 찾는 질문은 넣지 않았다. 6회차 모두가 정답이 되기 때문이다
- 실제 서비스는 주마다 미션이 달라 이번 평가보다 회차 구분이 쉬울 수 있다(한계로 적음)

## students.json

```json
{"dataset": "memory@1",
 "weeks": {"W1": "2026-09-28", "…": "…", "W7": "2026-11-09"},
 "missions": {"G3": {"MON": {"code": "DEMO-01-G3-ANALYZE", "missionId": "d1000000-…-000000000001",
                             "inputType": "CHOICE", "title": "…", "question": "…",
                             "defaultAnswer": {"choiceIds": ["c2"]}}, "…": {}}},
 "students": [{"studentKey": "E3A", "nickname": "eval3a", "grade": 3, "split": "tune",
   "rounds": [{"week": "W1", "themeKey": "T01", "complete": true, "days": ["MON", "…", "FRI"],
               "answers": {"MON": null, "TUE": {"text": "…"}}}],
   "extra": {"missionDay": "TUE", "answer": {"text": "…"}},
   "current": {"days": 1, "answer": {"text": "…"}},
   "deleteAfterLoad": false}]}
```

- `answers`의 값은 api-spec 3.1 제출 본문의 답 부분(`text`·`essay`·`steps`+`finalAnswer`·`choiceIds`). `null`이면 그 요일 미션의 `defaultAnswer`
- `extra.missionDay`: 그 학년 표의 같은 요일 미션을 `EXTRA` 맥락으로 한 번 더 푼다(실제 시각, 초5만)
- `current`: 실행 주 게시 테마(환경에 있는 것)의 첫 글 요일 1문제. 미션이 환경 것이라 적재 스크립트가 입력 방식에 맞춰 `text`를 넣는다
- `nickname`은 적재 때 쓰는 가상 닉네임(`eval3a` 등 영문, 윈도우 셸에서 한글 인자가 깨지지 않게). 어느 글에도 들어가지 않는다(검사함)

## queries.jsonl

```json
{"queryId": "q006", "studentKey": "E3A", "split": "tune", "category": "ANSWER",
 "query": "길고양이한테 물그릇 놓아 준 얘기", "gold": [{"week": "W1", "themeKey": "T01"}],
 "expect": "RESULTS", "evidence": "W1.TUE", "mustContain": ["길고양이", "물그릇"], "checkedBy": []}
```

- `gold`: 그 학생 완주 회차 중 정답 회차(주·테마). 없으면 빈 배열
- `expect`: `RESULTS`·`NO_RESULTS`·`NO_RECORDS`
- `evidence`: 정답 근거 위치(`W1.TUE`, `title`, `theme`, 다른 학년 테마 키, `W7.MON`·`EXTRA`·`CURRENT`)
- `mustContain`: 근거 글에 꼭 있는 말. 답 내용·여러 회차는 이 말이 정답 회차에만 있는지, 범위 시험은 완주 회차에는 없는지 검사함
- `mustNotContain`: 관련 없음·다른 학생 질문의 핵심 낱말. 그 학생 회차 어디에도 없어야 함
- `checkedBy`: 정답을 확인한 사람 이름. 비어 있는 질문은 러너가 빼고 뺀 수를 적는다

## 질문 종류 (학생당 15개, 삭제 학생 2개)

| 종류 | 개수 | 뜻 | 기대 |
|---|---|---|---|
| `TITLE` | 2 | 테마 제목 낱말이 들어간 질문 | 그 회차 |
| `PARAPHRASE` | 3 | 제목 낱말 없이 다른 말로 | 그 회차 |
| `ANSWER` | 3 | 학생이 쓴 답의 소재로 | 그 답이 있는 회차 |
| `MULTI` | 1 | 두 회차 답에 같은 소재 | 두 회차 모두 |
| `NONE` | 2 | 그 학생 기록과 관련 없는 일 | `NO_RESULTS` |
| `OTHER` | 2 | 다른 학년 테마(그 학생은 받은 적 없음) | `NO_RESULTS` |
| `SCOPE` | 2 | W7 미완주 회차·EXTRA·실행 주 글에만 있는 소재 | `NO_RESULTS`, 그 시도가 나오면 범위 위반 |
| `DELETED` | 2 | 삭제한 학생의 질문 | `NO_RECORDS` |

- 나누기별: 조정용·평가용 각각 결과 있음 36 · 거절 24, 삭제 2 → 모두 122
- 같은 학년 다른 학생의 답 소재는 질문으로 쓰지 않았다. 같은 학년은 테마가 같아 "관련 없음"인지 사람마다 판단이 갈리기 때문이다
- 모든 질문·방식 결과에 다른 학생·진행 주·EXTRA·액자 없는 회차·삭제 학생 시도가 하나라도 나오면 범위 위반으로 센다(정답과 별도)

## 만드는 순서

환경 변수는 `infrastructure/aws/demo_account_data.py` 머리말과 같다(`DEMO_API_BASE`·`DEMO_PARENT_*`·`DEMO_ADMIN_*`). 학부모는 평가 전용 계정을 쓴다.

학부모 1명당 자녀가 3명까지라(core `MAX_CHILDREN`) `students.json`의 `parent` 칸(a~d)마다 학부모를 나눈다. 초3·초5 짝(E3A·E5A …)이 한 학부모, 삭제용 E3X는 d 아래. 로그인 ID는 `DEMO_PARENT_LOGIN` 뒤에 a~d를 붙인 값(`evalparent` → `evalparenta`~`evalparentd`), 비밀번호는 모두 `DEMO_PARENT_PASSWORD`(8자 이상). 학부모 로그인 ID 규칙이 영문 소문자·숫자 4~30자라 하이픈은 쓸 수 없다

1. `python -I load_via_api.py children`: 평가 학부모 4명 아래 가상 자녀 9명 등록, 학생 ID를 적재 표에 기록
2. core_db에 `infrastructure/aws/prepare-demo-account-students.sql`을 초3·초5 짝마다 실행(`-v g3=eval3a -v g5=eval5a …`, 4번). 9명 모두 `is_demo`로 표시돼 리텐션 지표에서 빠지고, 초5는 결제 없는 시험 구독을 받아 EXTRA를 풀 수 있다. `E3X`는 표시하지 않아도 된다
3. `python -I load_via_api.py themes`: `themes.json` 16개를 작성 → 검토 요청 → 게시(미션 = `students.json` 학년 표). 같은 제목 테마가 있으면 이어서 게시하고, 같은 학년·주에 다른 게시 테마가 있으면 멈춘다
4. 주마다 core·learning 시계를 그 주 토요일 14:00 KST(`FAKETIME=@<토요일> 05:00:00`)로 옮기고 `python -I load_via_api.py solve --week W1` … `W7`. 서버의 이번 주·테마가 맞지 않으면 멈춘다. W1~W6은 다섯 문제, W7은 세 문제
5. 시계를 되돌린 뒤(실제 시각, W7 다음 주 화요일 이후: 무료 초3의 화요일 서술 문제가 열려야 함) `extra` → `current` → `delete`
6. `python -I load_via_api.py manifest`로 적재 수 확인. 검색 문서가 모두 `READY`가 될 때까지 1~2분 기다린다(러너가 확인)

- 적재 표 기본 위치 `evaluation/results/memory/load-manifest.json`. 학생·테마·시도 ID와 주·요일·맥락만 있고 원문은 없다. 환경마다 값이 달라 커밋하지 않는다
- 다시 실행해도 된다. 이미 끝낸 요일은 건너뛰고(그때는 시도 ID를 비워 두고 러너가 학생·테마·주·미션으로 채움), 삭제한 학생은 건너뛴다

## PC(compose)로 실행

kind 없이 PC 한 대에서 한다. E2E 스택(`compose.e2e.yaml`: llm-stub·합성 시드·동의 문서·상품) 위에 `compose.memory-eval.yaml`(시험 시계·임베딩만 실제 OpenAI)을 얹는다. Docker Desktop과 OpenAI 키(임베딩용)가 필요하다. 아래는 저장소 루트의 PowerShell 기준

```powershell
# 0) 공통
$C = "-p","mem-eval","--env-file","infrastructure/stubs/e2e.env","-f","compose.yaml","-f","compose.minio.yaml","-f","compose.e2e.yaml","-f","compose.memory-eval.yaml"
$env:EVAL_OPENAI_API_KEY = "<OpenAI 키>"   # 화면·파일에 남기지 않기
$FT = "/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1"

# 1) 이미지: core·learning 기본 이미지를 만들고 시험 시계 이미지를 얹음
docker compose -p mem-eval --env-file infrastructure/stubs/e2e.env -f compose.yaml build core-service learning-service
docker build -f infrastructure/aws/demo-clock.Dockerfile --build-arg BASE=mem-eval-core-service -t mem-eval-core-clock .
docker build -f infrastructure/aws/demo-clock.Dockerfile --build-arg BASE=mem-eval-learning-service -t mem-eval-learning-clock .

# 2) 띄우기(실제 시각)
docker compose @C up -d --build --wait core-service learning-service ai-service

# 3) 계정: 관리자(CONTENT)는 SQL로, 학부모는 가입 API로
$env:ADMIN_PASSWORD = "<12자 이상>"
python scripts/admin_account_sql.py --login-id eval-admin --name EvalAdmin --permissions CONTENT | docker compose @C exec -T postgres psql -v ON_ERROR_STOP=1 -U sagomungchi -d core_db
$env:DEMO_API_BASE = "http://127.0.0.1:8080/api/v1"; $env:DEMO_ORIGIN = "http://127.0.0.1:5272"   # e2e.env AUTH_WEB_ORIGIN과 같아야 함
$env:DEMO_ADMIN_LOGIN = "eval-admin"; $env:DEMO_ADMIN_PASSWORD = $env:ADMIN_PASSWORD
$env:DEMO_PARENT_LOGIN = "evalparent"; $env:DEMO_PARENT_PASSWORD = "<학부모 비밀번호 8자 이상>"   # 학부모 4명(evalparenta~d) 같은 비밀번호
$L = "evaluation/datasets/memory/load_via_api.py"
python -I $L parent-signup
python -I $L children

# 4) is_demo 표시·초5 시험 구독(E2E-PLUS)
docker compose @C cp infrastructure/aws/prepare-demo-account-students.sql postgres:/tmp/prepare.sql
foreach ($x in "a","b","c","d") { docker compose @C exec -T postgres psql -v ON_ERROR_STOP=1 -U sagomungchi -d core_db -v g3=eval3$x -v g5=eval5$x -v product_code=E2E-PLUS -f /tmp/prepare.sql }

# 5) 테마 게시(실제 시각, W7 다음 주 이후)
python -I $L themes

# 6) 주마다 시계를 그 주 토요일 14:00 KST(05:00 UTC)로 옮겨 풀이
$weeks = @(("W1","2026-10-03"),("W2","2026-10-10"),("W3","2026-10-17"),("W4","2026-10-24"),("W5","2026-10-31"),("W6","2026-11-07"),("W7","2026-11-14"))
foreach ($w in $weeks) {
  $env:EVAL_LD_PRELOAD = $FT; $env:EVAL_FAKETIME = "@$($w[1]) 05:00:00"
  docker compose @C up -d --wait --no-deps core-service learning-service
  python -I $L solve --week $w[0]
}

# 7) 실제 시각으로 되돌린 뒤 EXTRA·실행 주·삭제(실행 주 화요일 이후)
$env:EVAL_LD_PRELOAD = ""; $env:EVAL_FAKETIME = "+0"
docker compose @C up -d --wait --no-deps core-service learning-service
python -I $L extra; python -I $L current; python -I $L delete; python -I $L manifest

# 8) 검색 평가. 내부 토큰은 서비스별(#675)이라 러너는 core 호출자 토큰을 씀(learning이 core에 /internal/** 허용)
$env:T = ((Get-Content infrastructure/stubs/e2e.env | Select-String '^INTERNAL_TOKEN_CORE=').Line -split '=',2)[1]
$R = "evaluation/runners/memory_search_eval.py"; $PL = "docker compose $($C -join ' ') exec -T postgres psql -U sagomungchi -d learning_db"
# 8-1) 벡터만(V): 질의 변환 끄고 기준값 -1로 모음 → score가 조정용으로 기준값을 고름
$env:EVAL_MIN_SIMILARITY = "-1"; $env:EVAL_QUERY_REWRITE = "false"; docker compose @C up -d --wait --no-deps learning-service
python -I $R collect --learning-url http://127.0.0.1:8081 --token $env:T --psql $PL --label pc-<날짜> --environment "PC compose(E2E), 벡터만"
python -I $R score --raw evaluation/results/memory/memory@1__pc-<날짜>.raw.json
# 8-2) 하이브리드(H, #682): ai를 실제 LLM으로, 질의 변환 켜고 서비스 기준값 0.35 → 받은 그대로 채점(--as-served)
$env:EVAL_LLM_BASE_URL = "https://api.openai.com/v1"; $env:EVAL_LLM_MODEL = "gpt-6-luna"; docker compose @C up -d --wait --no-deps ai-service
$env:EVAL_MIN_SIMILARITY = "0.35"; $env:EVAL_QUERY_REWRITE = "true"; docker compose @C up -d --wait --no-deps learning-service
python -I $R collect --learning-url http://127.0.0.1:8081 --token $env:T --psql $PL --label pc-<날짜>-hybrid --warmup 2 --repeats 1 --environment "PC compose(E2E), 하이브리드"
python -I $R score --raw evaluation/results/memory/memory@1__pc-<날짜>-hybrid.raw.json --as-served
# 8-3) 되돌림: 가짜 LLM, 질의 변환 끔, 기준값 0.35
Remove-Item Env:EVAL_LLM_BASE_URL, Env:EVAL_LLM_MODEL; docker compose @C up -d --wait --no-deps ai-service
$env:EVAL_MIN_SIMILARITY = "0.35"; $env:EVAL_QUERY_REWRITE = "false"; docker compose @C up -d --wait --no-deps learning-service
```

- 하이브리드 카드 점수는 회차 최고 벡터 유사도라, 키워드로만 들어온 회차는 0.35보다 낮을 수 있음 → 기준값으로 다시 자르지 않고 `--as-served`로 받은 그대로 채점. 질문마다 LLM 변환(2~5초)이 있어 반복 1회
- 개선 후보 `text-embedding-3-large`(`dimensions=1536`, DB 그대로)는 ai만 `$env:EVAL_EMBEDDING_MODEL = "text-embedding-3-large"`로 다시 띄우고 모델 이름을 확인한 뒤, learning_db에서 `UPDATE memory_search_doc SET status='PENDING', retry_count=0, lease_until=NULL WHERE status='READY'`를 **한 번만** 실행해 다시 임베딩(약 5분)한 다음 8-1·8-2를 같은 순서로. 끝나면 small로 같은 방법으로 되돌림. 운영·시연 DB에는 이 UPDATE를 쓰지 않음
- 명령의 `<…>` 자리 표시는 실제 값으로 바꿔 넣음(키 자리에 글자 그대로 넣으면 ai가 헤더 오류로 503)

- 시계를 옮기는 동안 core·learning이 다시 뜬다(주마다 1~2분). 서버 이번 주가 맞지 않으면 `solve`가 멈춘다
- 설명 20건(실제 LLM)은 ai만 `$env:EVAL_LLM_BASE_URL = "https://api.openai.com/v1"; $env:EVAL_LLM_MODEL = "gpt-6-luna"; docker compose @C up -d --wait --no-deps ai-service`로 다시 띄워서 한다(PowerShell은 빈 값을 넣으면 변수가 지워져 llm-stub로 돌아가므로 주소를 직접 씀). 설명 표시지는 따로
- 끝나면 `docker compose @C down -v`로 지운다(평가 기록·임베딩 모두 삭제). 이 스택은 평가 전용이고 운영·시연 데이터와 섞이지 않는다

## 평가 실행

러너 `evaluation/runners/memory_search_eval.py`(표준 라이브러리만, DB는 psql 명령으로 읽기 전용)

1. learning에 `MEMORY_MINIMUM_SIMILARITY=-1`(벡터만 잴 때)을 넣고 다시 띄운다(평가 동안만). 하이브리드는 0.35 그대로
2. `collect --learning-url <learning 내부 주소> --token "<core 호출자 내부 토큰>" --psql "<learning_db psql 명령>" --label <이름>`: 문서 상태 확인 → V(내부 검색 API, 예열 5회 뒤 질문마다 3회) → K1·K2(읽기 전용 SQL) → `memory@1__<이름>.raw.json`
3. learning 기준값을 0.35로 되돌린다
4. `score --raw <raw 파일>`: 조정용으로 기준값(0.10~0.60) 고르기 → 평가용 V(고른 값·0.35)·K1·K2 지표, 범위 위반, 응답 시간, 통과 기준 → `memory@1__<이름>.json`. 정답을 확인한 사람 수 하한은 `--min-checkers`(기본 1, 평가용 2명 이상 58·3명 50). 하이브리드처럼 서비스 기준값으로 받은 결과는 `--as-served`(기준값을 고르지 않고 그대로 채점, 이름 `V@served`)
5. (선택) `usage --psql "<core_db psql 명령>" --since <모으기 시작> --until <끝>`: `MEMORY_EMBEDDING` 호출 수·입력 토큰

## 정답 확인

1. `python -I answer_check.py page --split eval`(조정용 `tune`, 삭제 `deleted`)로 정답을 뺀 확인 페이지를 만들어 확인자에게 준다. 확인자는 브라우저로 열고 질문마다 그 학생 6회차 중 정답 회차를 고른다(관련 없음·범위 시험은 "없음", 여러 회차면 모두). 회차 기록에는 학생 답뿐 아니라 테마 제목·문제 전 대화도 들어감. 다 고르면 "결과 파일 저장"으로 받은 json을 돌려받음
2. `python -I answer_check.py compare --answers <json>`으로 `gold`와 맞춰 보고, 다르면 근거를 다시 보고 질문·정답을 고치거나 평가에서 뺀다. `check_dataset.py`를 다시 돌린다
3. `compare --answers <json> --apply <이름>`으로 같은 질문의 `checkedBy`에 이름을 넣는다
4. 2026-11-16: 담당자 122개 모두, 평가용 다른 확인자 재현 52/60·동섭 56/60 일치(갈린 것은 기록에 낱말이 그대로 있거나 바꿔 말한 질문의 해석 차이라 정답표 유지)
5. 확인 페이지·돌려받은 json에는 학생 답이 들어 있어 커밋하지 않음(`.gitignore`)
