# 답변 표현 분류 모델 (tox)

학생 답변에서 단어 목록(`ExpressionPolicy`, #205)이 놓치는 욕 없는 모욕·비꼼·돌려 말한 성적 표현을 잡는 한국어 2분류 모델의 학습·평가 코드 (이슈 #690, 에픽 #688).
서빙(scoring-service `POST /internal/toxicity/checks`, #691)과 learning 호출(#692)은 이 폴더 범위가 아니며, 여기서는 학습·평가와 등록부에 올릴 모델 폴더 만들기만 한다.

> 원자료·분할·체크포인트·모델 폴더는 저장소에 넣지 않는다 (NFR-DAT-03). `.gitignore`로 막혀 있다.
> 학습·평가 데이터는 외부 LLM API로 보내지 않는다. AI Hub 데이터는 쓰지 않는다.

## 최신 상태 (2026-11-17)

| 항목 | 내용 |
|---|---|
| 모델 | `beomi/KcELECTRA-base`(MIT) `single_label_classification` 2라벨(0 정상, 1 막을 글) |
| 데이터 | 학습 K-MHaS·Korean HateSpeech(BEEP!), 외부 시험 APEACH, 모두 CC BY-SA 4.0 |
| 입력 | 학생이 쓴 칸별 글, 128토큰 창·겹침 32, 창 하나라도 확률 ≥ 임계값이면 걸림(api-spec 4.3.4) |
| 서비스 기본값 | 파일은 fp32, scoring이 불러올 때 Linear 채널별 int8 동적 양자화(`quantization: int8-dynamic-channel`, `scripts/quant.py`), 임계값 0.95(fp32로 쓰면 0.97) |
| 임계값 기준 | 꼭 통과할 글 390개 오탐 0, 단어 목록 대비 정상 추가 오탐 ≤ 1%(검증) |
| 성능(int8 0.95, 시험 K-MHaS) | 단어 목록만 29.3% → 모델을 붙이면 71.7% 잡음(단어 목록이 놓친 것의 59.9%를 더 잡음), 정상 추가 오탐 1.33%. APEACH는 25.9% → 45.1% |
| CPU 지연(1코어 p95) | int8 1,500자 포드 553ms·PC 1,068ms, fp32 1,500자 1,619ms·2,322ms(처리 마감 1.3초 넘음). 목표 300ms는 둘 다 미달. 채널별 int8은 같은 기계에서 per-tensor와 같은 속도 |

자세한 숫자·한계는 [results/eval_tox.md](results/eval_tox.md).

## 폴더 구조

```
ml/tox/
├─ scripts/
│  ├─ prepare_data.py   # 공개 데이터 → 2분류 jsonl (data/processed/), 표준 라이브러리만
│  ├─ train.py          # KcELECTRA 파인튜닝, 등록부 모델 폴더 저장 (checkpoints/)
│  ├─ eval.py           # 모델만 지표·글별 점수 저장 (results/eval_tox*.json)
│  ├─ wordlist.py       # 단어 목록과 함께 쓸 때 지표·임계값 (results/wordlist_*.json)
│  ├─ latency.py        # CPU 1코어 지연 (results/latency_*.json)
│  └─ quant.py          # int8 동적 양자화(채널별, scoring 로더와 같은 방식)
├─ tests/               # 데이터 정리·임계값 계산·저장 형식 시험
├─ results/eval_tox.md  # 지표·임계값·지연·한계
├─ data/                # (커밋 안 함) 원자료·분할
├─ checkpoints/         # (커밋 안 함) 학습한 모델 폴더
├─ pyproject.toml
└─ uv.lock
```

## 실행

```bash
cd ml/tox
uv sync --frozen
# 1) 데이터 정리: K-MHaS(github adlnlp/K-MHaS data/), BEEP!(github kocohub/korean-hate-speech labeled/), APEACH(HF jason9693/APEACH apeach.test.csv)
uv run python -I scripts/prepare_data.py --kmhas <K-MHaS/data> --beep <korean-hate-speech/labeled> --apeach <apeach.test.csv> --out data/processed
# 2) 학습 (GPU 있으면 자동으로 GPU)
#    동작 확인만: --limit 200 --epochs 1
uv run python scripts/train.py --out checkpoints/kcelectra-base-s42 --revision 681201a097b8120e6dd2a2e63a3e13d338736f88
# 3) 모델만 지표 + 글별 점수 저장 (--int8: 채널별 동적 양자화, scoring처럼 글 하나씩·창 8개씩 잼)
uv run python scripts/eval.py --model checkpoints/kcelectra-base-s42 --int8 --save-probs data/probs_int8.npz
# 3-1) 단어 목록 결과(results/eval_tox.md 재현의 임시 Kotlin 시험)와 합쳐 임계값을 train_info.json에 씀
uv run python scripts/wordlist.py --probs data/probs_int8.npz --flags data/wordlist_flags.json --eval-json results/eval_tox_int8.json --model checkpoints/kcelectra-base-s42 --write
# 4) CPU 1코어 지연
OMP_NUM_THREADS=1 uv run python scripts/latency.py --model checkpoints/kcelectra-base-s42
# 시험
uv run pytest
```

- `eval.py`는 저장소의 `backend/learning-service/db/seed/demo_missions.sql`, `frontend/web/src/data/classroom/demoGateway.ts`, `ExpressionPolicyTest.kt`에서 꼭 통과할 글을 읽는다. 저장소 밖에서 돌리면 `--repo`로 저장소 위치를 준다
- `python -I`로 `eval.py`를 돌리면 같은 폴더의 `train.py`를 못 불러온다. `uv run python scripts/eval.py`로 돌린다

## 모델 폴더 (등록부 업로드 단위)

| 파일 | 내용 |
|---|---|
| `config.json`·`model.safetensors` | HF `save_pretrained`, fp32 |
| `tokenizer.json`·`tokenizer_config.json` | 토크나이저 |
| `train_info.json` | `task`·`labels`·`positiveLabel`·`max_length`(128)·`stride`(32)·`threshold`·`thresholdSource`·`quantization`(`int8-dynamic-channel`이면 scoring이 불러올 때 채널별 int8, `wordlist.py --write`·`eval.py --write`가 씀)·`baseModel`·`baseRevision`·데이터 출처·학습 설정·검증 지표 |
| `valid_probs.npz` | (업로드 안 함) 검증 확률·라벨, 글 없음 |

- 이름 규칙 `tox-…`, 적용 범위 `answer-filter`, 로더 검사(2분류·`threshold` 필수)는 api-spec 5.2를 따른다. 업로드·preflight는 #691
- 학습 1회는 RunPod RTX 4090에서 4분 20초라 가중치는 다시 만들 수 있다

## 라이선스

| 대상 | 라이선스 | 확인 |
|---|---|---|
| beomi/KcELECTRA-base | MIT | HF 모델 API, 2026-11-16 |
| K-MHaS | CC BY-SA 4.0 | HF jeanlee/kmhas_korean_hate_speech 데이터 카드 |
| Korean HateSpeech(BEEP!) | CC BY-SA 4.0 | 저장소 `LICENSE.md` 원문 |
| APEACH | CC BY-SA 4.0 | HF jason9693/APEACH 데이터 카드 |

- 출처는 모델 문서에 표시하고 원자료·고친 데이터는 커밋·배포하지 않는다. 가중치는 S3에서 내부 추론에만 쓴다(learning.md 16절)

## 한계

- 학습 데이터가 성인 뉴스·연예 댓글이라 초등 답과 말투가 다르다
- 미션 본문에 나온 말을 허용하는 규칙이 모델에는 없다
- 다른 출처(APEACH) 재현율 0.390, 시드 1개
- fp32 1,500자 지연이 scoring 처리 마감 1.3초를 넘어 int8로 쓴다(채널별, 시험 재현율 0.82%p 손해). 운영 Pod에서 fp32가 마감 안이면 되돌린다(#691)
- int8은 같이 계산한 글에 따라 확률이 달라진다. int8 평가는 scoring과 같게 글 하나씩 잰다(`eval.py --int8` 기본)
