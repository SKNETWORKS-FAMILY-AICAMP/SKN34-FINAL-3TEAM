# 설명 sLLM (#475)

학생 글과 M2 항목 점수를 받아 학부모용 대표 답변 설명을 만드는 모델의 학습·평가 스크립트와 서빙·실측·평가 기록이다.
서비스 연결(ai-service `report_explanation`, report-service `explanation_generator`)은 이 폴더 범위가 아니다.

> AI Hub 원본·가공본·모델 가중치·어댑터 파일은 저장소에 넣지 않는다(NFR-DAT-03).
> 엔드포인트 주소·키도 기록하지 않는다. 숫자 기록은 [`results/gemma-lora-20261117.json`](results/gemma-lora-20261117.json).

## 확정 모델 (2026-11-17)

주간 서술·저녁 질문·대표 답변 상세 설명은 같은 LoRA Gemma를 쓴다. 다른 모델로 대체하지 않는다
([gemma-explanation-validation](../../docs/report/gemma-explanation-validation.md#2026-11-17-향후-리포트-모델-고정)).

| 항목 | 값 | 근거 |
|---|---|---|
| 기반 모델 | `cyankiwi/gemma-4-26B-A4B-it-qat-AWQ-INT4` (Apache-2.0, 17.2GB `model.safetensors` 1개) | 서빙 이름과 HF 저장소 이름 일치. 이미지 빌드 기록이 없어 실제로 받은 저장소는 **미확인** |
| 기반 revision | HF 최신 `76373001e106330a6815f237ef00838c7fed9356` (2026-10-19 수정) | 이미지에 들어간 revision은 **미확인** |
| 어댑터 | PEFT LoRA, r=16, alpha=16, dropout 0, `q_proj`·`k_proj`·`v_proj`·`o_proj` | `adapter_config.json` |
| 학습 기준 모델 | `/workspace/models/gemma-4-26b-qat`를 16비트로 학습(`train_lora.py`, `load_in_4bit=False`) | QAT 16비트 원본(`google/gemma-4-26B-A4B-it-qat-q4_0-unquantized`로 보임, 저장소 이름은 **미확인**)으로 학습하고 AWQ 양자화본에 얹어 서빙 |
| merge 버전 | 없음 | AWQ에 합치려면 bf16 원본에 합친 뒤 다시 양자화해야 함 |

### 어댑터 파일

비공개 HF 저장소에 보관한다. 아래 해시는 2026-11-17 로컬 사본으로 계산했고, HF 원본과의 대조는 하지 않았다.

| 파일 | 크기 | sha256 |
|---|---|---|
| `adapter_model.safetensors` | 45,991,472 bytes | `a56fe8f458f73a0b195d0108ab1a7b8d3be59d448bb0c4b8ec8b89eb8072fd25` |
| `adapter_config.json` | 1,290 bytes | `4c96bca2eabeae7a787b3b9cb8a3043f31f57a33308a8c6e2a909d0c1e3041b6` |

## 스크립트 (`scripts/`)

RunPod Pod(`/workspace`) 안에서만 돌린다. 화면에는 개수·지표 숫자만 찍고, 학생 글·이유 문장·생성 원문은 Pod 안 파일에만 쓴다.
AI Hub 원본·JSONL·생성 결과는 저장소에 넣지 않는다.

| 순서 | 파일 | 내용 |
|---|---|---|
| 1 데이터 준비 | `make_jsonl.py` | AI Hub 71818(서술형)·71819(논술형) → 답 1개당 한 줄 JSONL. 입력은 글 종류·학년·주제·학생 글·항목 점수(두 전문가 평균 사사오입), 출력은 항목별 전문가 이유 문장. 점수 표현·채점 이야기·원문에 없는 인용·15자 미만 문장은 그 항목만 뺌. 기본 학습 8,000개·검증 200개(종류별 반씩), 1,500음절 초과 글 제외, seed 42 |
| 2 학습 | `train_lora.py` | Unsloth `FastModel` 16비트 LoRA(A100 80GB 기준). 언어 모델 어텐션 q·k·v·o만(MoE 전문가는 vLLM LoRA 지원이 불확실해 제외, 붙으면 중단). 답 부분만 손실 계산 |
| 3 평가 | `eval_lora.py` | 검증 앞 N개(기본 50)로 학습 전·후 비교: 형식 완전성, 점수·숫자 노출, 인용이 글에 있는지, 전문가 문장과 글자 2-gram F1(참고), 길이·생성 시간 |
| 4 서빙 확인 | `vllm_check.py` | vLLM에서 어댑터가 붙는지(LoRA 켠/끈 결과 비교), 생각 끄기 프롬프트가 학습 때와 같은지, Unsloth 결과와 겹침. 16비트 원본과 AWQ(`--model .../gemma-awq --tag awq`) 둘 다 |
| 5 인용 검사 | `check_quotes.py` | 전문가 정답·학습 전·학습 후의 인용을 그대로/거의 같음(유사도 0.8 이상)/없음으로 나눠 셈 |

### 학습 설정 (`train_lora.py` 기본값)

| 항목 | 값 |
|---|---|
| LoRA | r 16, alpha 16, dropout 0, bias none |
| 최대 길이 | 3072토큰(넘는 답은 제외) |
| 학습 | lr 1e-4 cosine, warmup 3%, 1 에폭, 배치 1 × 누적 8, bf16, `adamw_8bit`, seed 42 |
| 평가·저장 | 한 에폭의 1/5마다(최소 20스텝), 체크포인트 3개 유지 |

### vLLM 확인 설정 (`vllm_check.py` 기본값)

`enable_lora=True`, `max_lora_rank=16`, `max_loras=1`, `max_model_len=4096`, `gpu_memory_utilization=0.88`, `temperature` 0, 최대 800토큰.
vLLM은 Unsloth와 패키지가 충돌해 별도 가상환경(`/workspace/vllm-env`)에서 돌린다. 운영 RunPod 엔드포인트는 `max_model_len` 8192다.

### 없는 것

- 양자화(GGUF 등) 스크립트와 CPU 실측: 없음. AWQ 기반 모델은 공개 양자화본을 그대로 쓴다
- 테스트(가짜 데이터): 없음
- 평가 결과 숫자: `eval_lora.py`·`vllm_check.py` 실행 결과는 Pod 안에만 남아 `results/`에 없다

## 서빙

| 항목 | 값 |
|---|---|
| 방식 | RunPod 서버리스, vLLM 0.32 직접 빌드 이미지(기반 모델을 이미지 `/models/llm`에 포함) |
| `/v1/models` 응답 (2026-11-17 조회) | `gemma-4-26b-a4b-it-qat-awq-int4`(`max_model_len` 8192), LoRA `explain`(부모 위 모델) |
| LoRA 설정 | 워커 환경 `LORA_MODULES={"name":"explain","path":"<HF 저장소>"}`(리스트가 아닌 객체 하나), 비공개 저장소라 `HF_HUB_OFFLINE=0` 필요 |
| 요청 | `model="explain"`, `temperature` 0, 상세 출력 한도 4096토큰 |
| `--max-lora-rank` | 어댑터 r=16이라 16 이상 |
| GPU·VRAM·기타 실행 옵션 | **미확인** (RunPod 엔드포인트 설정 확인 필요) |
| CPU | 실행하지 않음. AWQ는 GPU 커널 전용이라 CPU llama.cpp로 가려면 GGUF 변환과 재측정이 필요 |

## 실측 (RunPod, 2026-11-16)

RunPod 작업 기록의 `executionTime`(생성)과 `delayTime`(배정·준비 대기)을 나눠 적는다. 입력은 가상 글이다.

| 조건 | 출력 | 생성 시간 | 대기 |
|---|---|---|---|
| 워커가 떠 있음 (4회) | 문단 단위 상세 설명 | 2.9~4.2초 | 0.06~0.07초 |
| 워커 없음 (5회) | 문단 단위 상세 설명 | 3.6~6.3초 | 191~315초 |

- 항목 1회(최대 256토큰) 단위 실측은 **없다**. 위 값은 문단 단위 상세 설명이다.
- 로딩 VRAM·RAM과 서버 기동 시간은 **미측정**이다. 대기 시간에는 GPU 배정·이미지 받기·모델 적재가 섞여 있어 기동 시간으로 쓰지 않는다.
- 콜드 대기에 맞춰 서비스 타임아웃은 모델 300초, 상세 305/310초, 리포트당 최대 3건 전체 950초다.

## 평가

| 항목 | 상태 |
|---|---|
| 개발 비교(가상 글, 학부모용) | 핵심어 일치 대리지표: Gemma 직접 87.5%, Luna 직접 75% (1개 글, 2개 출력). 의미 정확도·사람 선호가 아님 |
| 상세 설명 A/B 설문 | 가상 글 4편, Luna(A)·Gemma(B) 위치 고정. 3인 평가 **미실시** |
| `checks.py` 후처리 통과율 | **미집계** |
| 사람 검토 50표본(NFR-AIQ-03) | **미실시** |
| 허용 기준 | **미정** (NFR-AIQ-06 기한 11/22) |

## 지원 범위

report-service `input_scores` 기준: 서술 초5·6, 논술 초4~6. 프리미엄·답변 공개·M2 점수가 모두 있어야 생성한다.

## 확인 필요

- [ ] 71818·71819 이유 문장 이용 조건 (#475). 학습에 논술 71819를 썼다(M2 논술 점수는 545 에세이)
- [ ] `eval_lora.py`·`vllm_check.py` 실행 결과 숫자를 Pod에서 옮겨 `results/`에 기록
- [ ] GPU 종류·VRAM, vLLM 실행 옵션, 이미지에 들어간 기반 revision
- [ ] 항목 1회(256토큰) 생성 시간, 로딩 메모리, 서버 기동 시간
- [ ] `checks.py` 통과율·사람 검토·허용 기준
