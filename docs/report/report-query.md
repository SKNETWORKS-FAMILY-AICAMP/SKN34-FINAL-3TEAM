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

## 검증

집중 검증은 `test_report_query.py` 14개를 포함한다: 기본 최신판·이전판, 최신 선택 후 상태 필터, 네 경로 학생 범위 검사, 무료/헤더 누락 가림, 실제 원문/삭제 근거, 권한별 파일 변형, 400/404, OpenAPI 대조, 응답 오류의 원문 비노출. 실제 PostgreSQL을 사용하고 core 프록시·learning·S3 서명 공급자는 명시한 대역으로 검사한다. 최종 회귀 결과는 통합 보고서에 기록한다.

2026-10-27 #53 보강에서는 실제 PostgreSQL·MinIO로 생성한 파일을 이 내부 API에서 조회해 full/free 6개를 HTTP 다운로드했다. 허용 학생 범위 밖 요청 403, 삭제된 객체의 서명 재발급 503도 확인했다. 실제 core 프록시의 권한 전달은 이 테스트에서 대체하지 않는다. 자세한 범위는 [#53 검증 보고서](report-rendering.md)를 따른다.

## 완성을 위한 외부 연결

- 김동섭님 #42: 공개 목록·상세·근거·다운로드 프록시에서 범위 헤더와 현재 상품 권한 헤더를 설정해야 한다. report 목록에 없는 QUEUED 작업의 표시는 core report_job과 결합해야 한다.
- #27: evidence의 answerId/attemptId/version·원문·available:false 및 410 계약을 맞춰야 한다.
- 인프라: 로컬 MinIO 내부/공개 주소 분리와 호스트 HTTP 다운로드는 검증했다. 운영 S3 주소·버킷 권한 주입은 후속이다. 수명 기본값 300초는 변경 가능한 초기 운영값이며 최종 팀 운영 설정과 구분한다.

실제 core 프록시를 거친 브라우저 E2E, 실제 AWS 서명 다운로드는 아직 검증하지 않았다.
