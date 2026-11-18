# 답변 표현 분류 모델 평가 결과 (#690)

- 모델: `beomi/KcELECTRA-base`(MIT, 커밋 `681201a097b8120e6dd2a2e63a3e13d338736f88`) 2분류 파인튜닝, 막을 글 = 1
- 학습·평가: 2026-11-17, RunPod RTX 4090 1장, torch 2.15.0·transformers 5.23.0, 시드 42. int8은 같은 날 저녁 scoring과 같은 길(글 하나씩·창 8개씩, 채널별 양자화)로 작업 공간 CPU·scoring 버전(torch 2.14.1)에서 다시 잼(아래 "int8 방식" 절)
- 판정 방식: api-spec 4.3.4와 같게 128토큰 창·겹침 32, 창 하나라도 확률 ≥ 임계값이면 걸림
- **서비스 기본값: 파일은 fp32 그대로 두고 scoring이 불러올 때 Linear 채널별 int8 동적 양자화(`train_info.json` `quantization: int8-dynamic-channel`), 임계값 0.95**(아래 "결정"·"int8 방식" 절). fp32로 쓸 때 임계값은 0.97
- 숫자 원본: `results/eval_tox.json`(fp32)·`eval_tox_int8.json`(채널별·서비스 조건)·`wordlist_fp32.json`·`wordlist_int8.json`·`int8_variants.json`·`kid_check.json`·`latency_*.json`. 결과 파일에는 숫자와 우리가 쓴 문장(꼭 통과할 글 상위 10개)만 있고 학습·시험 글 원문은 없다

## 데이터

| 자료 | 라이선스 | 쓰임 | 2분류 규칙 |
|---|---|---|---|
| K-MHaS(뉴스 댓글) | CC BY-SA 4.0 | 학습·검증·시험 | 라벨이 not_hate(8)만이면 정상, 다른 범주가 하나라도 있으면 막을 글 |
| Korean HateSpeech BEEP!(연예 뉴스 댓글) | CC BY-SA 4.0 | 학습·검증 | hate·offensive = 막을 글, none = 정상 |
| APEACH(크라우드 작성) | CC BY-SA 4.0 | 외부 시험만 | class 1 = 막을 글 |

| 나누기 | 글 수 | 막을 글 | 출처 |
|---|---|---|---|
| 학습 | 86,095 | 39,779 | K-MHaS train 78,199 + BEEP! train 7,896 |
| 검증 | 9,243 | 4,198 | K-MHaS valid 8,772 + BEEP! dev 471 |
| 시험 | 21,900 | 10,084 | K-MHaS test |
| APEACH | 3,770 | 1,922 | APEACH test |

- 같은 나누기 안 중복은 하나만 두고 라벨이 갈리면 뺐다(학습 426·검증 4·시험 39줄). 검증·시험에 있는 글은 학습에서 뺐다(352줄)
- KOLD(LICENSE 없음)·Korean UnSmile(상업 사용 문의 필요)은 쓰지 않았다(#205와 같은 기준). 원자료·분할은 `data/`(gitignore)에만 두고 외부 API로 보내지 않았다

## 학습

| 에폭 | 학습 손실 | 검증 F1(0.5) | 정밀도 | 재현율 | 정상 오탐 |
|---|---|---|---|---|---|
| 1 | 0.3772 | 0.8663 | 0.8999 | 0.8352 | 0.0773 |
| **2(저장)** | 0.2569 | **0.8719** | 0.8842 | 0.8599 | 0.0938 |
| 3 | 0.1891 | 0.8695 | 0.8756 | 0.8635 | 0.1021 |

- 3에폭·학습률 2e-5·배치 32·max_length 128·워밍업 10%·AdamW·AMP, 검증 F1이 가장 높은 에폭 저장. 4분 20초

## 임계값

기준안(이슈 #690·에픽 #688, 담당자 확정 2026-11-17): 꼭 통과할 글 오탐 0, 정상 문장 추가 오탐 1% 이하(단어 목록 대비).

| 항목 | 값 |
|---|---|
| 고른 임계값 | int8 **0.95**(서비스, 채널별, `train_info.json` `threshold`) · fp32 0.97 |
| 규칙(`wordlist.py`) | 꼭 통과할 글 최고 확률 초과 · 단어 목록이 통과시킨 검증 정상 글 중 모델이 더 막는 비율 ≤ 1% · 그중 모델 F1 최대(0.01 간격) |
| 꼭 통과할 글 | learning 데모 시드 241 + 웹 데모(`demoGateway.ts`) 97 + `ExpressionPolicyTest` 통과 문장 52 = 390개. 최고 확률 int8 0.867·fp32 0.797로 두 임계값 모두 0개 걸림 |
| 참고 | 단어 목록 결과 없이 "모델 정상 오탐 ≤ 1%"로 고르면(`eval.py`) int8 0.96·fp32 0.98 |

- 이슈 기준안의 "데모 문장 491"은 #205(11/02) 때 learning 데모 시드와 웹 데모 데이터를 합친 수다. 추출 스크립트가 저장소 밖이라 지금 파일에서 같은 방식으로 다시 뽑았고 그대로 재현되지는 않는다
- 미션 본문을 같이 넘겨야 허용되는 문장 2개는 모델이 미션을 보지 않으므로 조건에서 뺐다(#205 측정에서도 같은 예외): "고양이가 새끼를 다섯 마리 낳았다" fp32 0.013·int8 0.015, "틀딱이라고 부르면 할머니가 속상해요" 0.991·0.982(모델이 막음)
- 0.5였다면 꼭 통과할 글 2개(fp32, "시바견" 0.797·"일곱 난쟁이" 0.783)가 걸린다

검증셋 fp32 임계값별(학습 때 저장한 확률, 앞 128토큰, 모델만)

| 임계값 | 재현율 | 정상 오탐 | 정밀도 |
|---|---|---|---|
| 0.5 | 0.860 | 9.4% | 0.884 |
| 0.8 | 0.795 | 4.7% | 0.933 |
| 0.9 | 0.744 | 3.1% | 0.952 |
| 0.95 | 0.688 | 1.8% | 0.969 |
| 0.98 | 0.604 | 0.81% | 0.984 |

## 단어 목록과 함께 쓸 때

단어 목록(`ExpressionPolicy`, 미션 본문 없이)을 같은 글에 돌린 결과(글마다 0/1, `data/`에만)와 모델 점수를 합쳤다. "더 잡음" = 단어 목록이 놓친 막을 글 중 모델이 잡은 비율, "더 막음" = 단어 목록이 통과시킨 정상 글 중 모델이 막은 비율.

| 셋 | 단어 목록만 잡음 / 오탐 | int8 0.95 더 잡음 / 더 막음 | 합쳐서 잡음 / 오탐 | fp32 0.97 더 잡음 / 더 막음 | 합쳐서 잡음 / 오탐 |
|---|---|---|---|---|---|
| 검증 | 26.6% / 2.34% | 55.0% / 0.93% | 67.0% / 3.25% | 55.6% / 0.83% | 67.4% / 3.15% |
| 시험(K-MHaS) | 29.3% / 2.40% | **59.9% / 1.33%** | **71.7% / 3.69%** | 60.8% / 1.18% | 72.3% / 3.55% |
| APEACH | 25.9% / 1.19% | 25.9% / 0.66% | 45.1% / 1.84% | 27.4% / 0.55% | 46.2% / 1.73% |

- 이 데이터의 막을 글은 대부분 욕 없는 혐오·모욕이라 단어 목록만으로는 26~29%만 잡는다. 모델을 붙이면 시험셋에서 71.7%(int8)까지 오른다
- 추가 오탐은 검증에서 1% 이하로 골랐고 시험에서는 1.33%(int8)로 조금 넘는다. 기준은 바꾸지 않고 그대로 적는다
- 단어 목록의 정상 오탐 2.4%는 정상 라벨이 붙은 성인 댓글에도 욕이 섞여 있어서로 보인다(글을 열어 확인하지는 않음)

## 지표 (모델만)

| 셋 | 방식·임계값 | 정밀도 | 재현율 | F1 | 정상 오탐 |
|---|---|---|---|---|---|
| 검증 | int8 0.95 | 0.978 | 0.637 | 0.771 | 1.17% |
| 시험(K-MHaS) | int8 0.95 | 0.973 | **0.681** | 0.801 | **1.60%** |
| APEACH | int8 0.95 | 0.978 | 0.409 | 0.577 | 0.97% |
| 검증 | fp32 0.97 | 0.980 | 0.643 | 0.777 | 1.09% |
| 시험(K-MHaS) | fp32 0.97 | 0.977 | 0.689 | 0.808 | 1.41% |
| APEACH | fp32 0.97 | 0.981 | 0.424 | 0.592 | 0.87% |
| 시험(K-MHaS) | fp32 0.5 | 0.877 | 0.909 | 0.893 | 10.8% |
| APEACH | fp32 0.5 | 0.923 | 0.721 | 0.810 | 6.2% |

- 학습과 다른 출처인 APEACH에서는 재현율이 41~42%로 낮다
- int8(채널별)은 같은 규칙으로 고른 임계값에서 fp32보다 시험 재현율 −0.82%p(단어 목록과 합치면 −0.65%p). 오전의 층 전체 한 눈금(per-tensor) 방식은 −5.2%p였다("int8 방식" 절)

## CPU 지연

`latency.py`, 토큰화 → 128/32 창 → 창 8개씩 → 최댓값(scoring 계약 길), 1코어(`OMP_NUM_THREADS=1`), 예열 3·30회, 데모 시드 문장을 이어 붙인 글. p95(중앙)

| 글자 | 창 | fp32 포드 | fp32 PC | int8 포드 | int8 PC |
|---|---|---|---|---|---|
| 200 | 1 | 176ms (171) | 255ms (224) | 48ms (43) | 104ms (87) |
| 600 | 3 | 523ms (515) | 783ms (697) | 163ms (146) | 468ms (294) |
| 1,000 | 6 | - | 1,551ms (1,419) | - | 670ms (558) |
| 1,200 | 7 | 1,253ms (1,218) | 1,781ms (1,659) | 443ms (418) | 846ms (707) |
| 1,500 | 9 | **1,619ms** (1,567) | **2,322ms** (2,159) | 553ms (524) | 1,068ms (916) |

- 포드: RunPod CPU AMD Ryzen 9 7950X(`taskset -c 0`), Linux, torch 2.15.0. PC: 개발 PC Intel CPU(Family 6 Model 140), Windows, torch 2.15.0. 둘 다 다른 작업 없이 잼. 위 int8 숫자는 오전 per-tensor 방식
- 채널별 int8 속도(11/17 저녁, 작업 공간 x86_64 1코어, torch 2.14.1, 20회, 같은 기계에서 두 방식): 1,500자 p95 채널별 893ms(중앙 796) · per-tensor 848ms(중앙 794), 1,200자 767ms · 720ms. 차이는 잴 때마다 나는 정도라 속도는 같다고 본다(`latency_int8_channel_ws.json`·`latency_int8_tensor_ws.json`)
- 목표(이슈 #690, 200~1,200자 p95 300ms 이하): fp32·int8 모두 미달. 기준은 바꾸지 않고 결과만 적는다
- scoring 처리 마감 1.3초(learning.md 16절)에 fp32 1,500자는 두 CPU 모두 넘고(PC는 1,000자도 넘음), int8은 두 CPU 모두 안에 든다. 마감을 넘으면 scoring이 503을 주고 learning은 통과시키므로 그 글은 모델 검사가 빠진다
- 11/16에 합계 1,500자를 정할 때의 근거(1,500자 창 7개 1,115ms)는 분류 머리 학습 전 모델을 작업 공간 CPU 한 대에서 잰 값이었다. 같은 1,500자라도 글 구성에 따라 창 수가 다르다(이번 9개)

## 결정: 합계 1,500자 유지 + 불러올 때 int8 (담당자, 2026-11-17)

| 안 | 마감 1.3초(포드·PC) | 잃는 것 |
|---|---|---|
| **int8 + 1,500자(고름)** | 0.55초·1.07초로 안(per-tensor로 잼, 채널별도 같은 속도) | fp32보다 시험 재현율 −0.82%p(채널별, 합치면 −0.65%p). 오전 per-tensor는 −5.2%p |
| fp32 + 1,500자 | 1.62초·2.32초로 넘음 | 긴 글은 검사가 통째로 빠짐 |
| fp32 + 글자 제한 줄이기 | PC 기준 창 5개(약 800자)까지 | 설계 길이 변경, 초5·6 논술 뒷부분을 많이 못 봄(11/16 기록상 가운데 860자대) |
| 작은 모델(KoELECTRA-small) | 11/16 fp32 1,200자 0.2초 | 다시 학습·라이선스 확인 필요, 정확도 모름 |

- 고른 이유: 오늘 잰 숫자로 마감을 지키는 안이 int8뿐이고, 추가 오탐 기준은 그대로 둔 채 놓치는 쪽만 조금 늘어난다(채널별이면 거의 같음). 단어 목록이 앞에 있어 모델은 보조 단계다
- 되돌리는 조건: #691에서 운영 scoring Pod(CPU limit 1)로 fp32·int8을 다시 재서 fp32 1,500자 p95가 1.3초 안이면 fp32로 돌아간다(모델 파일은 같고 `train_info.json`의 `quantization`을 `none`, `threshold`를 0.97로만 바꿈). int8도 빠듯하면 작은 모델을 시험한다
- #691 로더 몫: `train_info.json`의 `quantization`이 `int8-dynamic-channel`이면 불러온 뒤 `torch.ao.quantization.quantize_dynamic(model, {Linear: per_channel_dynamic_qconfig}, qint8)`(api-spec 5.2, `scripts/quant.py`와 같음). torch 2.14·2.15에서 이 함수가 "앞으로 없어짐(torchao로 옮김)" 경고를 내므로 torch를 올릴 때 torchao로 옮기는 것을 같이 정한다

## 서비스 버전에서 다시 확인 (#691, 2026-11-17 오후, per-tensor 때)

scoring은 `uv.lock` 기준 torch 2.14.1·transformers 5.21.0이라 위 평가(torch 2.15.0·transformers 5.23.0)와 버전이 다르다. int8은 버전·CPU에 따라 확률이 조금 달라질 수 있어 같은 모델·같은 규칙으로 다시 쟀다. 숫자 원본 `results/service_check_int8.json`

| 항목 | 결과 |
|---|---|
| 데이터 | 공개 원본에서 `prepare_data.py`로 다시 만듦. 글 수·라벨 순서가 원래와 같음 |
| 검증·시험·APEACH 글별 확률(34,913개) | torch 2.15와 **완전히 같음**(가장 큰 차이 0.000000, 같은 작업 공간 CPU) |
| 단어 목록 규칙으로 고른 임계값 | **0.92 그대로** |
| 꼭 통과할 글 390개 | 최고 확률 0.8839("시바견"), 0.92에서 걸리는 글 0개 |
| 꼭 통과할 글 최고 확률 차이 | 포드(AMD) 0.8828 ↔ 작업 공간 0.8839. 같은 작업 공간에서 torch 2.15도 0.8839라 **버전이 아니라 CPU 차이**. 임계값까지 여유 0.036 |

- 결론: 서비스 버전으로 바꿔도 임계값·결과는 그대로다. 운영 CPU에서도 int8 확률이 0.001 단위로 달라질 수 있으므로, 운영 Pod 지연 측정(#691 확인 필요) 때 꼭 통과할 글 최고 확률도 같이 본다
- 이 절은 오전 per-tensor·64개 묶음 평가 기준이다. 저녁에 방식을 바꿨다(다음 절). 버전 차이가 없다는 결론은 같다(다음 절 숫자도 torch 2.14.1로 잼)

## int8 방식 다시 고름 (#690 약점 보완, 2026-11-17 저녁)

오전 결과를 다시 보다 두 가지를 찾았다. 숫자 원본 `results/int8_variants.json`·`eval_tox_int8.json`·`wordlist_int8.json`

1. **int8 확률이 같이 계산한 글에 따라 달라진다.** 동적 양자화는 입력 묶음마다 활성값 눈금을 새로 정한다. 같은 모델로 꼭 통과할 글 390개를 글 하나씩과 64개 묶음으로 계산하면 차이가 평균 0.02, 최대 0.54다("시바견" 혼자 0.565, 묶음 0.677). scoring은 글 하나씩(창 8개씩) 계산하는데 오전 평가는 64개 묶음이었다. 그래서 오전 임계값 0.92는 서비스와 다른 조건에서 고른 값이었다(서비스 조건으로 다시 고르면 0.93). fp32는 묶음과 상관없다(차이 최대 3e-6)
2. **층 전체 한 눈금(per-tensor)보다 출력 채널마다 눈금(per-channel)이 fp32에 훨씬 가깝다.**

검증셋, 단어 목록 규칙으로 임계값(scoring 버전 torch 2.14.1, 작업 공간 CPU)

| 방식 | 계산 | fp32와 확률 차이(평균) | 꼭 통과 최고 | 임계값 | 재현율 | F1 | 단어 목록과 합쳐 잡음 |
|---|---|---|---|---|---|---|---|
| fp32 | 묶음 | 0 | 0.797 | 0.97 | 0.643 | 0.777 | 67.4% |
| per-tensor(오전) | 64개 묶음 | 0.088 | 0.857 | 0.92 | 0.586 | 0.732 | 63.1% |
| per-tensor | 서비스 조건 | 0.075 | 0.728 | 0.93 | 0.604 | 0.746 | 64.6% |
| **per-channel(채택)** | **서비스 조건** | **0.048** | 0.867 | **0.95** | **0.637** | **0.771** | **67.0%** |

- 분류 머리(classifier)만 fp32로 두는 안도 64개 묶음으로 쟀는데 per-channel과 같았다(임계값·F1 같음) → 더 단순한 per-channel 전체로 함
- 채택: per-channel·서비스 조건으로 `eval.py --int8`(이제 기본이 글 하나씩) → `wordlist.py --write` → 임계값 0.95, `quantization: int8-dynamic-channel`. 시험·APEACH 숫자는 위 표들(오전 0.92 값을 바꿈)
- 시험(K-MHaS) 재현율: fp32 0.689 · per-channel 0.681 · 오전 per-tensor 0.638. 단어 목록과 합쳐 잡음 72.3% · 71.7% · 68.9%

## 아이 말투 문장 70개 (2026-11-17 저녁)

꼭 통과할 글 390개는 앱 문장이라 아이 말투를 따로 봤다. 문장은 우리가 지은 것(실제 학생 글 아님), 모델만(단어 목록 안 거침), 서비스 조건. 원본 `results/kid_check.json`

| 묶음 | 기대 | 개수 | int8 채널별 0.95 걸림 | fp32 0.97 | 오전 per-tensor 0.92 |
|---|---|---|---|---|---|
| 자기 감정("화가 났다", "배고파서 죽을 것 같았다") | 통과 | 15 | 0 | 0 | 0 |
| 교과·미션 내용(전쟁·차별·포식) | 통과 | 15 | 0 | 0 | 0 |
| 학교생활 | 통과 | 10 | 0 | 0 | 0 |
| 놀림말(바보·멍청이·찐따) | 정책 미정 | 10 | 1 | 1 | 0 |
| 유행어(개맛있다·킹받네·존잼) | 정책 미정 | 10 | 0 | 0 | 0 |
| 욕 없는 모욕·혐오 | 막아야 함 | 10 | 4 | 3 | 3 |

- 정상 아이 문장 40개는 하나도 안 막는다(채널별 최고 0.10)
- 상대에게 직접 하는 모욕은 잘 못 잡는다: "너 같은 건 없어지면 좋겠어" 0.10, "너는 살 가치가 없어" 0.42. 잡는 것은 집단 혐오("늙은이들은…", "장애인은…")와 "쓰레기 같은 인간" 같은 말
- 놀림말·유행어를 막을지는 정책(팀장 결정)이 먼저다

## 한계

- 학습 데이터가 성인 뉴스·연예 댓글이라 초등 답과 말투가 다르다. 꼭 통과할 글 390개는 우리 앱 문장이지만 실제 학생 답은 아니다
- 미션 본문에 나온 말을 허용하는 규칙(`HATE`·맥락 단어)이 모델에는 없다. 차별을 다루는 미션에서는 모델이 막을 수 있다("틀딱" 문장 0.98 이상)
- 다른 출처(APEACH)에서 재현율이 39~42%로 떨어진다. 시험셋 숫자는 학습과 같은 출처라 실제보다 좋게 나왔을 수 있다
- 시드 1개 학습 결과다
- 아이가 상대에게 직접 하는 모욕(욕 없는 말)은 10개 중 4개만 잡는다("아이 말투" 절). 실제 학생 답 라벨이 쌓이는 재학습(#725)·경계 구간(#726)이 해결 경로다
- 합계 1,500자 뒤의 글과 21번째 칸부터는 모델이 보지 않는다(설계 기준)

## 재현

```bash
cd ml/tox
uv sync --frozen
# 1) 데이터 정리 (K-MHaS data 폴더, BEEP! labeled 폴더, APEACH apeach.test.csv)
uv run python -I scripts/prepare_data.py --kmhas <K-MHaS/data> --beep <korean-hate-speech/labeled> --apeach <apeach.test.csv> --out data/processed
# 2) 학습 (GPU)
uv run python scripts/train.py --out checkpoints/kcelectra-base-s42 --revision 681201a097b8120e6dd2a2e63a3e13d338736f88
# 3) 모델만 평가 + 글별 점수 저장
uv run python scripts/eval.py --model checkpoints/kcelectra-base-s42 --save-probs data/probs_fp32.npz
uv run python scripts/eval.py --model checkpoints/kcelectra-base-s42 --int8 --save-probs data/probs_int8.npz
# 4) 단어 목록 결과(아래 임시 시험, 커밋하지 않음) → 임계값을 train_info.json에 씀
uv run python scripts/wordlist.py --probs data/probs_int8.npz --flags data/wordlist_flags.json --eval-json results/eval_tox_int8.json --model checkpoints/kcelectra-base-s42 --write
# 5) 지연 (CPU 1코어)
OMP_NUM_THREADS=1 uv run python scripts/latency.py --model checkpoints/kcelectra-base-s42 [--int8]
```

단어 목록 결과는 learning-service 시험 폴더에 아래 파일을 잠깐 두고 돌려서 뽑았다(커밋하지 않음, 글 원문은 쓰지 않고 0/1만).

```kotlin
// backend/learning-service/src/test/kotlin/com/sagomungchi/learning/answer/domain/TmpWordListDumpTest.kt
package com.sagomungchi.learning.answer.domain

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.sagomungchi.learning.answer.repository.ExpressionPolicyConfig
import com.sagomungchi.learning.mission.missionView
import java.io.File
import org.junit.jupiter.api.Test

class TmpWordListDumpTest {
    @Test
    fun dump() {
        val dir = System.getenv("TOX_DATA") ?: return
        val mapper = jacksonObjectMapper()
        val policy = ExpressionPolicyConfig.load(mapper)
        val plain = missionView(grade = 3)
        val out = linkedMapOf<String, List<Int>>()
        for (name in listOf("valid", "test", "apeach")) {
            out[name] = File(dir, "$name.jsonl").readLines().filter { it.isNotBlank() }.map { line ->
                val text = mapper.readTree(line)["text"].asText()
                if (policy.blockedCategory(listOf(text), plain) != null) 1 else 0
            }
        }
        File(System.getenv("TOX_OUT")).writeText(mapper.writeValueAsString(out))
    }
}
```

```bash
cd backend/learning-service
TOX_DATA=../../ml/tox/data/processed TOX_OUT=../../ml/tox/data/wordlist_flags.json \
  ./gradlew test --tests '*TmpWordListDumpTest' --tests '*ExpressionPolicyTest'
```
