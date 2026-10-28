# 이슈 #22 learning 미션 조회와 데모 미션 시드

작성일: 2026-10-27. 기준: `develop`의 `e3bb6ab`(#14 PR #60 포함) 및 [이슈 #22](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/22), [API 명세 2.2·3.8·4.1](../design/api-spec.md), [기능 명세 P03·FN-LRN-02·03](../design/functional-spec.md), [상태 다이어그램 3.1](../design/state-diagram.md), [기획서 5장](<../outputs/프로젝트_기획서_사고뭉치.pdf>).

learning-service의 `GET /internal/missions`, `GET /internal/missions/{id}`와 데모 미션 시드를 만들면서 정한 내용과 근거를 기록한다. 데이터베이스 스키마는 바꾸지 않았다. 내부 API는 core가 붙일 쿼리(`grade`·`demo`)를 api-spec 4.1에 추가했다.

## 설계 문서 갱신

구현에 맞춰 설계 문서를 아래와 같이 고쳤다.

| 문서 | 변경 전 | 변경 후 | 근거 |
|---|---|---|---|
| [api-spec 4.1](../design/api-spec.md) learning 미션 조회 | `/internal/missions`, `/internal/missions/{id}` "학생용 미션 조회 (2.2 프록시)" | `?grade&demo` 쿼리와 의미 추가: 학생 학년 `grade`(3~6, 필수), 시연 학생 여부 `demo`(`student.is_demo`, 기본 `false`), `demo_only` 미션은 `demo=true`일 때만 | learning은 학생 학년과 시연 여부를 저장하지 않고 core만 앎. 내부 헤더(`X-User-*`·`X-Student-Scope`)에는 이 값이 없음. core 프록시(#38)가 붙여야 함 |
| [class-diagram 4.1](../design/class-diagram.md) `MissionController`·`MissionService` | `get(missionId) MissionView` | `get(missionId, grade, demo) MissionView` | 상세도 목록과 같은 범위(학년·시연 전용)로 제한하려면 학년과 시연 여부가 필요. 범위 밖은 api-spec 1.3 `409 MISSION_NOT_AVAILABLE`. 프론트 목업(`demoGateway.mission`)도 학생 학년 미션 안에서만 상세를 엶 |
| class-diagram 4.1 `MissionController`·`MissionService` | `list(grade, inputTypes) List`, `listForStudent(studentId, grade) List` | `list(grade, demo) List`, `listForStudent(studentId, grade, demo) List` | `demo`는 시연 전용 미션 노출 판단. `inputTypes`는 같은 문서의 Service 인자와 맞지 않았고, 입력 방식 범위를 넘기는 주체·기준이 문서에 없음. P03이 학년으로 정함(논술 초5~6) |
| state-diagram 3.1 학생 목록 노출 조건 | `demo_only`는 시연 계정만 | 같은 줄에 "시연 학생 여부는 core가 learning 조회에 `demo`(`student.is_demo`)로 넘김" 추가 | 시연 계정 표시는 core DB(`user_account.is_demo`·`student.is_demo`)에만 있음. 전달 방법이 문서에 없었음 |
| [state-diagram 3.1](../design/state-diagram.md) 미션 운영 | 공개는 검토 요청 → `mission_review APPROVED` → 공개만 정의 | 개발·시연용 데모 시드는 관리자 흐름 없이 `PUBLISHED`·`DRAFT`를 직접 넣고 `mission_review`를 만들지 않는다는 줄 추가 | 관리자 작성·검토·공개 기능(FN-ADM-08~13)은 후속. 운영 미션은 기존 전이만 사용 |

## 프론트 목업·잠정 모델과 다른 점 (프론트 담당 확인)

[API 명세 3.7·3.8](../design/api-spec.md)은 프론트 `Mission` 모델을 백엔드 확인 전 잠정 계약으로 쓴다. 설계 문서와는 맞고, 목업과 아래가 다르다.

| 항목 | 프론트 목업·모델 | 구현 | 근거 |
|---|---|---|---|
| 범위 밖 상세 오류 | `demoGateway.mission`이 `404 NOT_FOUND` | `409 MISSION_NOT_AVAILABLE` | api-spec 1.3 "비공개·범위 밖 미션". 없는 미션만 404 |
| `scene` | `Mission.scene`(`math`·`science` 등) | 응답에 없음 | DB(`mission_version`)에 대응 컬럼이 없음. 장면은 `sceneUri`·`staticSceneUri` |
| 입력 틀 | 필드 없음 | `inputTemplate`(풀이 단계·논술 틀 칸 이름) 추가 | api-spec 2.2 상세의 "입력 방식 틀", ERD `input_template` |
| 분류 문항 `categories` | api-spec 3.8 "미션 상세에 `categories:[{id,label}]` 제공" | 제공하지 않음 | DB에 분류 그룹을 담을 컬럼이 없고 이번 시드에 분류 문항이 없음. 프론트에서 추후 맞춤 → #79에서 확정([판정 규칙 보고서](learning-judgment-rules.md)): `categories` 제공 |

## 데모 미션 시드

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 문항 수 | 학년(초3·초4·초5·초6)마다 생각 유형별 1문항, 총 20문항. 문항마다 학년 하나(`grade_min = grade_max`) | 지원 학년 초3~6 (P03). 학년별 성취 수준 차이를 문항에 반영 |
| 공개 범위 | 초3·초5 10문항만 `PUBLISHED`, 초4·초6 10문항은 `DRAFT`. 모두 `demo_only = false` | 시연 초3·초5 각 5문항 (P03), 공개 문항은 초3·초5 각 5개 유지 (api-spec 3.8) |
| 입력 방식 | 학년마다 고르기·순서·서술·풀이 단계·논술을 나눔. 논술은 초5·초6만, 분류는 이번 시드에 없음 | 논술 틀 초5~6 (P03). 이슈 #22 시드 조건(서술·논술·고르기·수학 최종 답 각 1 이상) 충족 |
| 판정 방식 | 고르기·순서·풀이 단계의 최종 답은 정답 키로 규칙 판정, 서술·논술·풀이 과정은 기준표 요소로 AI 판정 | 기획서 5장 "문항 종류별 판정과 진행" |
| 고르기·순서 문항 | 질문은 고르기·순서 맞추기만 요구하고 까닭을 쓰라고 하지 않음. 까닭은 다른 답을 골랐을 때 되묻기로 받음. 기준표 요소는 되묻기 생성에 참고할 "고르는 생각" 하나만(예: "두 화분에서 다른 점(물)을 시든 원인으로 고름"). 예시 답은 정답 해설 | 제출 형식이 `choiceIds`뿐이라 글을 쓸 칸이 없음 (api-spec 3.1·3.8). 고르기는 정답 키로 판정하고 다른 답에는 까닭을 묻는 되묻기로 연결, 저학년 이유 설명은 판정하지 않음 (FN-JDG-01). 정답이면 바로 마무리 (P04) |
| 기준표 설명 | 요소 설명에 미션 주제를 넣음. 예: "쉬는 시간을 20분으로 늘리는 것에 찬성 또는 반대 입장을 밝힘". 풀이 단계의 "방법 세우기"는 여러 방법을 인정하되 남은 부분만의 넓이·부피를 구하는 방법으로 씀 | ai 판정 요청에는 학생 답과 기준표 요소만 가고 미션 질문은 없음 ([API 명세 4.2](../design/api-spec.md)). 설명이 일반적이면 주제와 무관한 답이나 틀린 방법도 충족으로 판정될 수 있음 |
| 풀이 단계 | 입력 틀 ① 무엇을 구하나요? ② 어떻게 구할까요? ③ 계산 ④ 확인해 보기 / 최종 답. 기준표는 방법과 무관한 생각 단계(문제 파악·방법 세우기 필수, 결과 확인은 들어가면 좋은 생각) | 풀이 방법이 여러 가지라 특정 방법을 요소로 두지 않음 |
| 질문 은행 | 되묻기 유형마다 2개, 총 6개. 정답·미션 내용 없음 | P16. ai 되묻기가 유출 검사에 걸리면 learning이 같은 유형에서 고름 |
| 작성 | 문항·기준표·예시 답은 learning 담당이 작성. AI Hub 문항·답안 미사용 | 이슈 #22 "확인 필요" 항목을 담당자가 정함 |
| 정답 키 | 값만 넣음. 고르기·순서 `{"choiceIds":[...]}`(순서는 정답 순), 풀이 단계 `{"finalAnswer":"30 m²"}` → #79에서 확정([판정 규칙 보고서](learning-judgment-rules.md)): 수만(`30`), 단위는 `answer_unit` | 학생 제출 필드 이름(api-spec 3.8 `choiceIds`·`finalAnswer`)과 맞춤. ERD는 "정답·동치 표현"만 정함. 단위·동치 비교는 판정 규칙의 일 |
| 기타 값 | `judge_verified = false`(사람 검증 전), `basic_skills` 비움, 작성자 `created_by`는 고정된 시드용 ID | 기초 능력 값 목록이 문서에 없음. `created_by`는 NOT NULL이지만 core 사용자와 FK가 없음 |
| 적재 | `backend/learning-service/db/seed/`의 SQL을 로컬 DB에 직접 적용. 마이그레이션(Flyway)에 넣지 않음. ID를 고정하고 `INSERT … ON CONFLICT (id) DO UPDATE`라 다시 실행하면 파일 내용으로 덮어씀. 적용 방법은 파일 머리말 | 시드는 개발·시연용이라 운영 스키마와 분리. 이슈 #22 "확인 필요" 항목을 담당자가 정함. 시도를 만든 뒤에도 문항을 고쳐 다시 적용할 수 있게 지우고 다시 넣지 않음. 파일에서 빼낸 요소·질문은 DB에 남으므로 직접 지움 |

### 성취기준

2022 개정 교육과정 원문(교육부 고시 제2022-33호 과학과 [별책 9]·국어과 [별책 5]·도덕과 [별책 6], 수학과 교육과정)에서 코드와 문장을 확인했다. 초5·초6은 기획서 5.3(1)의 생각 유형별 예시 기준을 따른다. 기준과 맞지 않던 초안 문항 두 개는 코드가 아니라 문항 내용을 고쳤다.

| 기획서 기준 | 처음 문항 | 고친 문항 |
|---|---|---|
| `[6국01-02]` 주장을 파악하고 이유나 근거가 타당한지 평가하며 듣는다 | 휴대폰 논술에서 내 주장만 씀 | 친구의 주장과 까닭 두 개를 주고 까닭이 타당한지 따진 뒤 내 주장을 씀 |
| `[6수03-14]` 평행사변형, 삼각형, 사다리꼴, 마름모의 넓이 | 직사각형 화단에서 뗀 부분 | 사다리꼴 화단의 넓이 |

| 학년 | 분석하기 | 따져 보기 | 새로 만들기 | 문제 해결하기 | 돌아보기 |
|---|---|---|---|---|---|
| 초3 | `[4과04-02]` | `[4국03-03]` | `[4도02-02]` | `[4수02-01]` | `[4도01-04]` |
| 초4 | `[4과09-02]` | `[4국02-04]` | `[4과05-03]` | `[4수01-04]` `[4수01-03]` | `[4국03-05]` |
| 초5 | `[6과07-02]` | `[6국01-02]` | `[6도03-02]` | `[6수03-14]` | `[6국03-05]` |
| 초6 | `[6과14-02]` | `[6국03-02]` | `[6도04-01]` | `[6수03-19]` | `[6국06-04]` |

3~4학년군 과학에는 그림자 성취기준이 없어(그림자는 `[6과13-01]`) 초4 분석하기를 자석으로 정했다. 초4 수학은 세 자리 수 범위(`[4수01-03]`·`[4수01-04]`) 안의 수만 쓴다.

## 구현에서 정한 것

클래스·메서드 이름은 [클래스 다이어그램 4.1](../design/class-diagram.md)을 따른다 (`MissionController`, `MissionService.listForStudent`·`get`, `MissionRepository`, `MissionView`). 메서드 인자는 위 "설계 문서 갱신"대로 class-diagram을 고쳤다.

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 학생용 객체 이름 | `MissionView`. 정답·예시 답·기준표 필드가 없어 응답에 섞일 수 없음 | class-diagram의 `get(missionId, grade) MissionView`. `Mission`은 공개·검토 규칙을 가진 관리자 쪽 엔티티 이름으로 남김 |
| 수행 상태 조회 | `MissionRepository`가 `attempt`에서 미션별 가장 최근 시도를 읽음. 없으면 `NOT_STARTED` | class-diagram에서 `MissionService`는 `MissionRepository`만 쓰고 `AttemptService`가 `MissionService`를 씀. attempt 쪽 서비스를 부르면 순환 |
| 상세 조회 범위 | 목록과 같은 범위(공개 + 학생 학년·입력 방식). 비공개·범위 밖이면 `409 MISSION_NOT_AVAILABLE`, 없으면 `404 NOT_FOUND`. 메서드는 `get(missionId, grade)` | api-spec 1.3 `MISSION_NOT_AVAILABLE`(비공개·범위 밖 미션). 프론트 목업(`demoGateway.mission`)도 학생 학년 미션 안에서만 상세를 엶. 범위 확인에 학년이 필요해 class-diagram을 `get(missionId, grade)`로 갱신. 목업은 범위 밖을 `404 NOT_FOUND`로 처리해 api-spec과 다름 → 프론트 담당 확인 |
| 목록 위치 | `position`은 학생 학년 목록에서 1부터, `total`은 그 목록 크기. 페이지 나누기(api-spec 1.1)는 Controller | api-spec 3.8 목록 항목. Service 인자는 class-diagram 그대로 |
| 학생 확인 | `X-User-Role: STUDENT`이고 `X-Student-Scope`에 학생 1명일 때만 허용, 그 학생이 조회 대상. 아니면 `403 FORBIDDEN` | 학생 미션 API는 역할 학생 (api-spec 2.2). core가 `/missions`를 그대로 넘기는 프록시라 경로에 학생 ID가 없음 (api-spec 4.1) |
| 학년 | core가 쿼리 `grade`(3~6)로 넘김. 범위 밖이면 `400 VALIDATION_FAILED` | 학생 학년은 core에만 있음. 지원 학년 초3~6 (P03) |
| 응답 필드 | 프론트 `Mission` 모델 이름. 안내는 `hint`, 학년 범위는 `grade`·`gradeMax`, 입력 틀은 `inputTemplate`. 프론트의 `scene`은 DB에 없어 제외(장면은 `sceneUri`) | api-spec 3.7·3.8이 프론트 모델을 잠정 계약으로 씀 |
| 목록 봉투 | `PageResponse`를 `mission/controller`에 둠 | 공통으로 쓸 곳이 생기면 `_common`으로 옮김. architecture 2.6 `_common` 구성을 지금 바꾸지 않음 |
| 입력 방식 범위 | 학년으로 계산(논술은 초5 이상, P03). `inputTypes`는 받지 않음 | 입력 방식 범위를 넘기는 주체·기준이 문서에 없고 P03이 학년으로 정함. class-diagram을 `list(grade)`로 갱신 |
| 시연 전용 미션 | `demo_only = true` 미션은 `demo=true`일 때만 목록·상세에 노출, 아니면 목록에서 빠지고 상세는 409. 노출 규칙은 `MissionView.isOpenTo(grade, demo)` 한곳에 둠(학년 범위, 논술 초5~6, 시연 전용). SQL은 `demo_only`를 함께 읽기만 함. `demo`가 없으면 `false` | state-diagram 3.1 "시연 계정만"(FN-LRN-02). 기본값 `false`라 core가 붙이기 전에는 모두 제외 |

## #14 Repository 기반 사용

#14(PR #60)가 develop에 머지된 뒤 그 방식으로 맞췄다. #14 파일은 고치지 않았다.

- Mapper XML constructor resultMap으로 `MissionView`를 바로 만든다. UUID는 #14의 전역 `UuidTypeHandler`가 변환한다.
- `choices`·`input_template`(jsonb)은 #14 보고서 권장대로 요소 타입을 지정한 `JacksonJsonbTypeHandler`(`ChoiceListTypeHandler`·`StringListTypeHandler`)로 변환한다. 일반 `List`에 전역 적용되지 않도록 `TypeReference<List<Choice>>` 등 구체 타입으로만 등록하고, XML의 `typeHandler`로 지정한다(`MissionPersistenceConfig`). 값이 없으면 SQL에서 빈 배열로 바꾼다.
- `MissionRepositoryTest`가 `PostgresRepositoryTest`를 상속해 실제 PostgreSQL 17.11(Flyway V1~V5)에서 확인한다: 공개 미션의 현재 버전만 `sort_order` 순, jsonb 변환, 비공개·없는 미션 구분, 시연 전용 여부 읽기, 학생별 가장 최근 시도 상태.
- 기존 `InternalAuthFilterTest`가 대상 없는 `@WebMvcTest`로 모든 Controller를 불러와 `MissionController`가 생기자 실패했다. 테스트 대상을 시험용 Controller로 제한했다.

## 검증

2026-10-27, develop `ecd6ecf` 병합 상태, JDK 21, Docker Desktop.

- `./gradlew clean test bootJar`: 24개 통과, 실패·생략 0개. 미션 테스트 17개(`MissionRepositoryTest` 4, `MissionServiceTest` 7, `MissionControllerTest` 6)와 기존 7개. `docker build` 성공.
- 시드: 로컬 compose PostgreSQL(learning V1~V5)에 여러 번 적용, 모두 성공. 미션 20(초3·초5 `PUBLISHED` 각 5, 초4·초6 `DRAFT` 각 5), 기준표 요소 53, 생각 열기 40, 질문 은행 6.
- 앱을 로컬로 띄우고 시드 데이터로 `/internal/missions` 호출:

| 요청 | 결과 |
|---|---|
| 초3 목록 | 200, 5개(고르기·서술·순서), `position` 1~5 |
| 초5 목록 | 200, 5개(논술·풀이 단계 포함) |
| 초4 목록 | 200, 0개 (`DRAFT`) |
| 초3 미션 상세 | 200, 정답·예시 답·기준표 필드 없음 |
| 초3 미션을 초5 학생이 상세 조회 / `DRAFT` 미션 상세 | 409 `MISSION_NOT_AVAILABLE` |
| 없는 미션 | 404 `NOT_FOUND` |
| 학부모 역할 | 403 `FORBIDDEN` |
| 진행 중 시도 1건을 넣은 뒤 목록 | 그 미션만 `IN_PROGRESS`와 `attemptId` (확인 후 시도 삭제) |

## 후속

| 항목 | 지금 | 후속에서 할 일 |
|---|---|---|
| core 프록시가 붙일 쿼리 | learning은 `grade`(필수)·`demo`(기본 `false`)를 받음 | core #38(학생 미션 API learning 프록시)에서 학생 학년과 `student.is_demo`를 붙임. 붙이기 전에는 `demo_only` 미션이 모두에게서 빠짐 |
| 공개 중단·새 버전과 진행 중 시도 | 미션 목록·상세는 지금 공개된 현재 버전 기준. 공개 중단된 미션은 목록에서 빠져 진행 중 상태도 목록에 안 보이고, 새 버전을 공개하면 상세는 새 버전 질문을 보여 줌 | 진행 중 시도는 시작 당시 버전을 유지해야 함(P07, state-diagram 3.1). #23 시도 상세가 시도에 고정된 `mission_version`을 주고, 이어하기는 시도(학생 홈 `resume`)로 들어가는지 확인 |
| 분류 문항 `categories` | 제공하지 않음 | 분류 그룹 저장 위치(ERD)와 함께 정하고 프론트에서 맞춤 → #79에서 확정([판정 규칙 보고서](learning-judgment-rules.md)) |
