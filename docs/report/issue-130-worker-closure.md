# #130 실제 report-worker 생성기 연결 완료 근거

## 처리 방향

기존 #56/PR #148의 구현을 재사용한다. 최신 develop 전수 점검(PR #172)도 B5를 해결로 판정했다. 새 생성기·별명 필드·API를 중복 구현하지 않는다.

| #130 항목 | 현재 구현·검증 |
|---|---|
| 기본 진입점 실제 생성기 | worker.run → build_pipeline → NamedGenerator → RenderingGenerator → NarrativeGenerator → RecordGenerator |
| #119 별명 공급 | CoreClient.lookup이 SYSTEM·학생 scope로 /internal/students/{id}/profile 조회. NamedGenerator가 display_name에 반영 |
| AI 서술 장애를 명확히 처리 | AI 503/빈 응답은 GENERATION_FAILED, 무료 성공으로 대체하지 않음. 숫자/인용 대조 실패만 기존 TEMPLATE 정책 |
| 서술 API 미구현 동안 정책 | 담당자와 기존에 확정한 API 장애 FAILED 유지. #64/PR #149가 병합돼 API 구현도 존재 |
| 무료·NO_RECORD 완료 | 기본 worker 직접 명령·실제 DB/브로커/학습 기록/MinIO에서 생성·파일 저장 확인 |
| pytest·Ruff | 최신 기준으로 다시 실행하고 아래 기록 |

표시 이름은 학생 개인정보가 있는 메시지 필드로 추가하지 않고 core 내부 조회로 공급한다. codec은 기존 이벤트 계약을 유지한다.

## 검증 범위

기존 scripts/verify_report_compose.py를 재사용한다. core·learning·기본 report worker·PostgreSQL·RabbitMQ·MinIO·파일 렌더링은 실제 구현, AI 응답은 이슈가 허용한 합성 대역이다. 실제 AI 모델 품질이나 관리자 버튼 전체를 검증했다고 표현하지 않는다.

## 실행 결과 (2026-10-30)

- 기준 develop `5f32ee6`: #172 전수 점검·#161 프론트 피드백 계약 포함. #132 report job guard도 보존했다.
- report pytest **278 passed**, 132.79초. Ruff check·format **86개 파일 통과**.
- 현재 core·learning을 JDK21로 bootJar 빌드하고 기본 worker 운영 이미지의 Compose 검증을 다시 실행했다.
- 실제 연동 **8개 시나리오 + 이벤트 스키마 검사 통과**: 유료/중복/개인정보/파일/scope, 무료, NO_RECORD, 삭제/없는 학생 실패, 대조 불일치 TEMPLATE, AI 503 FAILED, MinIO 장애 FAILED.
- 별명 조회·학습 기록·DB·브로커·저장·렌더링은 실제 구현이며 AI 응답만 합성 대역이다. 무료와 NO_RECORD에서 AI 호출 없이 COMPLETED를 확인했고, AI 장애는 실패로 유지했다.
- 제품 코드·API·이벤트·스키마 변경 없이 기존 구현으로 #130을 충족했다. 로컬 증거는 저장소 밖 `../tmp/issue130-tests-20261030.xml`, `../tmp/issue130-compose-20261030/results.json`에 있다. 검증 전용 자원 정리 완료.
- 최초 JAR 빌드 명령의 PowerShell 옵션 전달과 동시 Gradle 캐시 잠금 문제를 보완해 빌드를 순차 재실행했다. 제품 코드 변경으로 해결한 오류가 아니며 실패 실행은 성공 결과에 합산하지 않았다.

**판정: #130의 구현·완료 조건 충족. 이 문서 변경은 기존 완료 근거 정리이며 새 생성기를 만드는 작업이 아니다.** PR·GitHub 이슈는 직접 변경하지 않는다.

## 관련 근거

- [기존 worker 연결 검증](report-worker-integration.md)
- [리포트 전체 구현](report.md)
- [최신 전수 점검](audit.md) 3.2 B5

기존 #119 이슈가 열려 있는 것과 내부 API 구현·사용 가능 여부는 구분한다. 현재 기본 worker는 구현된 해당 API를 실제 호출한다.
