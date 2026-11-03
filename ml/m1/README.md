# M1 수학 풀이 점검 모델

학생의 수학 풀이를 받아 정답 여부·필수 과정 실수·계산 실수를 보는 모델의 학습·평가 코드 (이슈 #263).
로컬 MVP(`sayu_project/mvp`)에서 만든 코드를 저장소로 옮긴 것이며, 서빙(scoring-service, #88)은 이 폴더 범위가 아니다.

> AI Hub 원본·가공본(`work/records.csv`)·EDA 예시·모델 가중치는 저장소에 넣지 않는다 (NFR-DAT-03, architecture 5장: 가중치는 승인 후 S3). `.gitignore`로 막혀 있다.
> AI Hub 데이터는 외부 LLM API로 보내지 않는다.

## 현재 상태 (2026-11-02) — 기준선까지, 본 학습 전

| 항목 | 내용 |
|---|---|
| 데이터 | AI Hub 71716(수학 과목 자동 풀이) 손글씨풀이 **라벨링** zip 16개(TL_3·VL_3)만 사용. 풀이 레코드 177,804건 |
| 분할 | AI Hub Training/Validation은 문항은 다르지만 그룹(숫자만 바꾼 쌍둥이 문항)이 2,536/2,569개 겹침 → 합친 뒤 그룹 id 해시로 train 80 / val 10 / test 10 |
| 기준선 (test 16,913건, 정답 여부 균형정확도) | 다수 클래스 0.500, 규칙 "마지막 숫자=정답" 0.642, 규칙 "정답 숫자가 풀이에 있음" **0.703** (`results/eval_m1.md`) |
| 모델 | `klue/roberta-base` + 출력 3개(정답 여부·필수 과정 실수·계산 정확도). **학습된 모델 없음**: 지금 가중치는 코드 확인용 실행(2,000건·1에폭, 검증 균형정확도 0.5)뿐이고 저장소에 넣지 않음 |
| 허용 기준 | 정하지 않음(팀 결정 대상). 통과해도 "71716 기준"이라고만 적음 |
| 서비스 | scoring은 M1 "미학습 비활성" 계약(#88). 국어(M2) 우선·M1 후순위(#213) |

## 데이터에서 확인한 것 (로컬 MVP README에서 옮김, 처음 확인은 초5 Training 22,698 + Validation 2,607건)

- 풀이 1건 = JSON 1개. 문제·모범답안·학생 풀이가 한 파일에 같이 있다. 파일명 `_O/_X` = 정답/오답 (전체 177,804건 중 불일치 1건, `results/eda_71716.md`)
- 텍스트는 손글씨를 OCR한 **LaTeX**(`$\frac{3}{8}$`, 세로셈 `\begin{array}`) → `scripts/mathtext.py`가 평문(`3/8`, `34 / 15 / 19`)으로 바꾼다
- `id = 그룹_문항`. 같은 그룹은 숫자·이름만 바꾼 쌍둥이 문항인데 AI Hub Training/Validation이 **그룹을 공유**한다(초5 339/339, 전체 2,536/2,569). 그대로 쓰면 평가 점수가 부풀려지므로 그룹 단위로 다시 나눈다
- 필수 과정 실수 있음 83%(정답 풀이도 대부분 1개 이상). 계산 정확도에는 0/1만 있고 0.5가 없다 → 클래스는 데이터에서 읽는다
- 모델 입력 = `문제 / 정답` + `학생 풀이`. 정답이 맞는지는 문제를 봐야 알 수 있어 풀이만 넣지 않는다. 그래서 M1을 쓰는 미션은 모범 정답이 있어야 한다
- 71716 점수는 **손글씨 OCR 풀이** 기준이다. 앱에서 학생이 직접 친 풀이에 대한 정확도는 자체 미션 표본으로 따로 잰다

## 폴더 구조

```
ml/m1/
├─ scripts/
│  ├─ common.py     # 경로, 71716 zip 읽기, 레코드 만들기 (라벨 정의는 파일 머리말)
│  ├─ mathtext.py   # OCR LaTeX → 평문, 모델 입력 형식(model_input)
│  ├─ eda.py        # 데이터 구조 확인 → work/reports/eda_71716.md
│  ├─ prepare.py    # 학습용 표 + 그룹 단위 분할 → work/records.csv
│  ├─ train.py      # roberta 파인튜닝 → models/
│  ├─ evaluate.py   # 기준선·모델 비교 → results/eval_m1.md
│  └─ model.py      # 모델 구조(build_model) + 오프라인 평가용 불러오기(available·meta·predict_many)
├─ tests/test_m1.py # 가짜 zip으로 eda·prepare·evaluate, 평문화·모델 입력·모델 구조
├─ results/         # 커밋하는 결과(원문 없음): eval_m1.md, eda_71716.md(예시 절 제외)
├─ data/            # (커밋 안 함) AI Hub zip을 여기 두거나 경로를 인자·.env로 지정
├─ work/            # (커밋 안 함) records.csv, EDA 리포트 원본(예시 절 포함)
├─ models/          # (커밋 안 함) 학습한 가중치
├─ pyproject.toml
└─ uv.lock
```

## 실행

```bash
cd ml/m1
uv sync

# 데이터 위치: 인자로 주거나 .env에 AIHUB_71716_DIR=<받은 폴더> (zip은 풀지 않아도 됨)
uv run python scripts/eda.py "<110.수학 과목 자동 풀이 데이터 폴더>"
uv run python scripts/prepare.py "<같은 폴더>"
uv run python scripts/evaluate.py            # models/에 가중치가 없으면 기준선만

# 학습 (GPU 권장, CPU는 전체 수십 시간)
uv run python scripts/train.py --limit 2000 --epochs 1   # 코드가 도는지 빠르게 확인
uv run python scripts/train.py --epochs 2                # 전체

uv run pytest           # 테스트 (torch 없으면 모델 구조 테스트는 건너뜀)
uv run ruff check . && uv run ruff format --check .
```

- `eda.py`의 리포트에는 AI Hub 풀이 원문 예시가 들어가므로 `work/reports/`(커밋 안 함)에 쓴다. `results/eda_71716.md`는 예시 절을 뺀 정리본이다.
- `evaluate.py`는 `results/eval_m1.md`를 덮어쓴다(숫자만, 원문 없음).

## 입력 형식

- `mathtext.model_input(question, reference_answer, solution)` → (`"문제: … / 정답: …"`, 평문 풀이)
- 학습·평가와 서비스 추론은 같은 형식을 써야 한다. 가중치의 `meta.json`에 `input_format: "mathtext.model_input-v1"`로 기록되며, scoring에서 M1을 구현할 때 이 함수와 `build_model` 구조를 맞춰야 한다.

## 다음 단계 (이 이슈 범위 밖)

1. 풀이 과정 라벨 뜻 확인: "필수 과정 실수 있음" 83%로 정답 비율 72%보다 높아, `explanation_error_required`를 AI Hub 문서로 다시 확인. 계산 정확도에는 0.5(과정 생략) 값이 없음
2. 허용 기준을 팀과 먼저 정함
3. 전체 학습 후 `evaluate.py`로 기준선(규칙 0.703)과 비교
4. 정답 여부는 서비스에서 정답 키 규칙(`MathEquivalenceJudge`)이 이미 판정하므로, M1의 쓸모는 풀이 과정 점검 쪽. 학습 데이터(손글씨 OCR)와 앱 입력(직접 입력)의 차이는 자체 미션 표본으로 따로 잼
