# 답변 표현 분류 모델 (tox)

학생 답변에서 단어 목록(`ExpressionPolicy`, #205)이 놓치는 욕 없는 모욕·비꼼·돌려 말한 성적 표현을 잡는 한국어 2분류 모델의 학습·평가 코드 (이슈 #690, 에픽 #688).
서빙(scoring-service `POST /internal/toxicity/checks`, #691)과 learning 호출(#692)은 이 폴더 범위가 아니며, 여기서는 학습·평가·모델 폴더 만들기와 재학습 작업(#729: 업로드·`REGISTERED` 자동 등록까지, 활성화 안 함)을 한다.

> 원자료·분할·체크포인트·모델 폴더는 저장소에 넣지 않는다 (NFR-DAT-03). `.gitignore`로 막혀 있다.
> 아이 말투 학습 문장은 Claude가 지은 문장으로, NFR-DAT-03(생성형 AI 출력 학습 미사용)의 예외로 쓴다.
> 학습·평가 데이터는 외부 LLM API로 보내지 않는다. AI Hub 학생 답안(71818 서술형 초5·6)은 학습에 쓰지 않고 오탐 확인에만 쓰며, 원문은 저장·출력·커밋하지 않는다(확률 요약만 `results/`).

## 최신 상태 (2026-11-19)

| 항목 | 내용 |
|---|---|
| 서비스 모델 | `tox-koelectra-small` 1.0-1119: `monologg/koelectra-small-v3-discriminator`(Apache 2.0) 2라벨(0 정상, 1 막을 글)을 아이 말투 재학습한 KcELECTRA-base(선생님)에게 증류 |
| 데이터 | 학습 K-MHaS·Korean HateSpeech(BEEP!)(CC BY-SA 4.0) + 직접 지은 아이 말투 문장 691개 ×3, 외부 시험 APEACH, 아이 시험 문장 250개(직접 지음) |
| 입력 | 학생이 쓴 칸별 글, 128토큰 창·겹침 32, 창 하나라도 확률 ≥ 임계값이면 걸림(api-spec 4.3.4) |
| 서비스 기본값 | 파일은 fp32, scoring이 불러올 때 Linear 채널별 int8 동적 양자화(`quantization: int8-dynamic-channel`, `scripts/quant.py`), 임계값 0.99 |
| 임계값 기준 | 꼭 통과할 글 389개 오탐 0, 단어 목록 대비 정상 추가 오탐 ≤ 1%(검증) |
| 성능(int8 0.99) | 아이 모욕 100개 중 76개(단어 목록과 합쳐, 첫 모델 34), 아이 정상 150개·실제 초5·6 답 16,385개 오탐 0. 어른 K-MHaS 시험 66.79%(첫 모델 71.6%)·APEACH F1 0.507(0.574)로 낮아짐 |
| CPU 지연(1코어 p95) | 1,200자 99ms·1,500자 139ms(작업 공간), 목표 300ms 통과 |
| 재현 | `train.py`가 시드 + GPU 계산 순서를 고정(결정적 학습). 같은 GPU 종류에서 같은 가중치(md5 확인) |

자세한 숫자·후보 비교·한계는 [results/eval_tox.md](results/eval_tox.md). 11/17 첫 모델(KcELECTRA-base, 0.95) 기록도 같은 문서 아래쪽에 있다.

## 폴더 구조

```
ml/tox/
├─ scripts/
│  ├─ prepare_data.py    # 공개 데이터 → 2분류 jsonl (data/processed/), 표준 라이브러리만
│  ├─ kid_data.py        # 아이 말투 학습 문장 만들기·시험 문장과 겹침 검사
│  ├─ make_data_kid.py   # data/processed → p_orig·p_kid(아이 ×3)·p_cont
│  ├─ train.py           # 파인튜닝·이어 학습(--model에 체크포인트 폴더)·증류(--teacher), 결정적 학습
│  ├─ teacher_probs.py   # 증류용 선생님 확률(npz, 글 없음)
│  ├─ eval.py            # 모델만 지표·글별 점수 (results/…/eval_tox*.json)
│  ├─ wordlist.py        # 단어 목록과 함께 쓸 때 지표·임계값 (results/…/wordlist_*.json)
│  ├─ kid_eval.py        # 아이 말투 시험 문장 250개(--test로 다른 시험 파일)
│  ├─ kid_variants.py    # 아이 시험 문장을 모양만 바꾼 시험 만들기
│  ├─ mustpass_probs.py  # 꼭 통과할 글 전부의 확률(저장소에서 다시 뽑음: 11/19 389개, #837 뒤 387개)
│  ├─ aihub_probs.py     # 실제 초등 답 확률(원문 저장 안 함)
│  ├─ quant.py           # scoring 로더와 같은 채널별 int8
│  ├─ latency.py         # CPU 1코어 지연 (results/…/latency_*.json)
│  └─ retrain.py         # 재학습 작업(#729): 이어 학습·활성 비교·추천 태그·자동 등록
├─ eval_sets/            # 직접 지은 아이 말투 문장(kid_test.json 시험 250 · kid_train.json 학습 691 · kid_test_variants.json 모양 바꾼 시험) · user_probe.json 팀원 문장 13 · must_pass.json 꼭 통과할 글 389 고정본
├─ tests/                # 데이터 정리·임계값 계산·저장 형식·아이 문장·재학습 작업 시험
├─ results/eval_tox.md   # 지표·임계값·지연·한계, results/1119-distill/ 지금 모델 숫자 원본
├─ data/                 # (커밋 안 함) 원자료·분할·선생님 확률·글별 확률
├─ checkpoints/          # (커밋 안 함) 학습한 모델 폴더
├─ Dockerfile            # 재학습 작업 CPU 이미지(빌드 기준은 저장소 루트)
├─ pyproject.toml
└─ uv.lock
```

## 실행

```bash
cd ml/tox
uv sync --frozen
# 1) 데이터 정리: K-MHaS(github adlnlp/K-MHaS data/), BEEP!(github kocohub/korean-hate-speech labeled/), APEACH(HF jason9693/APEACH apeach.test.csv)
uv run python -I scripts/prepare_data.py --kmhas <K-MHaS/data> --beep <korean-hate-speech/labeled> --apeach <apeach.test.csv> --out data/processed
# 2) 아이 말투 문장 붙이기 → data/p_kid
uv run python scripts/make_data_kid.py
# 3) 학습 (GPU 있으면 자동으로 GPU, 동작 확인만: --limit 200 --epochs 1)
#    지금 모델의 선생님·학생 명령은 results/eval_tox.md "재현 (11/19 모델)"
uv run python scripts/train.py --data data/p_kid --out checkpoints/<이름> [--model … --revision … --teacher data/teacher_s48.npz]
# 4) 모델만 지표 + 글별 점수 (--int8: 채널별 동적 양자화, scoring처럼 글 하나씩·창 8개씩)
uv run python scripts/eval.py --model checkpoints/<이름> --int8 --data data/p_kid --save-probs data/probs_int8.npz --out <json>
# 4-1) 단어 목록 결과(results/eval_tox.md 이전 기록 재현의 임시 Kotlin 시험)와 합쳐 임계값을 train_info.json에 씀
uv run python scripts/wordlist.py --probs data/probs_int8.npz --flags data/wordlist_flags.json --eval-json <json> --model checkpoints/<이름> --write
# 4-2) 아이 말투 시험 문장
uv run python scripts/kid_eval.py --model checkpoints/<이름> --int8 --threshold <임계값>
# 5) CPU 1코어 지연
OMP_NUM_THREADS=1 uv run python scripts/latency.py --model checkpoints/<이름> --int8
# 시험
uv run pytest
```

- `eval.py`·`mustpass_probs.py`·`latency.py`는 저장소의 `backend/learning-service/db/seed/demo_missions.sql`, `frontend/web/src/data/classroom/demoGateway.ts`, `ExpressionPolicyTest.kt`에서 꼭 통과할 글을 읽는다. 저장소 밖에서 돌리면 `eval.py`·`latency.py`는 `--repo`로 저장소 위치를 준다. 이렇게 뽑으면 #837 뒤 387개라, 재학습 작업은 `eval_sets/must_pass.json` 389개 고정본을 쓴다
- `python -I`로 `eval.py`를 돌리면 같은 폴더의 `train.py`를 못 불러온다. `uv run python scripts/eval.py`로 돌린다
- 결정적 학습은 같은 시드·GPU 종류·라이브러리에서 같은 가중치를 낸다. 대신 조금 느리다

## 재학습 작업 (#729)

> **운영 실행은 #887 결정 뒤**, CronJob은 #730. 기준·종료 코드·한계는 [learning.md](../../docs/report/learning.md) 16절 "재학습 작업 구현"

```bash
# 저장소 루트에서
docker build -f ml/tox/Dockerfile -t tox-retrain .
docker run --rm --network <learning·core·S3에 닿는 망> \
  -e LEARNING_URL=http://learning-service:8081 -e CORE_URL=http://core-service:8080 \
  -e INTERNAL_TOKEN -e S3_BUCKET -e S3_REGION \
  tox-retrain
# INTERNAL_TOKEN에는 ops 토큰 값(보내는 쪽 이름, architecture 2.2)
# 로컬 MinIO: -e S3_ENDPOINT_URL -e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY
# 운영: -e S3_BUCKET_OWNER (업로드 때 버킷 소유 계정 확인)
# 선택: -e TOX_PUBLIC_DATA_PREFIX(기본 datasets/tox-retrain/public-v1/) -e OMP_NUM_THREADS(기본 2)
```

- 미리 있어야 하는 것: 활성 `tox-` 모델 1개, S3 public-v1 묶음(`train.jsonl`·`valid.jsonl`·`apeach.jsonl`·`wordlist_flags.json`·`must_pass.json`·`manifest.json`)
- 새 라벨 200건 미만이면 종료 코드 0. CPU 2개·메모리 3GiB에서 200건에 약 10~14분([실측](results/eval_tox.md))
- 활성화는 하지 않는다. 등록부의 추천 태그를 보고 사람이 승인한다

## 모델 폴더 (등록부 업로드 단위)

| 파일 | 내용 |
|---|---|
| `config.json`·`model.safetensors` | HF `save_pretrained`, fp32 |
| `tokenizer.json`·`tokenizer_config.json` | 토크나이저 |
| `train_info.json` | `task`·`labels`·`positiveLabel`·`max_length`(128)·`stride`(32)·`threshold`·`thresholdSource`·`quantization`·`baseModel`·`baseRevision`·데이터 출처·학습 설정(`deterministic`)·검증 지표·`distill`(선생님·α·온도). 재학습 모델은 `review_threshold`·`data`(이번 학습 자료만)·`dataSha256`·`initFrom`(출발 모델·내력) |
| `valid_probs.npz` | (업로드 안 함) 검증 확률·라벨, 글 없음 |

- 이름 규칙 `tox-…`, 적용 범위 `answer-filter`, 로더 검사(2분류·`threshold` 필수)는 api-spec 5.2를 따른다. 업로드·사전 검사·활성화는 scoring.md 6장(로컬 확인 결과는 eval_tox.md)
- 학생 학습 1회는 RunPod RTX 4090에서 약 17분(결정적 설정), 선생님 확률 약 1분

## 라이선스

| 대상 | 라이선스 | 확인 |
|---|---|---|
| monologg/koelectra-small-v3-discriminator (지금 모델) | Apache 2.0 | GitHub `monologg/KoELECTRA` LICENSE 원문(HF 모델 카드엔 표기 없음), 2026-11-18 |
| beomi/KcELECTRA-base (선생님·첫 모델) | MIT | HF 모델 API, 2026-11-16 |
| K-MHaS | CC BY-SA 4.0 | HF jeanlee/kmhas_korean_hate_speech 데이터 카드 |
| Korean HateSpeech(BEEP!) | CC BY-SA 4.0 | 저장소 `LICENSE.md` 원문 |
| APEACH | CC BY-SA 4.0 | HF jason9693/APEACH 데이터 카드 |

- 출처는 모델 문서에 표시하고 원자료·고친 데이터는 커밋·배포하지 않는다. 가중치는 S3에서 내부 추론에만 쓴다(learning.md 16절)

## 한계

- 아이 말투 숫자는 직접 지은 문장으로 잰 것이라 부풀었을 수 있다. 실제 아이 모욕 데이터는 없다
- 어른식 욕설·처음 보는 말투(APEACH)는 첫 모델보다 약하다(기준4·5 미달, 담당 결정으로 우선 사용)
- 미션 본문에 나온 말을 허용하는 규칙이 모델에는 없다. 욕과 같은 글자가 든 정상 문장("시바새끼도 귀여워")을 막을 수 있다
- 같은 설정이어도 학습마다 결과가 흔들린다. 결정적 학습은 같은 GPU 종류·라이브러리에서만 같은 가중치를 보장한다
- int8은 같이 계산한 글에 따라 확률이 달라진다. int8 평가는 scoring과 같게 글 하나씩 잰다(`eval.py --int8` 기본)
