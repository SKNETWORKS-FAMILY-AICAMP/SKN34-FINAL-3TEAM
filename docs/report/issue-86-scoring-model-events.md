# #86 scoring 활성 버전 이벤트 수신 검토

작성일: 2026-10-29. 작업 브랜치: `feature/scoring-model-events`.
#85 구현 브랜치에서 이어 작업했으며 기존 #85 실제 모델 검증 자료는 보존했다.
원격 PR·push·이슈 체크박스 갱신은 하지 않는다.

## 목적과 확정 기준

core에서 모델 버전을 활성화하거나 롤백하면 모든 scoring 레플리카가 해당 버전을
로딩하도록 한다. 사용자는 #86을 #85 구조에 맞춰 진행하도록 확정했다.
이전 버전도 S3/MinIO에서 재다운로드하고 메모리 로딩 후 임시 파일을 정리한다.
새 모델 로딩 실패 시 기존 모델은 유지한다. 로컬 영구 캐시는 새로 만들지 않는다.

## 구현과 요구사항 대응

| 요구사항 | 구현 |
|---|---|
| Pod별 브로드캐스트 | `ModelVersionConsumer`가 서버 생성 이름의 exclusive·auto-delete 큐를 `events.topic`의 `model.version.*`에 바인딩 |
| 큐 연결 후 초기 조회 | consume 등록까지 마친 다음 `ModelStartup` 시작. 조회 중 수신 메시지는 메모리에 보존 |
| 순서 역전·중복 | 이름별 최신 이벤트 보존, `ModelRegistry`에서 revision 비교. scoring이 받는 kind는 MODEL만이므로 다른 kind와 혼합하지 않음 |
| scoring 모델만 적용 | MODEL이며 `m2-`·`m1-` 이름인 항목만 전달. 다른 kind·모델 무시 |
| 로딩 완료 후 교체 | #85 스레드풀 로더 재사용. 기존 객체를 유지하다 성공 후 참조 교체 |
| 로딩 실패 | 기존 모델 유지·재시도. scope는 기존 모델과 최신 승인 범위의 교집합으로 제한. 한 모델 실패가 다른 이름의 업데이트를 막지 않음 |
| 형식 오류 | 봉투·data 검증 실패 시 본문 없는 경고 후 ACK, 재시도 없음 |
| 재연결 | 이전 session 정리 → 새 큐 바인딩 → snapshot 재조회. 중단 중 변경은 snapshot 및 Outbox 이벤트로 조정 |
| readiness | 최초 준비·재연결 조정 전 false. 빈 활성 목록은 준비 완료. 정상 기동 이후 교체 실패는 기존 모델 제공을 유지 |
| 로그 | 모델명·revision·큐명·예외 유형만 기록. 메시지 본문·artifact URI·자격 증명 미기록 |

API와 이벤트의 wire 계약은 변경하지 않는다. 기존 EventEnvelope·CoreClient·ModelRegistry를
재사용하고 실제 구현에 맞춰 architecture·class·sequence 문서와 색인을 갱신했다.
이벤트 스키마 변경 시 scoring CI가 실행되도록 workflow 경로 필터를 추가했다.

## 검증 범위

- 자동 테스트: 조회 중 이벤트·로딩 중 이벤트·낮은 revision·rollback 재로딩·실패 후 재시도·기존 모델 유지·다른 kind 무시·잘못된 메시지 ACK·schema 필드 일치·큐 바인딩 순서·재연결을 검사한다.
- 실제 통합: `scripts/verify_scoring_events.py`가 #85 검증 도구를 재사용하여 격리된 PostgreSQL·core·RabbitMQ·MinIO·scoring 2개를 실행한다.
- 실제 2.0 서술형·논술형 가중치는 Git 외부 tar에서 MinIO로 스트리밍한다. `2.1-check`는 **같은 2.0 artifact를 가리키는 교체 검증용 메타데이터**이며 새 모델의 품질·성능 검증이 아니다.
- core의 실제 등록·활성화·rollback API와 Outbox 이벤트를 사용한다. RabbitMQ 관리 API로 exclusive·auto-delete 큐 두 개와 바인딩을 확인한다.
- `/internal/versions`의 두 레플리카 revision을 비교하고, 파일 없는 교체 시 이전 버전 유지, 브로커 중단 중 활성화 후 재연결 복구, 임시 다운로드 정리를 검사한다.
- 테스트 자격 증명·Compose 파일·결과 JSON은 Git 밖 `../tmp/issue86-events-verified-20261029/`에 둔다. 테스트 전용 컨테이너·볼륨은 종료 시 정리한다.

## 실행 결과 (2026-10-29)

- 최종 scoring 전체 자동 테스트 **73개 통과**(17.24초). Ruff check·format 통과.
- 최신 develop 병합 후 공통 문서·계약 검사 **58개 통과**. 앞서 실행한 core 모델 레지스트리 계약 검사 5개도 통과했다.
- 실제 Compose 검증 통과: 두 exclusive 큐·바인딩, 두 서버의 모델 활성화,
  rollback 재다운로드, 파일 누락 시 기존 버전 유지, 브로커 중단 중 활성화 후 재연결 복구,
  두 서버의 임시 파일 정리. 최종 narrative revision은 두 서버 모두 6이었다.
- 원본 2.0 모델을 활용한 로컬 연동 확인이며 모델 가중치는 Git에 추가하지 않았다.
- 최종 결과: Git 외부 `../tmp/issue86-events-verified-20261029/results.json`,
  테스트 XML `../tmp/issue86-pytest-final-20261029.xml`.
- 중간 검증 1회는 재연결 복구 직후 임시 디렉터리가 남아 있어 즉시 정리 단언이 실패했다.
  검증기를 최대 60초 동안 정리 완료를 확인하도록 보완한 뒤 최종 실제 통합 실행을 모두 통과했다.
  임시 디렉터리를 강제로 지우거나 정리 검사를 생략하지 않았다.
- 최신 develop `c608f52` 병합 시 `.env.example`·`compose.minio.yaml`의 report와 scoring
  MinIO 설정이 같은 위치에 추가되어 충돌했다. 양쪽 서비스 설정을 모두 보존하여 해결했다.
  scoring 실행 코드의 develop 변경은 timeout 주석 정리뿐이며 모델 교체 동작은 동일하다.

## 후속 연결 검증

#86의 이벤트 처리와 활성 버전 조회를 검증한다. 이슈 완료 조건에 함께 적힌
**실제 `/internal/m2/scores` 응답의 버전 교체**는 해당 API를 만드는 #87에서 연결 검증해야 한다.
현재 모델 레지스트리 교체를 M2 API까지 완료한 것으로 표시하지 않는다.
실제 AWS·Kubernetes 배포·원격 GitHub CI는 이번 로컬 검증 범위가 아니다.
