# #55 삭제 장벽 마이그레이션 검토

기존 report 초기 revision을 수정하지 않고 `20261027_02`를 추가한다. 학생 삭제와 겹친 생성, 삭제 전 발행되었다가 늦게 전달되는 생성 명령 때문에 삭제한 리포트가 다시 만들어지는 것을 막기 위한 최소 상태다. 기능 코드와 별도 커밋으로 검토한다.

| 컬럼 | 제약 | 목적 |
|---|---|---|
| student_id | UUID PK, NOT NULL | 학생별 장벽 하나 |
| scope | varchar, PROFILE/RECORDS CHECK, NOT NULL | 영구 삭제와 기록 초기화 구분 |
| cutoff_at | timestamptz, NOT NULL | 삭제 전 생성 명령을 걸러내는 최초 이벤트 시각 |
| deletion_request_id | UUID, NOT NULL | 현재/마지막 삭제 요청 식별 |
| status | varchar, PENDING/COMPLETED CHECK, NOT NULL | 실패 후 재시도 중 생성·조회 차단 |
| updated_at | timestamptz, NOT NULL | 운영 처리 시각 |

이름·답변·서술·파일 경로는 저장하지 않는다. 다른 DB와 물리 FK를 만들지 않는다. `processed_event`에는 처리 완료한 이벤트 UUID를 기록하며 core 완료 보고 실패 시 다음 전달에서 보고만 반복한다.

2026-10-27 일회용 PostgreSQL 17.11에서 세 DB 전체 적용, ERD 대조, 잘못된 scope/status/NULL 거부, 정상값 허용, 반복 적용 no-op, report downgrade base → upgrade head를 확인했다. core 35테이블/318컬럼, learning 19/156, report 7/50, 총 61/524다. 제약 음성 사례 50개, CHECK 값 집합 64개, ERD 인덱스 19개 검증을 포함하며 전체 12.7초였다. 기존 #5/#19 보고서 수치는 해당 시점의 기록으로 유지한다.

운영 DB에 적용하지 않았다. PROFILE 영구 차단·RECORDS 이후 새 명령 허용, 표식 보존 기간, 서비스 간 최초 이벤트 시각 기준은 #45/core 담당자 검토가 필요하다. 저장소가 버전 관리/복제를 사용한다면 이전 객체 버전·복제본의 삭제 정책도 인프라에서 확정해야 한다. 롤백은 표식을 제거하므로 삭제 이벤트/생성 큐가 살아 있는 운영 환경에서 무조건 수행하면 안 된다.
