# 리포트 실제 연동에 남은 입력

2026-10-28 develop `47e5ffe` 기준. 과거 미확보 목록을 현재 상태로 교체한다. 필요한 자료는 API 형식·합성 응답·구현 PR·설정이며 AI Hub 원본이나 운영 자격 증명을 저장소에 올리지 않는다.

| 대상 | 담당/이슈 | 필요한 내용 |
|---|---|---|
| #51·#52·#54 | #27, Overlay1010 | attempts/thinking-types/changes/evidence 실제 DTO·페이지·기간·버전·삭제 표식을 API 4.1.1 report 입력 구현안과 대조. exists만으로 집계·원문 대조를 할 수 없다. |
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

[인계 문서](report-service-handoff.md)와 [에픽 점검](report-epic-readiness.md)을 참고한다. Slack·이슈 댓글로 요청을 보내지 않았다.
