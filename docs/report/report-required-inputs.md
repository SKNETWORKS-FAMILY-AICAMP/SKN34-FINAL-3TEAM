# 리포트 실제 연동에 남은 입력

2026-10-28 develop `b344797`(PR #105, #27) 기준. 로컬 develop과 누적 작업 브랜치 `feature/report-deletion`에 반영했다. 다른 report 브랜치는 이번에 갱신하지 않았다. 필요한 자료는 API 형식·합성 응답·구현 PR·설정이며 AI Hub 원본이나 운영 자격 증명을 저장소에 올리지 않는다. 이번 확인은 #27 범위이며 아래 다른 담당 항목을 새로 검증한 것은 아니다.

| 대상 | 담당/이슈 | 필요한 내용 |
|---|---|---|
| #51·#52·#54 | report 담당(우리 쪽) | #27 공급 자료 확보, 세 계약 차이 수정, 실제 learning → report 집계·DB·조회·파일 검증 완료. #27 자료를 더 기다릴 필요는 없다. 전체 생성에 남은 AI·core 연결은 아래 별도 항목이다. |
| #52 | #64, 조회 시 미배정 | 서술 API·API 4.2.1 응답·prompt/model 버전. AI 장애 FAILED, 대조 실패 TEMPLATE 기준 연결. 이슈에서 허용한 가짜 응답 검증은 별도 수행했다. |
| #52·#53 | core 리포트 담당 김동섭 | AI 전송 전 이름 가림과 파일 제목에 쓸 신뢰할 수 있는 닉네임 내부 조회 경로. 확정 report.generate.v1 메시지에는 임의로 추가하지 않는다. |
| 실제 생성·#54 | core 리포트/상품 담당 | 현재 503인 ReportEntitlementService의 실제 상품 판정, 조회 시 X-Report-Narrative-Enabled 전달. 이미 구현된 학생 scope·공개 프록시는 재요청하지 않는다. |
| #55 전체 연동 | #42/#45 core 담당 김동섭 | 삭제 전 queued job 정리·늦은 상태 이벤트 무시. 현재 양 scope 모두 생성 차단. 재개가 필요하면 별도 계약을 확정한다. |
| #55 운영 | 조장·DB/인프라 | 별도 guard migration(20261027_02) 검토·표식 보존·S3 버전/복제본·캐시 처리·종료 유예/DLQ 복구. 운영 DB 미적용. |
| #53 운영 | 인프라 | 운영 S3/IAM/IRSA·공개 endpoint·Chromium /tmp writable volume. 로컬 MinIO 구성과 검증은 확보되어 재요청하지 않는다. |

## 이미 확보·확정된 것

- PR #98의 #42/#45 공유 report.*.v1·student.deleted.v1, core 완료 API·SYSTEM/학생 scope 검사·최초 time 보존.
- 이번 #50의 production codec·worker 구독·Outbox. 다른 담당자에게 report codec 작성을 요청하지 않는다.
- 사용자 확정 연결어(왜냐하면·때문·그래서·따라서), AI 장애 FAILED / 대조 실패 TEMPLATE.
- 구현된 PDF 라이브러리·한글 폰트·S3 키·revision 분리. URL 300초는 설정 가능한 운영 기본값.
- 최신 core와 같은 RECORDS 이후 자동 재개 금지. report도 새 생성 차단으로 수정했다.
- #27 [PR #105](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/105)의 실제 DTO·SQL·OpenAPI·회귀 테스트·[구현 보고서](learning-records.md). 아래 기존 질문은 공급 코드와 문서로 확인했다.

## #27 답변 전 report 사전 정리 기록 (2026-10-28)

다음은 답변 전에 수행한 report 보완 기록이다. 이후 #27 계약 확인은 아래 절에 갱신했다. 실제 서비스 연동 완료를 뜻하지 않는다.

- learning 돌아보기 입력은 `reflection:null`(생략도 허용) 또는 `{difficulty:EASY|NORMAL|HARD,text:string|null,createdAt}`이다. `{written:false}`는 입력 객체가 아니라 report 출력/저장 항목의 표현이다. 난이도만 작성한 경우는 `written:true,text:null`로 구분한다.
- 내부 계산·저장에는 난이도 코드를 유지하고 API 3.4·PDF·HTML·Markdown은 `쉬웠어요`·`보통`·`어려웠어요`를 표시한다. OpenAPI도 동일하며 무료/유료 표시는 같다.
- attempts 삭제 표식은 필수가 아니다. 정상 `NO_RECORD` 빈 목록도 허용한다. evidence 삭제 표시와 #55 삭제 완료 절차는 별개다.
- 도움 열람은 조회 시작일 이전이라도 최초 답변 전 기록을 포함한다. 시간은 오프셋 포함, 페이지는 0부터, 연결어는 확정된 네 개를 유지한다.

## #27 병합 후 확인 결과 (2026-10-28)

| 확인 대상 | 확보한 계약·근거 | 판단 |
|---|---|---|
| 구현 PR·명세 | PR #105 병합, `contracts/openapi/learning-service.yaml`의 기록 조회 스키마, `record/controller`·`service`·MyBatis SQL | 확보. 로컬 develop과 누적 report 브랜치에 반영 |
| evidence 정상 응답 | `{items:[...]}`. 정상 항목은 ID·시도·버전·전체 평문 quote·제목·제출 시각·available을 제공. `quote`는 attempts `text`와 같음 | 원문·버전 확인 완료. 잘린 미리보기 문제 없음 |
| 삭제된 근거 | 요청 ID를 중복 제거한 순서로 정상/삭제 항목 모두 반환. 없는 답변·삭제 학생은 `available:false`, 원문 없음 | 개별 삭제 표시를 확보. attempts의 삭제 표식 항목은 없음. report는 중복 없는 ID를 전송 |
| 평문 없는 답변 | 모든 입력 방식의 `text`는 문자열, 비어 있으면 `""`. evidence SQL도 null을 빈 문자열로 변환 | 정상 available=true/quote=null을 허용하도록 바꿀 필요 없음 |
| 시각·돌아보기 | answers·hintUsages는 시작일 이전 포함, 종료일까지. completedAt 제공, 돌아보기 미작성·기간 밖 null, 작성 시 createdAt 포함. EASY·NORMAL·HARD 유지 | 필요한 입력 확보. 난이도 한글 표시는 기존 report 처리 재사용 |
| P08·페이지 | 기간 내 제출 시도, 미완료·PENDING/RUNNING 포함. 종료일까지 전부 FAILED인 시도만 제외. KST 양 끝 포함. attempts·changes page 0부터, size 최대 100 | 기준 확보. thinking-types는 다섯 유형, 별도 페이지 없음 |
| 합성 응답 자료 | 제공자 테스트·보고서에 더해 우리 검증 스크립트로 실제 네 API 응답 JSON을 생성 | 로컬 output/report27-live-20261028-final에 확보. #27 담당자에게 별도 예시를 요청할 필요 없음 |

## 우리 쪽 계약 보완 완료

| 대상 | 해결한 차이 | 완료한 처리 |
|---|---|---|
| learning_client.py의 ScopeInput·_check_scope | 내부 응답에 childId를 요구하던 차이 | studentId로 검사. report 공개 응답 childId 보존, 실제 HTTP 조회로 확인 |
| AnswerInput·AnswerRecord·MetricsCalculator | 표시용 text의 칸 이름까지 세던 차이 | inputType·content의 학생 작성 칸만 집계. 원문 보존, 여섯 입력 방식의 수치를 실제 learning counts와 대조 |
| ChangeInput·변화 출력 | null 되묻기를 거부하던 차이 | DB·API에서 null 보존, PDF·HTML·MD 질문 생략. OpenAPI와 프론트 타입·빈 질문 표시도 정렬 |

수정 전 진단에서 studentId 페이지의 childId 누락 오류, followup:null의 문자열 형식 오류, 논술 합성 예의 39자/11자 집계 차이를 재현했다. 이후 제품 코드를 수정했고 실제 learning HTTP → report 집계 → DB 저장 → report HTTP·파일까지 검증했다. 재현 방법과 범위는 [연동 검증 보고서](report-learning-integration.md)를 따른다.

최종 report 전체 **220개**, 저장소 계약 **54개**, 실제 서비스 연동 **8개 항목** 통과. #27의 학생 기록 삭제 소비자는 별도 미구현이라고 명시되어 있어, 삭제 표식 이후 조회 검증을 #55 전체 삭제 연동 완료로 판단하지 않는다. 실제 AI/core 전체 생성은 별도다.

[인계 문서](report-service-handoff.md)와 [에픽 점검](report-epic-readiness.md)을 참고한다. Slack·이슈 댓글로 요청을 보내지 않았다.
