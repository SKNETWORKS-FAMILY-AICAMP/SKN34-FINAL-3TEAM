# 기존 LoRA Gemma 리포트 설명 검증 (#475, 2026-11-16~17)

리포트 대표 답변 상세 설명에 기존 LoRA Gemma를 쓸지 판단하려고 한 개발용 비교다. 사람 평가 전 탐색 실험이라 품질 우위 결론은 아니다. 생성 위치는 이후 SageMaker 실시간 엔드포인트로 바뀌었다([AI 보고서 24절](ai.md#24-리포트-gemma-sagemaker-호출-전환-747-2026-11-18)).

## 1. 범위

- 당시 RunPod 서버리스의 LoRA Gemma 4를 그대로 썼다. 추가 학습·모델 교체·배포 설정 변경 없음. 체크포인트·어댑터 해시는 따로 검증하지 않았다
- 가상 글 4개(설문용 Google Form 공개 페이지에서 읽음)로 학생·학부모, 요약·상세를 비교했다. 내용 보존과 블라인드 사람 평가 우위를 함께 만족해야 낫다고 보며, 낱말 일치만으로는 판단하지 않는다
- 점수 정의(내용 1/2/3 등)가 없어 루브릭을 지어내지 않았다. 4개 사례는 개발 파일럿이고 개념·별칭 목록은 승인 전 초안이라 모델에 넣지 않았다
- 원문·모델 출력·작업 영수증·자격 증명·블라인드 대응표는 저장소에 넣지 않았다(git 무시 `local_data/explanation_eval/`)

## 2. 도구와 기록

- `evaluation/runners/explanation_eval.py`: 호출 상한, 프롬프트·자료 지문, 이어 하기 가능한 RunPod 영수증, 정확 인용 검사, 직접/교정/두 단계 비교, 3인 블라인드 내보내기와 A/B/TIE 다수결. 오프라인 단위 시험 8개 통과
- `explanation_writer_probe.py`(같은 근거·같은 지침 비교), `explanation_layered_view_probe.py`(기본 설명), `explanation_form_pack.py`(설문용 Apps Script·미리보기), `structured_report_demo.py`(시연 리포트 3회)
- 실행 절차: [evaluation/datasets/explanation/README.md](../../evaluation/datasets/explanation/README.md). 숫자 기록: `evaluation/results/explanation/pilot-20261116.json`·`fixed-detail-survey-20261116.json`·`structured-report-demo-20261116.json`

## 3. 결과

예비 비교(한 사례의 학부모용 요약·상세 2개, 승인 전 GT 초안의 문자열 일치 대리지표):

| 방식 | 생성 성공 | 핵심어 일치 대리지표 평균 | 분량 조건 |
|---|---|---|---|
| Luna 직접 설명 | 2/2 | 75% | 2/2 |
| Gemma 직접 설명 | 2/2 | 87.5% | 2/2 |
| Gemma→Luna 교정 | 2/2 | 100% | 2/2 |
| Gemma 근거 추출→Gemma 설명 | 2/2 | 75% | 2/2 |

- 두 단계 Gemma는 핵심어 보존을 개선하지 않았고 구체적인 내용을 일반화했으며 해요체 대신 합니다체가 나왔다. 추출 인용 4개는 모두 원문에 있었다(관찰의 타당성은 사람 검토 몫)
- 같은 근거·보완 지침을 주면 Gemma(147자)·Luna(156자) 모두 핵심어 4/4·해요체로 좋아져 Gemma만의 우위는 입증하지 못했다
- 사용자 피드백: 기본 화면은 Luna 391자 형태, 상세 보기는 Gemma 763자 형태를 선호. 다음 비교는 기본 350~450자·상세 700~900자로 맞춰 같은 깊이끼리 보자는 제안으로 정리
- 상세 고정 위치 설문(A Luna 직접, B LoRA Gemma 직접, 4쌍): 최종 문항은 글마다 A/B 양자택일 4개. Apps Script는 새 비공개 초안만 만들며 실제 계정 생성·배포·응답 집계는 이 문서 범위 밖
- 추론은 승인 한도(12 + 6 + 3) 안에서 누적 21회. RunPod 대기는 191~285초, 실제 생성은 3.6~5.3초였다(콜드 대기가 이후 SageMaker 전환의 근거 중 하나, [infra 9.13](infra.md#913-리포트-gemma-cpugpu-서빙-비교와-s3-반입-743745-2026-11-18))
- 상세 설명 구역화(상세 분석·보완할 지점·개선 방안, 보완점이 원문에 없으면 null) 규칙은 [structured-detail-prompt.md](../../evaluation/datasets/explanation/structured-detail-prompt.md)로 정리했고 이후 서비스 프롬프트에 채택했다

## 4. 시연 리포트와 화면

- 가상 글 3편을 실제 LoRA Gemma에 한 번씩 보내 개발 앱 `reportDemo=structured` 시연(가상 초5, 2026-11-09~15 주간 리포트)에 연결했다. 결과 누락·원문 변경 때 합성 설명으로 대신하지 않는다
- 리포트 목록을 주간·일일로 나누고 상세를 메인 영역에서 여는 화면, 설명 위 `학생 글 전체` 표시는 [frontend 41절](frontend.md#41-리포트-원문-전체구역별-설명-475-2026-11-17)
- PR 검증(2026-11-17): 웹 단위 349·리포트 서비스 100·AI/평가/계약/E2E 격리 166·학부모 브라우저 26 통과. 추가 학습·사람 50표본 평가는 하지 않았다

## 2026-11-17: 향후 리포트 모델 고정

- 사용자 결정: 주간 서술·저녁 질문·대표 답변 상세 설명은 같은 LoRA Gemma 하나만 쓰고, 일반 LLM 설정이나 OpenAI 키가 있어도 리포트에 쓰지 않는다. 주소·설정 누락이나 장애는 실패로 처리하고 다른 모델로 대체하지 않는다(#733). 수치 리포트와 결정적 검증 실패 때의 템플릿 정책은 그대로
- 당시에는 RunPod 엔드포인트(#751 키 `SAGOMUNGCHI_SLLM_SERVERLESS_GEMMA`·`..._KEY_GEMMA`)였고, #747(2026-11-18)부터 같은 LoRA를 SageMaker 실시간 엔드포인트로 부르며 RunPod 키와 콜드 대기용 시간 값(300·310·950초)은 지웠다. 지금 설정은 `REPORT_LLM_ENDPOINT`·`REPORT_LLM_COMPONENT`·`REPORT_LLM_REGION`(values, 비밀값 아님)과 report 대기 80·80·300초다([AI 보고서 24절](ai.md#24-리포트-gemma-sagemaker-호출-전환-747-2026-11-18))
