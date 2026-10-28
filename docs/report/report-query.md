# 이슈 #54 리포트 조회 내부 API

기반은 #53 커밋 `3cfa9f1`, 작업 브랜치는 `feature/report-query`다. `query/router.py`·`service.py`·`schemas.py`를 추가하고 API 앱에 등록했다. 설계 문서 1.6·3.4의 수치·유형·변화·돌아보기·인용·검증·버전을 응답 모델로 검사한다.

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

learning 입력은 API 4.1.1의 `reflection:null` 또는 코드·작성 시각이 있는 객체다. 조회 출력과 입력을 혼용하지 않는다. #27 실제 evidence의 원문 범위·버전·삭제·평문 없는 답변 표현은 담당자 답변을 기다리며 기존 evidence 검증을 임의로 완화하지 않았다.

사전 정리 검증: `test_report_query.py` **22개 통과(51.33초)**. 일회용 PostgreSQL의 코드값을 조회해 무료/유료 API의 세 한글 표시값·미작성 null·작성했지만 텍스트가 없는 경우·DB payload 보존을 확인했다. 실제 FastAPI OpenAPI와 저장한 계약 파일도 일치한다. 기존 TestClient deprecation warning 1개는 실패와 구분한다.

## 검증

집중 검증은 `test_report_query.py` 14개를 포함한다: 기본 최신판·이전판, 최신 선택 후 상태 필터, 네 경로 학생 범위 검사, 무료/헤더 누락 가림, 실제 원문/삭제 근거, 권한별 파일 변형, 400/404, OpenAPI 대조, 응답 오류의 원문 비노출. 실제 PostgreSQL을 사용하고 core 프록시·learning·S3 서명 공급자는 명시한 대역으로 검사한다. 최종 회귀 결과는 통합 보고서에 기록한다.

## 완성을 위한 외부 연결

- 김동섭님 #42: 공개 목록·상세·근거·다운로드 프록시에서 범위 헤더와 현재 상품 권한 헤더를 설정해야 한다. report 목록에 없는 QUEUED 작업의 표시는 core report_job과 결합해야 한다.
- #27: evidence의 answerId/attemptId/version·원문·available:false 및 410 계약을 맞춰야 한다.
- 인프라: 브라우저에서 접근 가능한 S3/MinIO 서명 주소와 버킷 권한을 주입해야 한다. 수명 기본값 300초는 변경 가능한 초기 운영값이며 최종 팀 운영 설정과 구분한다.

실제 core 프록시를 거친 브라우저 E2E, 실제 AWS 서명 다운로드는 아직 검증하지 않았다.
