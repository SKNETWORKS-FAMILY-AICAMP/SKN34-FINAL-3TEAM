# #563 추억 검색 구현·검증

## 범위

학습 완료 기록을 검색 문서로 등록하고, 별도 주기 작업이 임베딩을 채운다. 학생 본인이 보유한 지난 회차만 검색한다. 외부 임베딩 품질 평가·운영 배포는 별도다. #559의 V19와 #484 V18을 유지하며 V20을 추가했다.

## 구현 결정

| 항목 | 값·근거 |
|---|---|
| 대상 | completed_at이 있는 THEME_DAY·THEME_REVIEW, EXTRA 제외 |
| 문서 | 테마 제목·장면 대화·미션 질문·최신 답변. 정답 키·clue 제외 |
| 등록 | 완료 트랜잭션에서 PENDING만 INSERT, attempt_id UK로 중복 방지 |
| 소급 | 주기 실행 시 기존 완료 시도를 INSERT SELECT ON CONFLICT DO NOTHING |
| 선점 | 트랜잭션 안에서 FOR UPDATE SKIP LOCKED + 조건부 UPDATE, 최대 64행 |
| 네트워크 | 트랜잭션 밖, 요청당 최대 8글. 계약 상한 64 이내 |
| 주기·리스 | 1분·600초. core 최대 64회×(연결 2초+읽기 4초), ai 최대 8회×(연결 2초+읽기 20초)=560초보다 긴 리스 |
| 재시도 | 선점 때 횟수 증가, 첫 시도 포함 5회. 실패는 FAILED, 한도 미만만 재선점 |
| 고착 복구 | 만료 PROCESSING은 PENDING, 5회에 닿으면 FAILED. 이전 리스의 결과는 저장 불가 |
| 벡터 | 1536차원·유한·영벡터 아님 검증, 응답 모델·차원·건수 검증 |
| 매퍼 | 벡터 저장·코사인 검색 MyBatis, 문자열→vector 형변환. 새 드라이버 의존성 없음 |
| 검색 | READY·본인·보유 액자·지난 주·같은 임베딩 모델 조건. 회차 최고 유사도로 상위 3개 |
| 기준값 | 0.35 초기값, app.memory.minimum-similarity로 변경. #568의 품질 평가로 조정할 값 |
| 결과 | RESULTS / NO_RESULTS / NO_RECORDS. 프로필·임베딩 장애 503 AI_UNAVAILABLE |
| 비교 기준선 | 같은 접근 범위의 최신 answer.plain_text ILIKE, %, _, ! 이스케이프 |
| 개인정보 | 프로필 닉네임·UUID를 전송 전 마스킹. 프로필 실패 시 전송 금지. 원문·질문 로그 없음 |
| 삭제 | 같은 학생 삭제 트랜잭션에서 attempt보다 먼저 삭제, FK NO ACTION |

## 설정·재현

기본 MEMORY_EMBEDDING_ENABLED=false다. true로 켜면 1분 뒤 등록·복구·선점 작업이 시작한다. false로 되돌리면 주기 실행만 중지하고 이미 저장된 문서를 지우지 않는다. 자동 소급은 멱등이며 실패 5회에 닿은 문서는 자동으로 되살리지 않는다.

- learning: JDK 21에서 `bash gradlew test bootJar -Pkotlin.incremental=false`
- 계약: `python -O -m unittest discover -s scripts/tests`
- DB: 분리된 빈 PostgreSQL에 `scripts/check_db_migrations.py`. 기존 DB에서 실행하지 않는다.
- #565 선택 연동 시험: 해당 ai 브랜치에서 EMBEDDING_PROVIDER=fake, INTERNAL_TOKEN=memory563-local-test로 서비스 실행. learning 테스트에 MEMORY_AI_URL을 지정하면 실제 HTTP→ai 라우터→임베딩 서비스→pgvector 저장→질문 검색을 실행한다. 환경 변수가 없으면 이 시험만 명시적으로 제외한다.

## 검증 결과

- 기준 develop: `a4795409` (#559 PR #571, #566 PR #572, #565 PR #580 포함). learning 코드는 직전 전체 검증 이후 변경 없음.
- learning `test bootJar`: 535건, 실패 0·제외 0. 최신 develop AI 서버로 추억 기능 38건 재검증도 통과.
- scripts/tests: 310건, 실패 0·기존 조건부 제외 1(원본 HWP 폴더 미지정).
- ai 임베딩·추억 설명: 62건 통과.
- MVC 실제 응답 JSON을 core·learning OpenAPI `MemorySearchResult` 양쪽과 대조: 통과.
- 전체 마이그레이션: core 61테이블/524컬럼, learning 39/350, report 8/66. 158건 부정 제약, 108 CHECK 값 집합, ERD 인덱스 57개 확인. 반복 적용·report downgrade/upgrade·DB 역할 6개 격리 통과. 46.1초.
- 합성 4문서 등록→READY 저장→검색: 28ms. 네 회차에서 상위 3회차 반환 확인.
- #565 실제 HTTP 라우터·서비스 + fake-bigram-v1: 합성 1문서 임베딩→DB 저장→질문 임베딩→검색 528ms. 1536차원, purpose=MEMORY, 원하는 시도 반환 확인.
- 실제 커밋하는 동시성 시험은 별도 Testcontainers DB로 분리했다. 다른 테스트 데이터와 섞이지 않는다.

가짜 벡터의 시간·검색 일치는 외부 임베딩 모델의 속도·정확도를 의미하지 않는다. 원격 CI는 푸시하지 않아 실행하지 않았다. 위 항목은 로컬 CI 상당 검증이다.

## 남은 범위

- 실제 외부 임베딩 제공자 호출·품질·사용량 발행과 운영 환경 확인은 미완료다.
- #568 평가셋에 따른 관련도 기준 최종 조정은 미완료다.
- #565 PR #580 병합 후 develop의 ai 서비스를 직접 실행해 추억 기능 38건을 재검증했고 모두 통과했다. 외부 제공자를 fake로 대체한 범위는 그대로다.


## 이슈 원문 체크리스트 대조

아래 체크는 위 로컬 검증 범위다. 외부 제공자·운영 검증 완료를 뜻하지 않는다.

### 해야 할 일
- [x] `memory_search_doc` 마이그레이션(status CHECK `PENDING|PROCESSING|READY|FAILED`, `READY`면 임베딩 칸 NOT NULL CHECK)
- [x] 학습 완료 트랜잭션에서 `PENDING` 등록(`EXTRA` 제외, `attempt_id` UK)
- [x] `EmbeddingClient`(서킷·타임아웃, `purpose=MEMORY`)
- [x] 주기 작업: 리스 만료 복구 → 최대 64행 선점 → 임베딩 → 리스 일치 행만 `READY`/`FAILED`(retry_count, 한도 기준안 5)
- [x] 소급: 기존 완료 시도 `PENDING` 일괄 생성
- [x] `POST /internal/students/{studentId}/memories/search`: 질문 임베딩 → `READY`·본인·보유 `theme_frame` 회차·지난 주 필터 → 거리 정렬 → 회차 상위 3, `RESULTS|NO_RESULTS|NO_RECORDS`, 임베딩 장애 503 `AI_UNAVAILABLE`
- [x] 키워드 기준선(`answer.plain_text` ILIKE) 함수(#568 비교용)
- [x] 삭제 순서에 `memory_search_doc`
- [x] 시험: 레플리카 동시 선점, 리스 만료, 재시도 한도, 다른 학생·진행 주·EXTRA 미포함, 삭제

### 완료 조건
- [x] 학습 완료 뒤 주기 작업으로 `READY`가 되고 검색 결과에 나옴 — 합성 완료 기록·실제 ai 서비스·fake 제공자
- [x] 두 작업 인스턴스가 같은 행을 중복 임베딩하지 않음 — 두 스레드·두 DB 연결의 동시 선점으로 1건만 반환 확인
- [x] `ci-db-schema`·learning 시험·계약 검사 통과, 결과서에 쓸 적재 수·소요 시간 기록 — 로컬 동일 검사, 원격 CI 미실행

### 확인 필요
- [ ] 관련도 기준값(평가셋으로 조정, #568) — 구현용 0.35는 설정·문서에 확정했으나 평가셋 품질 조정은 별도
- [x] 주기·배치 크기·재시도 한도 기준안 — 1분·64행/요청당 8글·첫 시도 포함 5회
- [x] pgvector 매퍼 방식(형변환 vs 드라이버 의존성 승인) — MyBatis 형변환, 새 드라이버 없음
