# #370 Pod별 모델 로딩 보고

## 설계와 범위

최신 develop fb6b08a2에서 시작했다. 필수 선행 #366은 병합됐으며 #368 사전 검사 배포나 AWS 재가동은 필요하지 않다. 운영 AWS를 변경하지 않는다.

| 방식 | 검토 결과 |
| --- | --- |
| scoring → RabbitMQ 결과 이벤트 + heartbeat | 채택. 이미 사용하는 events.topic과 core 소비 구조를 재사용하고 각 프로세스를 식별한다. 발행 장애는 기존 로딩·추론을 막지 않으며 다음 전체 보고로 복구한다. |
| core → scoring Service 단일 조회 | Pod 하나만 확인하므로 전체 상태로 표현할 수 없다. |
| core → Kubernetes API로 Pod 열거·개별 조회 | 정확한 배포 수를 알 수 있지만 새로운 클러스터 권한과 서비스 탐색 결합이 필요해 이번 범위에서 제외한다. |

## 계약

- 이벤트 `model.loading.reported`, source `scoring-service`, schema v1. Pod명(기본 hostname), 프로세스별 UUID, 단조 증가 sequence, 전체 모델 상태를 보낸다.
- 성공·실패·진행 중에 target name/version/revision과 현재 메모리에 남은 버전/revision을 구분한다. 실패에는 예외 유형만 포함하고 원문·URI·자격 증명은 포함하지 않는다.
- 로딩 중 변경 신호와 30초 heartbeat로 발행한다. 발행은 2초 제한, 단일 태스크이며 실패하면 다음 전체 보고에서 회복한다. 새 로딩 실패 시 기존 모델 유지 동작은 변경하지 않는다.
- core `model_loading_report`(V36)에 프로세스별 최신 전체 상태를 저장한다. 같은 instance의 중복·역순 sequence와 역행 시각은 무시한다. 같은 Pod명은 가장 최근 보고 프로세스만 조회한다.
- `GET /api/v1/admin/model-loading`은 기존 SERVICE_OPS 권한을 요구한다. 상태는 승인·평가 JSONB에 저장하지 않는다.
- 120초 이상 보고가 없으면 stale로 표시하고 성공/실패 집계에서 제외한다. 24시간 지난 기록은 조회에서 제외하고 매시간 정리한다. 축소·비정상 종료·보고 통신 장애는 모두 보고 만료로 표현하며 죽은 Pod라고 단정하지 않는다.
- 화면 분모는 최근 보고된 Pod 수다. 전체 배포 replica 수는 모르므로 전체 배포 성공으로 표시하지 않는다. 아직 보고하지 않은 Pod가 존재할 수 있고 보고 0개는 미확인이다.
- 현재 활성 모델의 name/version/revision이 모두 일치할 때만 완료 수에 포함한다. 과거 버전 보고는 대기 상태로 표시한다. 모델 이외 PROMPT/RUBRIC에는 적용하지 않는다.

## 배포 순서

V36 migration → RabbitMQ definitions(새 core 큐·재시도·DLQ 바인딩) → core → scoring → web 순서로 반영한다. 기존 라우팅·모델 승인·활성화 계약은 유지한다. 새 공유 큐는 코드에서 선언하지 않는다. 추가 AWS IAM 권한이나 Kubernetes 조회 권한은 없다.

## 검증

- core: 로딩 상태·인증 4개, 실제 로컬 연동 1개, 기존 모델 HTTP 12개, 관리자 운영 25개로 총 42개 통과. bootJar 통과.
- scoring: 전체 201개 통과. Ruff check·format 통과. #368은 별도 브랜치이므로 해당 브랜치의 사전 검사 테스트 수와 다르다.
- web: 단위 244개, 브라우저 12개(데스크톱·태블릿·휴대폰), 타입 검사·린트·빌드 통과.
- 저장소 계약: 전체 194개 실행에서 큐 개수 1건이 실패해 새 큐 5개와 관리자 조회 allowlist를 반영했다. 해당 계약·새 이벤트·마이그레이션 8개 재검증 통과.
- DB: 격리 PostgreSQL에서 3개 DB 마이그레이션 적용·재적용, report 왕복, ERD 89개 테이블 대조, 무결성 음성 사례 105개, 서비스 역할 6개 분리 검증 통과. 검증용 컨테이너 중지.
- 실제 core HTTP 응답과 두 프로세스의 모델 보고 payload를 OpenAPI·이벤트 JSON Schema에 대조하여 통과.

### 로컬 2 replica 검증 범위

`ModelLoadingLocalIntegrationTest`는 서로 다른 scoring Python 프로세스 2개를 동시에 실행한다. 합성 로더를 제외한 운영 ModelRegistry·ModelLoadingReporter·EventPublisher → 실제 RabbitMQ → 운영 core consumer → 실제 PostgreSQL → SERVICE_OPS HTTP 조회까지 검증한다. 한쪽은 revision 2 완료, 다른 쪽은 ValueError로 실패하고 revision 1 모델을 유지한다. 실제 M2 가중치 다운로드·추론 및 Kubernetes Pod 기동 검증은 아니다.

이 HTTP 응답을 브라우저 테스트 입력으로 사용하여 2개 중 1개 로딩 완료, 실패 Pod·오류 유형·기존 모델 유지 표시, 3개 화면 크기의 가로 넘침 없음까지 확인했다. 브라우저와 실행 중인 core의 실시간 직접 연결 검증과 구분한다.

재현: scoring Python 의존성이 설치된 환경에서 `MODEL_LOADING_LOCAL=true`, `SCORING_TEST_PYTHON`에 scoring Python 실행 파일을 지정한 뒤 core `test --tests '*ModelLoadingLocalIntegrationTest'` 실행. 이어서 web에서 `MODEL_LOADING_LOCAL=true npm run test:models` 실행한다. 일반 CI 브라우저 테스트는 합성 응답을 사용한다.

## 이슈 원문 체크리스트

### 해야 할 일
- [x] 보고 방식 설계: scoring이 로딩 결과 이벤트를 발행하고 core가 모으는 안(추천)과 대안 비교
- [x] scoring: `ModelRegistry.load` 성공·실패 시 Pod 식별자와 함께 보고(실패 시 오류 유형만, 기존 모델 유지 표시)
- [x] core: Pod별 최신 로딩 상태 저장·조회 API
- [x] web: 버전 카드의 "로딩 확인" 단계에 Pod 수 대비 로딩 완료 수, 실패 Pod 표시
- [x] Pod 축소·재시작 시 오래된 기록 처리 규칙

### 완료 조건
- [x] 레플리카 2개 이상인 local 환경에서 한 Pod 로딩 실패 시 화면에 구분되어 보임을 확인
- [x] 관련 테스트 통과

### 유지할 원칙
- 로딩 성공을 품질 승인으로 표시하지 않음. 추론 확인은 자동 판정하지 않음

AWS는 재가동·배포하지 않았다. 기존 운영 이미지와 prod migration digest는 변경하지 않았다. 배포 시 V36이 포함된 migration 이미지를 별도로 반영해야 한다.
