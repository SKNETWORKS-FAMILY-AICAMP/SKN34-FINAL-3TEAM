# 이슈 #263 M1 학습·평가 코드 `ml/m1` 이관

M1(수학 풀이 점검) 학습·평가 코드가 저장소 밖 로컬 MVP 폴더(`sayu_project/mvp`, git 아님)에만 있어 분실 위험이 있고 팀원이 볼 수 없었다. architecture 5장 "모델 학습 코드(M2·M1·sLLM)는 `ml/`에서 관리"와 NFR-AIQ-04 검증 방법 "실험 실행 기록"에 맞춰 `ml/m1`로 옮겼다. 목적은 코드 보존·재현이며 M1 본 학습은 범위 밖(이슈 배경, 국어(M2) 우선·M1 후순위 #213).

## 사용자 결정 (11/02)

| 항목 | 결정 | 근거 |
|---|---|---|
| M1 담당자(이슈 확인 필요) | 사용자(로컬 코드 작성자) | 사용자 확인 |
| 범위 | 코드 이관만. M1 라벨 확인·전체 학습은 하지 않음 | 이슈 배경, #213 |
| 평가용 함수 | `build_model`과 함께 `available`·`meta`·`predict_many`(+`_load`)도 옮김. 앱 전용 1건 예측 `predict()`와 `judge_route` 전환만 제외 | `evaluate.py`가 모델 평가에 `available`·`predict_many`를 씀. 설계상 학습·평가(실험)는 `ml/`(architecture 5장, NFR-AIQ-04 "학습·평가"), 서비스 추론만 scoring(#88). `ml/m2`도 평가 글 예측을 `ml/m2` 안에서 함 |
| EDA 리포트 출력 | 기본 출력을 커밋하지 않는 `work/reports/`로. `results/`에는 예시 절을 뺀 정리본만 | `eda.py`가 리포트 끝에 AI Hub 풀이 원문 예시 절을 만들어, 다시 실행하면 커밋 대상 폴더에 원문이 생김. NFR-DAT-03은 "EDA 예시"를 저장소에 넣지 않도록 명시 |
| CI | `ci-ml-m1.yml` 추가(`ci-ml-m2.yml`과 같은 방식) | 코드를 아는 사람이 한 명이라 PR마다 자동 검사 |
| `ml/m2`와 공유 코드 | 없음, 각자 유지 | 이슈 기본 판단 |

## 옮긴 것

| 로컬 | `ml/m1` | 바꾼 것 (로직 그대로) |
|---|---|---|
| `m1/common.py` | `scripts/common.py` | `sys.path` 조작·`sayu.mathtext` import → `mathtext`. 경로: 데이터 기본 `data/71716`(인자·`AIHUB_71716_DIR` 그대로), 가공본 `work/`, 평가 결과 `results/`, EDA 리포트 `work/reports/`(`EDA_REPORT_DIR` 추가), 가중치 `models/` |
| `m1/eda.py`·`prepare.py`·`evaluate.py`·`train.py` | `scripts/` 같은 이름 | import(`common`·`model`), 머리말의 실행 예(`uv run python scripts/…`, 개인 데이터 경로는 자리표시로)와 결과 경로. `eda.py`는 `EDA_REPORT_DIR`에 씀 |
| `sayu/mathtext.py` | `scripts/mathtext.py` | `model_input` 설명 문구만 |
| `sayu/m1.py` | `scripts/model.py` | `build_model`·`available`·`meta`·`_load`·`predict_many`. `MODEL_DIR`은 `common`에서, 앱 전용 `predict()` 제외 |
| `tests/test_m1.py` | `tests/test_m1.py` | 평문화·EDA→분할→기준선 평가(가짜 zip)·모델 구조 테스트만. 앱 연결(pipeline·report·db) 4개 제외. EDA 출력이 `work/` 아래인지 확인하는 테스트 1개 추가 |
| `m1/reports/eval_m1.md` | `results/eval_m1.md` | 그대로 |
| `m1/reports/eda_71716.md` | `results/eda_71716.md` | "예시 (원문 → 평문화)" 절을 빼고 뺀 이유를 한 줄 추가 |
| `m1/requirements-m1.txt` | `pyproject.toml`·`uv.lock` | 로컬 실행 환경과 같은 버전으로 고정: torch 2.14.1, transformers 5.20.2, tokenizers 0.23.3, python-dotenv 1.2.4(`ml/m2`와도 같음) |

- 코드 모양: `ml/m2`와 같은 ruff 설정(줄 100자, E·F·I·B)을 맞추느라 `ruff format`으로 줄바꿈·import 순서가 바뀌었고, `zip()`에 기본값과 같은 `strict=False`를 명시(B905), 한글 폭 때문에 긴 문자열은 이어 붙이기로 나눔(출력 문자열 동일). 한 줄은 f-string 안 식이라 `# noqa: E501`
- 그 밖: `ml/m1/.gitignore`(`data/`·`work/`·`models/`·`checkpoints/`·`*.csv`·`*.zip`·`*.pt`), `README.md`, `.github/workflows/ci-ml-m1.yml`, architecture 5장 트리의 `m1/` 설명

## 넣지 않은 것

- AI Hub 71716 원본 zip, 가공본 `records.csv`(문제·학생 풀이 포함), EDA 예시 절 (NFR-DAT-03)
- 가중치 `models/m1/`(442MB): 코드 확인용 실행(2,000건·1에폭, 검증 균형정확도 0.5)이라 학습된 모델이 아니고, 가중치는 승인 후 S3에 둠(architecture 5장)
- 로컬 MVP 앱 전용 코드: 1건 예측 `predict()`, `pipeline`의 `judge_route` 전환과 그 테스트

## 이슈와 다른 점

- 이슈 "넣지 않는 것"은 `available()`을 앱 전용으로 적었으나 `evaluate.py`가 사용 → 옮김(위 결정). 이슈 작업 위치의 "`sayu/m1.py`의 모델 구조(`build_model`)"에 평가용 함수가 더해짐
- 이슈의 가중치 제외 근거는 "(NFR-DAT-03)" 아래에 있었으나 NFR-DAT-03은 원본·가공본·EDA 예시만 다룸 → 가중치 제외 근거는 architecture 5장(승인 가중치는 S3)
- EDA 리포트 출력 위치, CI 추가, 실제 데이터 재실행 비교는 이슈 본문에 없던 것을 더함
- 완료 조건 "#213 보고서의 'M1 학습 코드 → 별도 이슈'를 이 이슈 번호로 갱신"은 PR #268(#213)에 이미 반영(보고서 3.3 준비 현황·5장 확인 필요의 #263). #268 머지 시 충족, 이 브랜치에서는 그 파일을 고치지 않음(충돌 방지)
- 이슈 본문 수정안은 사용자에게 전달(사용자가 이슈 작성자)

## 검증

- 실제 데이터 재실행(이슈 완료 조건 "데이터가 있으면 다시 실행할 수 있음"): 사용자 로컬의 AI Hub 71716 라벨링 zip 16개로 `ml/m1`에서 `eda.py` → `prepare.py` → `evaluate.py` 실행. 결과물 세 개가 로컬 MVP 결과물과 **바이트 단위로 같음**(`cmp`)
  - `work/records.csv` 75,523,581바이트: 177,796건(읽기 실패 0, 건너뜀 14), 그룹 단위 분할 train 142,710 / val 18,173 / test 16,913건, train과 val·test에 함께 있는 그룹 0
  - EDA 리포트 원본(예시 절 포함, `work/reports/eda_71716.md`): 풀이 레코드 177,804건 등 전부 같음
  - `results/eval_m1.md`: test 16,913건, 정답 여부 균형정확도 다수 클래스 0.500·규칙 0.642·0.703
- `uv run pytest` 4개 통과(torch 모델 구조 테스트 포함), `ruff check`·`ruff format --check` 통과
- CI와 같은 환경(Python 3.12, torch 없음)을 따로 만들어 실행: ruff 통과, 테스트 3개 통과·1개 건너뜀(torch)
- 저장소에 AI Hub 원본·가공본·가중치 없음: `git status --ignored`로 `work/`·`.venv/`가 제외되고 커밋 대상은 코드·`results/`의 숫자 리포트뿐임을 확인(아래 PR 검증에 파일 목록)

## 알려진 한계

- 학습된 M1 모델이 없음. 허용 기준도 미정이라 M1 성능은 말할 수 없음(기준선까지)
- 풀이 과정 라벨의 뜻이 불분명: "필수 과정 실수 있음" 83%로 정답 비율 72%보다 높음. 계산 정확도에 0.5 값 없음 → 본 학습 전에 AI Hub 문서로 확인 필요(README 다음 단계)
- scoring에서 M1을 구현하면 `build_model`·`model_input`과 같은 구조가 두 곳에 생김. 설계상 `ml/`은 학습, scoring은 가중치 로딩이라 피할 수 없고, `meta.json`의 `input_format`(`mathtext.model_input-v1`)으로 맞춤
- `results/eda_71716.md`는 손으로 관리하는 정리본이라 EDA를 다시 돌려도 자동 갱신되지 않음
- 학습 데이터는 손글씨 OCR 텍스트, 앱 입력은 직접 입력이라 분포가 다름(로컬 `eval_m1.md`에도 명시)
