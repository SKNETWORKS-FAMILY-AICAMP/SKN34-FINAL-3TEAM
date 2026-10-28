# 이슈 #54 리포트 조회 내부 API

기존 작업 브랜치는 `feature/report-query`다. 아래 초기 검증 기록 이후, #53 검증 커밋 `c10e8b9`에 조회 브랜치 `5661d21`을 통합하고 `local/issue54-integration`에서 재검증했다. 현재 검증 결과는 마지막 절을 기준으로 한다. `query/router.py`·`service.py`·`schemas.py`를 추가하고 API 앱에 등록했다. 설계 문서 1.6·3.4의 수치·유형·변화·돌아보기·인용·검증·버전을 응답 모델로 검사한다.

## 동작

| API | 동작 |
|---|---|
| 목록 | studentId 범위 확인 → 학생/대상 주별 최신 revision 선택 → status 필터 → 페이지 반환 |
| 상세 | reportId 소속 학생 확인 → 같은 학생/대상 주의 최신판 기본 조회, revision으로 이전판 선택, revisions 포함 |
| 근거 | 실제 reportId와 itemId의 소속 확인 → learning 원문 재조회. 삭제 원문은 available:false이며 저장된 예전 quote로 대체하지 않음 |
| 파일 | 실제 reportId 판의 메타데이터·학생·형식·키를 검사하고 현재 권한의 full/free 파일에 한정해 서명 |

모든 경로는 기존 내부 토큰 검사와 X-Student-Scope를 사용한다. 범위 밖 학생 403, 없는 보고서/판/항목/파일 404, 형식 오류 400이다. 원문 조회·스토리지 장애는 정상적인 빈 응답으로 숨기지 않는다. 응답 스키마 오류 로그에 학생 원문이 포함되지 않도록 전용 핸들러를 추가했다.

현재 이용권의 판단 주체는 core다. `X-Report-Narrative-Enabled`가 없으면 false다. false일 때 narrative·저녁 질문·생각 유형 summary를 응답과 파생 파일에서 제외한다. 생성 당시 유료 여부만으로 이전 유료 파일을 서명하지 않는다. 이 헤더는 core가 검증한 권한으로 설정해야 하며 웹에서 받은 값을 그대로 전달하면 안 된다.

API 4.4와 `contracts/openapi/report-service.yaml`을 맞췄다. OpenAPI는 실제 FastAPI 모델에서 내보낸 JSON 표현의 YAML 1.2 문서이며 테스트에서 서버 스키마와 대조한다. URL 경로의 snake_case placeholder 이름은 서버 함수 이름이며 실제 URL 식별자는 UUID다.

## 돌아보기 표시 계약 정리 (2026-10-28)

API 3.4의 `reflections[].difficulty`는 `쉬웠어요`·`보통`·`어려웠어요` 또는 미작성의 null이다. 조회 응답 모델과 OpenAPI에 이 범위를 명시하고, #53과 공유하는 `generation/presentation.py`에서 저장된 `EASY`·`NORMAL`·`HARD`를 변환한다. PDF·HTML·Markdown과 같은 표시값이며 DB payload를 덮어쓰지 않는다. 무료/유료 응답 모두 동일하다. 난이도를 선택하고 글을 쓰지 않은 돌아보기는 `written:true,text:null`, 미작성은 `written:false,difficulty:null,text:null`이다.

learning 입력은 API 4.1.1의 `reflection:null` 또는 코드·작성 시각이 있는 객체다. 조회 출력과 입력을 혼용하지 않는다. 초기 작업에서는 #27 evidence 계약을 확인 대기로 기록했으며, 현재 통합본은 develop의 #27/#51 수신 계약과 #52 원문 검증을 유지한다. 이번 검증은 실제 learning 서버 실행과 구분한다.

사전 정리 검증: `test_report_query.py` **22개 통과(51.33초)**. 일회용 PostgreSQL의 코드값을 조회해 무료/유료 API의 세 한글 표시값·미작성 null·작성했지만 텍스트가 없는 경우·DB payload 보존을 확인했다. 실제 FastAPI OpenAPI와 저장한 계약 파일도 일치한다. 기존 TestClient deprecation warning 1개는 실패와 구분한다.

## 검증

집중 검증은 `test_report_query.py` 14개를 포함한다: 기본 최신판·이전판, 최신 선택 후 상태 필터, 네 경로 학생 범위 검사, 무료/헤더 누락 가림, 실제 원문/삭제 근거, 권한별 파일 변형, 400/404, OpenAPI 대조, 응답 오류의 원문 비노출. 실제 PostgreSQL을 사용하고 core 프록시·learning·S3 서명 공급자는 명시한 대역으로 검사한다. 최종 회귀 결과는 통합 보고서에 기록한다.

2026-10-27 #53 보강에서는 실제 PostgreSQL·MinIO로 생성한 파일을 이 내부 API에서 조회해 full/free 6개를 HTTP 다운로드했다. 허용 학생 범위 밖 요청 403, 삭제된 객체의 서명 재발급 503도 확인했다. 실제 core 프록시의 권한 전달은 이 테스트에서 대체하지 않는다. 자세한 범위는 [#53 검증 보고서](report-rendering.md)를 따른다.

## 완성을 위한 외부 연결

- core 공개 프록시: 기준 develop의 ReportClient는 학생 범위를 전달하지만 현재 상품 권한 헤더는 아직 설정하지 않는다. report는 헤더 누락을 무료로 처리하는 기존 기준을 유지한다. 상품 권한 공급·전달과 실제 공개 API 연동은 core 담당 범위다. report 목록에 없는 QUEUED 작업 표시는 core report_job과 결합해야 한다.
- #27: 병합된 LearningClient의 answerId/attemptId/version·원문·available:false 및 410 계약을 사용한다. 실제 learning 서버까지 포함한 통합 검증은 별도다.
- 인프라: 브라우저에서 접근 가능한 S3/MinIO 서명 주소와 버킷 권한을 주입해야 한다. 수명 기본값 300초는 변경 가능한 초기 운영값이며 최종 팀 운영 설정과 구분한다.

실제 core 프록시를 거친 브라우저 E2E, 실제 AWS 서명 다운로드는 아직 검증하지 않았다.

## #53 검증본 기준 통합·요구사항 검증 (2026-10-28)

기준은 develop `b644b56f`와 #53을 통합한 `c10e8b9`다. 여기에 기존 #54 브랜치 `5661d21`을 병합했으며 소스·문서의 Git 충돌은 없었다. 기준 develop과 #53 전용 검증 브랜치는 변경하지 않았다. 이번 결과는 로컬에만 보존하며 GitHub push·PR 수정은 하지 않았다.

### 계약 보완과 팀 문서 정합성

학습 기록의 `followup:null`은 #51/#53에서 이미 허용하지만 기존 #54 `Change` 응답 모델은 문자열만 허용했다. 실제 PostgreSQL에 해당 payload를 저장한 뒤 무료·유료 상세 조회를 실행하여 HTTP 500을 각각 재현했다. 설계 문서 API 3.4에 null의 의미를 먼저 명시하고, 응답 모델과 자동 생성 OpenAPI에 같은 계약을 반영했다. 원문 답변·계산 수치·DB payload는 변경하지 않는다.

기존 권한 책임(core 판단, report 학생 범위 검사), 무료 조회 시 가림, 기본 URL 수명 300초와 설정 범위 1~3600초는 변경하지 않았다. 별도 공통 인증·DB 트랜잭션 계층이나 마이그레이션은 추가하지 않았다. 공유 문서 변경은 API 3.4의 nullable 설명과 기존 README의 #54 보고서 링크이며, 상세 검증 기록은 이 문서에 둔다. OpenAPI는 실제 앱에서 재생성하고 일치 테스트로 확인했다. 운영값의 새 정책 승인이나 전체 서비스 연동 완료를 주장하지 않는다.

### 해야 할 일

- [x] `GET /internal/reports?studentId&status`: 대상 주별 최신 revision을 먼저 선택하고 상태·페이지 처리
- [x] `GET /internal/reports/{reportId}?revision`: item_type별 조립, 기본 최신판·지정 이전판·revisions 반환
- [x] `GET /internal/reports/{reportId}/evidence/{itemId}`: 해당 판의 항목 소속 확인, learning 원문 재조회·삭제 시 available:false
- [x] `GET /internal/reports/{reportId}/files/{format}`: #53 ObjectStorage 재사용, 해당 reportId의 판·현재 상품 범위에 맞는 URL·expiresAt 반환
- [x] 범위 밖 학생 403, 없는 리포트·판·항목 404, RFC 9457 오류 형식

### 완료 조건

- [x] API 3.4 응답 모델·실제 OpenAPI 일치·nullable 및 돌아보기 표시 테스트
- [x] 기본 최신판·revision 지정 조회 테스트
- [x] 네 경로의 범위 밖 학생 403 테스트
- [x] Ruff check·format 검사 및 전체 pytest 통과

### 이번 실행 결과

- `uv run --frozen ruff check --no-cache .`: 통과.
- `uv run --frozen ruff format --check --no-cache .`: 70개 파일 일치.
- report 전체 pytest: **215 passed, 30.16초**, 실패·건너뜀 없음. 이 중 조회 테스트 31개이며 #53의 렌더링·저장 회귀도 포함한다.
- 공통 계약·스키마 unittest: **58개 통과**.
- 운영 Docker 이미지 `local/issue54-report:20261028` 빌드 성공.
- 초기 nullable 회귀 테스트 2개는 수정 전 500으로 실패했고 수정 후 전체 검사에서 통과했다. 실패한 초기 실행은 성공 수치에 합산하지 않았다.
- 기존 Starlette/httpx 폐기 예정 경고 1개는 남아 있다.

검사는 실제 PostgreSQL·RabbitMQ 테스트 컨테이너를 사용한다. 추가로 인증/범위 누락의 RFC 9457, 다른 revision의 itemId 거부, 잘못된 학생 파일 키 서명 차단, 실제 LearningClient와 HTTP 대역을 통한 410/503/근거 누락 처리, 실제 ObjectStorage와 moto를 통한 full/free·이전판 다운로드 및 설정 TTL을 검증했다. HTTP 대역·moto 검사를 실제 core/learning/AWS 연결로 표현하지 않는다.

검증용 의존성 이미지는 앞선 #53 이미지(`local/issue53-verify:20261028`)를 재사용하되 `/workspace`에는 **이번 #54 로컬 작업 폴더**를 읽기 전용으로 연결했다. 따라서 실행 대상 소스는 이번 통합본이다. 로그·JUnit XML은 저장소 밖 `SKN34-FINAL-3TEAM-context/issue54-validation/`에 보존했다. 원격 develop이 이후 변경되면 해당 새 기준으로 재검증해야 한다.
