# 이슈 #51 학습 기록 조회·수치 계산 검토

## 기준과 구현 상태

[#51](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/51)의 learning 조회·P08 계산·항목 및 근거 저장을 구현했다. 기준 develop은 `ecd6ecf`, 직접적인 구현 기반은 #50의 로컬 커밋 `666decc`다. 작업 브랜치는 `feature/report-metrics`이며 #50 브랜치와 구분한다.

2026-10-27 기준 #27은 열려 있고 실제 learning API 연동 완료는 확인되지 않았다. **이 문서의 검증 결과는 명시한 입력 구현안과 합성 고정 응답, 실제 report DB에 대한 결과다. #27·#42와의 실제 연동 완료를 뜻하지 않는다.**

| 구분 | 근거·결정 |
|---|---|
| 기간·포함/제외 | 기능 명세 P06·P08, FN-RPT-02~06 |
| 표본 상태 | API 1.5: 0건 `NO_RECORD`, 1~4건 `INSUFFICIENT_SAMPLE`, 5건 이상 `OK` |
| Metric | API 1.6: count·numerator·denominator·formula·period·sourceType·state |
| 까닭을 잇는 말 | #51 담당 사용자가 2026-10-27 이 대화에서 `왜냐하면·때문·그래서·따라서` 4개 사용을 확인. P08과 코드 상수에 반영 |
| learning 상세 입력 | API 4.1.1에 구현안으로 명시. #27 실제 응답과의 대조는 남아 있음 |
| 저장 | 기존 ERD 5장 `weekly_report`·`report_item`·`report_item_evidence`·Outbox 사용 |

새 마이그레이션·의존성·테이블 생성은 없다. 기존 Alembic 스키마에 대한 SQLAlchemy Core 조회 정의를 보강했다. `target_metadata = None`과 명시적 마이그레이션 방식을 유지한다.

## 코드와 설계 문서 대조

| 실제 위치 (`backend/report-service/`) | 역할 |
|---|---|
| `app/clients/learning_client.py` | 세 내부 조회, 전체 페이지 수집, 필수 입력·학생·기간 검사, 정규화 |
| `app/clients/base.py` | 기존 내부 토큰·사용자 범위·trace 헤더 재사용. 고정 응답 시험용 transport 주입 지원 |
| `app/generation/records.py` | 프레임워크와 독립적인 학습 기록·기간 모델. 메모/초안 필드 없음 |
| `app/generation/metrics.py` | P08 계산, 5유형·변화·돌아보기·인용 후보·근거 연결 |
| `app/generation/record_generator.py` | #50 생성 단계에 학습 조회·계산을 연결하는 `RecordGenerator` |
| `app/generation/models.py` | `GenerationResult.items`, `ReportItem`·`EvidenceLink` |
| `app/generation/repository.py` | 종료 상태와 같은 Session에서 item·evidence 저장 |

클래스 다이어그램의 report 절도 실제 `GenerationConsumer`, `RecordGenerator`, `MetricsCalculator.calculate`, `ReportRepository.finish`, `OutboxRepository.add`와 맞췄다. AI·렌더링·조회·삭제 등 #52~#55의 계획과 현재 #50/#51 구현을 구분해 설명했다. 기존 설계의 `OutboxWriter` 별도 클래스 대신 현재 서비스가 `OutboxRepository.add`를 호출하는 흐름을 표시했다.

## 계산 규칙

- 기간은 KST 날짜 양 끝을 포함한다. 시각 비교는 시작일 00:00 이상·종료일 다음 날 00:00 미만이다. UTC 응답도 KST 경계로 검사한다.
- 기간 내 제출 답변이 하나 이상 있는 시도를 포함하며 미완료 시도도 포함한다. 종료일까지의 답변이 모두 `FAILED`인 시도, 제출이 없는 시도, 삭제 표식은 제외한다. `PENDING/RUNNING`을 처리 실패로 바꾸지 않는다.
- 기간을 걸친 시도는 각 주의 답변 제출 존재 여부로 포함한다. 비교는 시도 최초 답변과 해당 주 종료일 이전 마지막 답변이다. 이 구체적인 입력 요구는 API 4.1.1의 #27 확인 대상에 포함했다. 미래 답변·돌아보기를 과거 주의 결과에 넣지 않는다.
- 도움 없이 시작한 비율은 최초 답변보다 이른 `hintUsages.openedAt`이 없는 시도 수 / 집계 대상 시도 수다. 같은 시각 또는 이후 열람은 최초 답변 전 열람으로 세지 않는다. 열람 내역이 누락되면 임의의 `helped=false`로 채우지 않는다.
- 분모 5 미만에서는 비율 `value`가 null이다. `count`는 분자이며 분자·분모·기간·계산식을 함께 저장한다. 단순 건수 Metric의 `value`도 null이며 `count`를 사용한다.
- 글자 수는 공백·줄바꿈을 포함한 Python Unicode 코드포인트 수다. 예: `가🙂`는 2글자다. 문장 수는 `.?!`·CR/LF로 나눈 비어 있지 않은 덩어리 수다. 문자열을 교정·정규화해 원문을 바꾸지 않는다.
- 연결어 상수의 관리 위치는 `metrics.py`의 `REASON_CONNECTIVES`다. 네 문자열 각각의 비중첩 매칭 횟수를 합한다. `때문에`도 `때문` 1회이며 같은 말이 반복되면 반복 횟수만큼 센다.
- 제출 시도 수·종료일까지 완료한 시도 수·도움 없이 시작한 비율을 Metric으로 저장한다. 다섯 생각 유형은 항상 생성하며 해당 유형 기록이 없으면 `NO_RECORD`다.
- learning 입력의 돌아보기는 `{difficulty:EASY|NORMAL|HARD,text:string|null,createdAt}` 또는 `null`이며 생략도 허용한다. `{written:false}`는 report 결과의 표시 방식이므로 learning 입력 객체로 받지 않는다. 기간 안에 실제 작성했다면 선택 텍스트가 null이어도 report는 `written:true`로 저장한다. 미작성·기간 밖은 `written:false`, difficulty/text null로 저장하며 대신 작성하지 않는다. 내부 저장의 난이도는 코드이며 사용자 표시 변환과 구분한다.
- 평문이 없는 답변은 제출 시도 수에는 포함할 수 있지만 가짜 평문·변화·인용을 만들지 않는다. 인용 후보는 마지막 제출 평문에서 가져오며 `verified:false`다. #52에서 실제 evidence 재조회·대조 후 검증 여부를 결정한다.

## 조회·실패·트랜잭션

`attempts`·`thinking-types`·`changes` 경로를 기존 `internal_client`로 호출한다. 범위가 없는 호출은 거부한다. 재시도를 추가하지 않으며 403·404·5xx·필수 필드 누락·다른 학생/기간·중복/누락 페이지·원문 불일치를 빈 기록으로 바꾸지 않는다.

메모·초안·알 수 없는 추가 필드는 정규화 모델에 전달하지 않는다. 반환된 changes의 최초/마지막 답변 ID·평문과 제출 답변 이력을 대조한다. 생각 유형과 미션도 제출 기록과 일치하는지 검사한다.

계산 결과를 받은 `ReportRepository.finish`는 `COMPLETED` 조건부 전이 후 `report_item`과 `report_item_evidence`를 같은 Session에 저장한다. #50 서비스가 같은 트랜잭션에 완료 Outbox를 추가한다. evidence FK 또는 Outbox 저장이 실패하면 상태·항목·근거·완료 이벤트가 함께 롤백되어 `RUNNING`에서 재개할 수 있다.

item seq는 item_type별 0부터 시작한다. 근거에는 실제 attempt ID·answer ID·answer version을 저장한다. 같은 job을 다시 전달하면 완료된 행을 재사용하여 항목·근거를 중복 저장하지 않는다.

## 검증 결과 (2026-10-27)

| 검사 | 결과 |
|---|---|
| `uv run --frozen ruff check .` | 통과 |
| `uv run --frozen ruff format --check .` | 49개 파일 통과 |
| `uv run --frozen pytest` | **91개 통과, 실패·오류·생략 0개, 25.14초** |
| #51 계산 규칙 | `test_metrics.py` 27개: 0/1/4/5/6건, 도움 시각, UTC/KST 경계, 문자·문장·연결어, 원문 일치·누락 검사 |
| #51 learning 클라이언트 | `test_learning_client.py` 19개: 101건 페이지 수집, 내부 헤더, 삭제·메모 제외, 응답 실패·누락·중복·범위 검사 |
| #51 실제 report DB 저장 | `test_record_generation.py` 5개: 5종 항목·근거, NO_RECORD 완료, 불일치 실패, evidence FK 실패 롤백, 메모 미저장 |
| 기존 회귀 | #14·#50 및 공통 테스트 40개 포함. 실제 PostgreSQL 17.11·RabbitMQ 4.3.7 사용 |
| Docker | `sagomungchi/report-service:issue51-local` 빌드 및 production 의존성만 설치된 이미지에서 새 모듈 import 통과 |

JUnit XML의 테스트 합계·파일별 수와 위 표를 대조했다. 기존 Starlette TestClient deprecation 경고 1개가 있으며 테스트 실패는 없다. Windows 격리 환경의 로컬 소켓 제한으로 멈춘 첫 실행은 성공 결과로 집계하지 않았고, asyncio·Docker 실행이 가능한 환경의 완료 실행만 기록했다. 합성 데이터만 사용했다.

## 완료 조건과 남은 연동

| #51 완료 조건 | 현재 근거 |
|---|---|
| P08 규칙 단위 테스트 | 27개 통과 |
| 고정 learning 응답으로 item·evidence 저장 | MockTransport + 실제 PostgreSQL 저장·중복·롤백 검사 통과 |
| 기록 없는 학생 → COMPLETED + NO_RECORD, LLM 미호출 | 네트워크 요청이 learning GET뿐임을 검사. 현재 R2 생성기는 AI를 호출하지 않음. #52 체인 추가 후에도 생략 분기를 재검증해야 함 |
| Ruff·pytest 통과 | 위 검증 결과 참조 |

2026-10-28에는 최신 #50의 공유 v1 codec·worker 기반이 이 브랜치에 반영됐다. 남은 것은 #27 실제 응답과 API 4.1.1 구현안의 필드·페이지 방식 대조 및 실제 서비스 연동 검증이다. #42 규격 재확정은 요청하지 않는다. #51 구현·검증과 전체 에픽 완료는 구분하며 이슈 종료는 선행 작업 및 실제 연동 상태를 확인한 뒤 판단한다.

## #27 협의 전 사전 정리 (2026-10-28)

- 입력 `reflection:null`과 결과 `written:false`를 구분하고 난이도 입력을 API 1.5의 세 코드로 제한했다. 선택 텍스트 null과 미작성, 기간 밖 기록을 분리해 검사한다.
- attempts 삭제 표식은 선택적 입력이며 정상 빈 목록의 `NO_RECORD`도 허용한다. 삭제된 원문 근거 응답은 별도 evidence 계약이다.
- 기간 이전 도움 기록·시간대 오프셋·0부터 시작하는 페이지 기준을 API 4.1.1에 명시했다. 이미 확정한 연결어 네 개를 유지한다.
- #27 담당자의 응답 예시·실제 PR을 받기 전까지 양쪽 계약 합의나 실제 연동 완료로 표시하지 않는다. 아직 확인할 evidence 원문 범위·버전·삭제·평문 없는 답변의 응답은 이번 수정에서 임의로 바꾸지 않는다.
- 사전 정리 검증: `test_learning_client.py`·`test_metrics.py` **56개 통과(0.66초)**, 변경 Python 파일 Ruff 검사·형식 검사 통과. 이 검사는 합성 HTTP 응답과 계산 규칙에 대한 결과이며 #27 실제 서비스 검증은 아니다. 추가 PR은 등록하지 않았다.
