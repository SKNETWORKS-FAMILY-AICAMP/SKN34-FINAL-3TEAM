# Existing LoRA Gemma explanation validation — 2026-11-16

## Scope fixed with the user

- Use the current Gemma 4 LoRA model on RunPod Serverless. No additional training, model replacement
  or deployment-setting change. The user confirmed the existing `.env` Gemma endpoint is the LoRA
  endpoint. The checkpoint/adapter hash has not been independently verified.
- Compare source-grounded explanations for student/parent and summary/detail. A better result must
  preserve content AND receive better blinded human ratings; lexical coverage alone is not victory.
- The supplied Google Form is labelled four synthetic texts. Its public page was read anonymously
  after connected Drive/browser tools failed; no form was edited or submitted. Four input cases and
  16 archived outputs are stored locally under ignored `local_data/explanation_eval/`.
- The form has accuracy, text evidence, audience fit and naturalness, each 1–5. Its model labels are
  shuffled per case/audience. Their identities were subsequently recovered by exact body matches
  against archived generation files: 16/16. A different v3 identity CSV matched only 3/16 and was
  rejected. Respondent evaluations are still unavailable; the old ranking cannot be recalculated.

## Initial findings and experiment boundaries

- The smartphone text explicitly acknowledges studying with a phone and gives difficulty with
  self-control as a reason for agreeing limits with parents. An archived explanation says the reason
  for limiting even in that case was not continued. This is a concrete **human-review target** for
  missing-vs-insufficient reasoning, not an automatically adjudicated model error.
- Scores are present, but definitions of content 1/2/3 and the other numbered criteria are not.
  Do not invent a rubric or justify every low score by inventing an absent feature.
- Four inspected cases are a development pilot, not a held-out final evaluation. Concept/alias lists
  are drafts, not approved semantic GT. Do not pass them to the model. Human agreement on required
  concepts, forbidden claims and length limits precedes a final study.

## Artifacts and checks

- `evaluation/runners/explanation_eval.py`: bounded live calls, prompt/dataset fingerprints,
  resumable RunPod receipts, exact-quote validation, direct/edit/two-stage arms, lexical proxy
  summaries, three-rater blind exports and A/B/TIE majority aggregation.
- `evaluation/datasets/explanation/README.md`: protocol, comparison limitations, execution and review.
- Offline unit tests: 8 passed. Includes GT exclusion at every generation stage, fabricated quote
  rejection, no repost after ambiguous submission, failure accounting, blind exports and no-majority
  handling and a paid-call cap that also counts receipts from prior processes. Python compilation
  passed. Ruff is not installed in the current Python environment;
  no Ruff success is claimed.
- Raw source, model output, job receipts, credentials and blind identity keys are not committed.
  There are no human ratings or quality wins fabricated by the tool.

## Live execution status

The user explicitly approved sending the four synthetic cases' answer, grade, topic and scores to
the configured RunPod LoRA endpoint and OpenAI gpt-6-luna, with the **first run limited to one case
and at most 12 paid calls**. Respondent identities and survey evaluations are excluded.

The first run completed in ignored `local_data/explanation_eval/pilot-approved-20261116/`:
one case × parent summary/detail × four arms (API direct, Gemma direct, reconstructed Gemma→Luna,
two-stage Gemma). Nine distinct inference calls produced eight explanations. Drafts/evidence were
shared rather than generated again. All eight outputs passed JSON/text and predefined length checks.
The initial prompt protocol was frozen before observing those outputs.

## 예비 결과 (정성평가 전)

아래 수치는 승인 전 GT 초안의 **문자열 일치 대리지표**다. 의미 정확도·사람 선호도·통계적
우위가 아니며, 한 사례의 학부모용 출력 두 개만 대상으로 한다.

| 최초 비교 방식 | 요약/상세 생성 성공 | 핵심어 일치 대리지표 평균 | 분량 조건 통과 |
|---|---|---|---|
| Luna 직접 설명 | 2/2 | 75% | 2/2 |
| Gemma 직접 설명 | 2/2 | 87.5% | 2/2 |
| Gemma→Luna 교정 (통제된 재구성) | 2/2 | 100% | 2/2 |
| Gemma 근거 추출→Gemma 설명 | 2/2 | 75% | 2/2 |

- 두 단계 Gemma가 최초 실험에서 핵심어 보존을 일관되게 개선하지는 않았다. 요약에서 숙제·신문
  같은 구체적인 내용을 일반화했고, 요청한 해요체 대신 합니다체가 나왔다. 문장 종결형 점검은
  결과를 본 뒤 수행한 탐색적 진단이며 사전 등록된 성능 지표로 제시하지 않는다.
- 추출된 원문 인용 4개는 모두 원문에 정확히 존재했다. 이 검사는 인용의 존재만 확인하며,
  그 인용에 붙인 관찰의 타당성은 별도 사람 검토가 필요하다.

## 별도 개발 실험: 동일 근거·동일 보완 지침

최초 결과를 본 뒤, 구체적인 대상·활동을 추상화하지 말 것과 해요체 준수를 명확히 한 쓰기
지침을 고정했다. 기존에 수집한 같은 근거와 같은 지침을 Gemma·Luna에 각각 제공했다.
`explanation_writer_probe.py`가 2회 추가 호출했으며, 최초 결과를 교체하거나 최선의 출력만
고른 것이 아니다. 이 단계는 **개발용 탐색**이며 독립된 최종 평가가 아니다.

- Gemma: 147자, 핵심어 문자열 4/4, 해요체 출력.
- Luna: 156자, 핵심어 문자열 4/4, 해요체 출력.
- 보완 지침으로 Gemma의 관찰된 문제가 개선됐지만 Luna도 개선됐다. Gemma만의 우위는 입증하지
  못했다. 정확성·유용성·자연스러움의 판단은 3인 블라인드 평가 전까지 보류한다.

## 호출·산출물·다음 단계

- 총 추론 요청 **11회**(Gemma 6, Luna 5), 모두 완료. 승인 한도 12회를 넘기지 않았다.
- 최초 Gemma 요청의 대기/실행은 각각 222,293ms/5,286ms, 근거 추출 요청은
  191,350ms/3,648ms였다. 배정·준비 대기와 실제 생성 시간을 분리해 기록한다. 준비 지연의
  모든 원인이 콜드 스타트라고 단정하지 않으며 배포 설정은 변경하지 않았다.
- 숫자만 담은 집계는 `evaluation/results/explanation/pilot-20261116.json`에 기록했다.
- 로컬 `review-index.html`에서 최초 비교 6쌍과 별도 쓰기 비교 1쌍을 읽을 수 있다. 각 비교에는
  평가자 3인용 1–5점 평가표와 A/B/TIE 선호표가 있다. 모델 대응표는 평가자에게 공유하지 않는다.
- 사람 평가 칸은 모두 비워 두었다. 3명이 실제로 독립 평가한 뒤에만 다수결을 집계한다.
  A/B/TIE가 한 표씩이면 NO_MAJORITY로 유지한다. 의미 GT 검토와 학생용·새 사례 검증도 남아 있다.
- 추가 학습·실서비스 적용·배포 변경·푸시·PR은 하지 않았다.

## 사용자 피드백에 따른 출력 단계 구분

- 사용자는 최초 비교의 5번을 제외한 A를 선호한다고 말한 뒤, 기본 화면에는 4번 A, 상세
  보기에는 5번 A와 같은 출력을 원한다고 구체화했다. 5번 A를 모든 용도에서 낮게 평가한
  것으로 해석하지 않는다. 비공식 사용자 피드백은 3인 평가 CSV와 별도로 보관한다.
- 4번 A는 Luna의 391자 설명, 5번 A는 Gemma의 763자 설명이다. 최초 상세 조건이
  300~1100자로 넓어 출력 깊이가 혼재했다. 모델 선호와 분량·용도 선호를 분리해야 한다.
- 다음 비교에서는 기본 약 350~450자, 상세 약 700~900자로 맞춘 뒤 같은 대상·같은 깊이의
  출력을 비교한다. 상세에는 같은 근거의 해설·지도 방법을 확장하고 새로운 관찰을 발명하지 않는다.
- 승인 한도의 마지막 요청은 `explanation_layered_view_probe.py`에서 같은 첫 가상 글로
  Gemma의 320~480자 기본 설명을 생성하는 용도다. Luna 예시 원문이나 숨긴 GT를 입력하지
  않으며, 기존 Gemma 장문은 수정하지 않는다. 이것은 단계별 출력 가능성 예시이지 우위 평가가 아니다.
- 12번째 요청은 결과 폴링 중 HTTP 500으로 클라이언트가 실패 처리했으나, 기존 작업을 GET으로
  다시 조회해 COMPLETED 결과를 회수했다. 새 추론을 재접수하지 않았다. 대기 284,860ms,
  실행 4,684ms였다. 반환한 기본 설명은 247자로 목표 320~480자에 미달했다.
- 실제 Gemma 기본 247자와 기존 상세 763자를 편집 없이 연결한 로컬 `layered-preview.html`을
  만들었다. 기본·상세 구성의 가능성 예시이며 4번 A와 동일한 품질·분량을 입증한 것은 아니다.
- 현재 누적 추론 요청은 12회(Gemma 7·Luna 5)로 한도를 소진했다. 본문 두 개를 함께 생성해
  저장하는 방식은 향후 서비스 적용안이며, 이번 작업에서 서비스 API·화면은 변경하지 않았다.
- HTTP 오류 뒤 남은 작업 취소 시도는 자동 승인 검토가 외부 작업 변경으로 거절했다. 취소는
  실행하지 않았고 이후 읽기 전용 조회에서 완료를 확인해 추가 정리가 필요하지 않았다.

## 상세 설명 고정 위치 설문

- 사용자는 기본 설명보다 상세 설명에서 Gemma가 유용할 수 있다는 가설을 검증하기 위해,
  상세 출력의 A/B 위치를 고정하도록 요청했다. A는 Luna 직접 생성, B는 LoRA Gemma 직접
  생성이다. 평가자용 설문에는 모델명을 넣지 않는다. 기존 무작위 비교의 A/B와 혼동하지 않는다.
- 첫 글의 기존 상세 출력 두 개를 그대로 사용하고, 나머지 가상 글 3개는 사용자에게 별도
  승인받은 최대 6회 추론으로 추가한다. 최초 12회 승인과 추가 6회 승인은 별개다.
- 기존 상세 조건과 동일한 입력 허용 목록·시스템 지시·분량 범위(300~1100자)를 사용한다.
  출력은 교정하거나 좋은 결과만 골라 재생성하지 않는다. 실제 길이가 다르므로 분량을 통제한
  모델 능력 실험으로 해석하지 않는다. 이미 검토한 개발 사례이며 위치 편향도 남는다.
- `explanation_form_pack.py`는 완료된 직접 생성 쌍만 읽어 Google Forms용 Apps Script와
  Markdown 미리보기를 만든다. 이전 Gemma→Luna 교정 결과를 Gemma 단독으로 섞지 않는다.
  숨긴 GT·모델 대응표·키·엔드포인트 주소는 설문에 포함하지 않는다.
- 평가 항목은 원문 정확성, 근거 구체성, 한국어 자연스러움, 글 구조, 학부모 적합성의 각 1~5점과
  종합 선호(A/B/동등/둘 다 부적합), 필수 선택 이유, 선택적 오류 인용이다. 점수 산정의 정확성과
  GT 핵심어 검증은 별도다. 3인 독립 평가 후 같은 A 또는 B가 2표 이상인 경우에만 다수 선호로
  기록한다. 동등·둘 다 부적합·다수결 불성립을 승리로 계산하지 않는다.
- 연결 도구에 Forms 생성 기능이 없어 실제 Google 계정에서 생성한 폼은 아직 없다. 제공하는
  Apps Script는 실행 시 새 비공개 초안을 만들고 기존 폼을 수정하거나 자동 게시하지 않는다.
  문법·고정 순서·출력 보존·중복 생성 방지는 로컬 모의 실행으로 확인하며 실제 Forms 실행과 구분한다.
- 추가 추론 전 상태 조회의 일시적 HTTP 429/5xx·전송 오류는 동일 작업의 GET만 재시도하도록
  보완했다. 추론 POST를 재전송하지 않으며 대기 제한 도달 시 자동 취소하지 않는다. 이 동작은
  모의 HTTP 500→완료 테스트로 확인했다.
- 추가 6회(Gemma 3·Luna 3)는 모두 완료했다. 첫 글 기존 출력과 합쳐 비교 쌍은 4개다.
  A/B의 글별 문자 수는 391/763, 504/735, 352/541, 527/645다. 전체 누적 요청은 18회이며
  최초 12회와 별도 승인 6회의 합이다. 숫자 기록은
  `evaluation/results/explanation/fixed-detail-survey-20261116.json`에 보관했다.
- 최종 설문 팩은 무시되는 로컬 `local_data/explanation_eval/fixed-detail-survey/`에 있다.
  총 8개 출력의 직접 생성 결과와 바이트 수준의 텍스트 일치를 확인했다. Google Forms용
  스크립트의 초안 생성·8개 평가 그리드·순서 고정·재실행 시 중복 생성 방지는 로컬 모의 실행으로
  확인했다. 실제 Google 계정에서 실행·게시하거나 팀원에게 배포하지 않았다.
- 이후 사용자 요청으로 최종 설문을 선호 선택만 남기도록 수정했다. 평가자 코드·점수 그리드·
  선택 이유·오류 인용 질문은 모두 제거했다. 최종 응답 문항은 글마다 A/B/동등/둘 다 부적합 중
  하나를 선택하는 총 4개다. 출력과 A/B 위치는 유지했다. 설문 버전을 변경해 기존 다항목 폼을
  생성했던 프로젝트에서도 새 선호 전용 초안을 만들도록 했다. 모의 실행으로 4개 선택 문항만
  생성되고 점수·서술형 문항이 없는 것을 확인했다. 응답자 구분은 수집하지 않으므로 팀원 3명의
  독립적인 1회 응답 여부는 별도로 확인해야 한다.

- 최종 사용자 수정: 각 글의 응답을 A/B 양자택일로 제한했다. 동등·둘 다 부적합 선택지를 제거하고 설문 버전을 변경했다. 총 4개 필수 선택 문항이며 출력과 모델 위치는 유지했다.

## 상세 설명의 문체와 구역화 제안

- 사용자 요청에 따라 다음 비교를 위한 공통 출력 규칙을
  `evaluation/datasets/explanation/structured-detail-prompt.md`에 정리했다. 인사·호칭·분석을
  시작한다는 서문을 빼고 상세 분석/보완할 지점/개선 방안으로 나눈다. 보완점이 원문에서
  확인되지 않으면 null로 두고 화면에서 생략하는 안이다. 아이가 실제로 어려움을 느꼈다고
  단정하지 않도록 제목을 보완할 지점으로 제안했다.
- 현재 서비스는 `report_explanation`에서 평가 항목별 짧은 이유를 생성하고 규칙으로 합성한다.
  이번 실험의 전체 글 장문 상세와 다른 경로이므로 해당 서비스를 장문 생성으로 임의 교체하지
  않았다. 새 규칙은 제안 문서이며 실행 가능한 서비스 반영이나 출력 품질 검증 결과가 아니다.
- 기존 네 비교 쌍·양자택일 설문·생성 기록은 변경하지 않았다. 추가 모델 호출도 하지 않았다.

## 실제 Gemma 시연 리포트 및 목록·상세 화면

- 이후 사용자가 실제 Gemma 연결을 요청해 로컬 가상 글 세 편을 RunPod LoRA Gemma에 각 한 번씩
  보냈다. 세 요청 모두 완료했다. 기존 설문 평가와 별도이며 누적 추론은 21회(기존 18회 + 이번 3회)다.
- 입력은 가상 글의 학년·문항·원문뿐이며 학생 이름·식별자·숨긴 GT·합성 설명을 보내지 않았다.
  해당 UI 자료에는 실제 M2 점수가 없어, 이 결과를 점수 해설의 정확성 평가로 사용하지 않는다.
- `structured_report_demo.py`는 3회 한도, 요청별 영수증, 동일 원문·프롬프트 기록을 남긴다.
  실제 결과와 브라우저용 저장 파일의 세 JSON 본문이 일치함을 확인했다. 인증정보나 엔드포인트는
  브라우저 파일에 넣지 않는다. 반환된 문장은 교정하지 않았다. 인사말은 없지만 합니다체가
  남았으며 내용 품질·GT 검증은 미완료다. 숫자 기록은
  `evaluation/results/explanation/structured-report-demo-20261116.json`에 있다.
- 개발 앱의 명시적 `reportDemo=structured` 시연에서만 가상 초5 자녀, 글 세 편·답변 네 개,
  2026-11-09~15 주간 리포트를 만든다. 지표는 학습 기록에서 계산한다. 상세 설명은 실제 생성
  결과를 원문·답변 버전과 대조해 연결하고, 짧은 요약은 화면 확인용 문구임을 명시했다.
  결과 누락·원문 변경에는 합성 설명으로 대체하지 않는다. 재집계 시에도 같은 원문의 결과를 쓴다.
- 전체 목록을 주간·일일 구역과 그리드로 나누고 제목을 테마 색 #277044로 표시했다.
  `리포트 보기` 버튼을 누르면 목록이 사라지고 상세가 메인 영역을 차지한다. 왼쪽 위 화살표는
  같은 필터의 목록으로 복귀한다. URL의 reportId와 현재 자녀의 목록을 대조하므로 브라우저의
  뒤로·앞으로 가기도 동작하며 다른 자녀의 상세를 섞지 않는다.
- 빌드·타입·린트, 관련 단위 테스트 6개, 학부모 브라우저 회귀 23개를 통과했다. 실제 개발 서버에서
  세 Gemma 결과가 수정 없이 표시되고 목록/상세 왕복·새로고침·세 화면 폭이 동작함도 별도로
  확인했다. 실제 모델을 페이지 새로고침 때 추가 호출하지 않는다. 운영 백엔드 배포는 하지 않았다.

## 2026-11-17: 향후 리포트 모델 고정

사용자 결정에 따라 주간 서술·저녁 질문·대표 답변 상세 설명은 같은 LoRA Gemma RunPod 엔드포인트를 사용한다. 일반 LLM 설정이나 OpenAI 키가 있어도 리포트에 사용하지 않는다. Gemma 주소·키 누락이나 장애는 실패로 처리하며 타 모델로 대체하지 않는다. 수치 리포트·기존 결정적 검증 실패 템플릿 정책은 유지한다. 271~276초 실측을 반영해 모델 300초, 내부 서술 310초, 상세 305/310초와 최대 3건 전체 950초를 적용한다. 상세 출력 한도는 4096토큰이다. `SAGOMUNGCHI_SLLM_SERVERLESS_GEMMA`와 해당 키를 compose 환경에 공급한다.

## 원문 전체 표시

발췌문만 보여 전체 글 분석을 환각처럼 오해하는 문제를 수정했다. 설명 항목의 itemId로 기존 근거 API를 호출해 시도·답변·버전이 모두 일치하는 원문을 `학생 글 전체`에 표시한다. 조회 실패·비공개·다른 버전에는 발췌문으로 대체하지 않는다. 이 PR은 #475의 기존 튜닝 모델 활용·비교·화면 적용 범위이며 추가 학습·사람 50표본 평가 완료나 원 이슈의 모든 완료 조건 달성을 주장하지 않는다.
