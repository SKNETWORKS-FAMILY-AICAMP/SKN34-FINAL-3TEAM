# 이슈 #55 학생 삭제 처리

`feature/report-deletion`은 #54 조회 구현 위에 삭제 소비자와 worker 조립을 추가한다. #45 공유 스키마를 임의로 만들지 않고 아키텍처의 `student.deleted.v1`, subject 학생 UUID, data의 `deletionRequestId`·`scope`를 읽는다. 실제 producer와 계약 테스트는 남아 있다.

## 처리 순서와 실패

1. 학생 단위 배타 advisory lock을 얻는다. 생성은 같은 학생 shared lock과 job lock을 사용한다. RUNNING 생성이 실제 수행 중이면 삭제는 오류를 반환해 기존 지연 큐로 이동하며, 생성이 종료된 다음 재시도한다.
2. `report_deletion_guard`를 PENDING으로 커밋한다. 이 상태에서는 새 생성과 리포트 조회를 차단한다.
3. 해당 학생 `reports/{studentId}/` 아래 S3 객체를 삭제한다. 실패하면 DB 리포트 행과 PENDING 장벽을 남기고 재시도한다. 파일 일부가 먼저 삭제되었을 수 있으므로 원자적 S3/DB 트랜잭션이라고 표현하지 않는다.
4. `report_item_evidence → report_item → report_file → weekly_report`와 해당 학생 Outbox를 삭제하고 guard COMPLETED·processed_event를 같은 DB 트랜잭션에 저장한다.
5. 기존 내부 HTTP 클라이언트로 core 완료 API에 `{service:"report"}`를 보낸다. 실패하면 이벤트 재시도에서 물리 삭제를 반복하지 않고 완료 보고를 다시 보낸다.

동일 이벤트 두 번 처리 시 S3/DB 삭제는 한 번이고 완료 보고는 두 번일 수 있다. 다른 학생은 삭제 범위에 들어가지 않는다. 더 오래된 RECORDS 이벤트는 최신 삭제 이후 생성된 리포트를 다시 지우지 않으며 PROFILE은 RECORDS보다 우선한다.

## 구현 기본안과 팀 확인

PROFILE·RECORDS 모두 기존 리포트 내용/파일을 삭제한다. PROFILE은 이후 생성도 차단하며 RECORDS는 삭제 이후 최초 생성 명령만 허용한다. 이것은 사용자나 팀이 확정한 정책으로 보고하지 않는다. #45와 범위·삭제 중 요청·시각 기준·삭제 표식 보존을 확정한 뒤 운영 적용한다. 추가 DDL은 [별도 스키마 보고서](report-deletion-schema.md)에서 검토한다.

`worker.run(codec)`은 생성/삭제 소비자와 Outbox를 조립한다. 기본 `python -m app.worker`는 #42 production codec이 없으므로 생성 큐를 소비하지 않고 경고한다. 가짜 성공 응답이나 임의 공유 메시지는 사용하지 않는다. 종료 시 소비 취소 → 진행 중 처리 대기 → 채널 정리 순서를 사용한다. SIGTERM 유예 시간과 DLQ 복구는 운영 설정이 필요하다.

## 검증

2026-10-27 삭제 테스트 10개를 포함한 report 전체 **144개 통과**, Ruff check/format 통과. 실제 PostgreSQL에서 중복·다른 학생 보존·S3 오류 재시도 큐 이동·core 장애 후 보고만 재시도·생성/삭제 lock 충돌·늦은 명령 차단·기록 초기화 후 새 명령·오래된 삭제·조회 차단을 확인했다. 저장소 오류는 테스트 대역이고 별도 렌더링 테스트는 moto S3를 사용한다. 실제 core/learning/MinIO를 모두 연결한 통합 검증으로 표현하지 않는다.

생성 도중 업로드 취소는 작업 스레드 정리까지 기다린 뒤 lock을 반환한다. 다른 프로세스의 비정상 종료로 남은 RUNNING 행은 삭제가 lock을 얻은 후 함께 정리한다. 발행 중이던 Outbox 이벤트, 이미 발급된 URL, S3 이전 버전/캐시는 report DB 삭제만으로 모두 회수할 수 없으므로 인계 문서의 core/인프라 후속 사항이 필요하다.
