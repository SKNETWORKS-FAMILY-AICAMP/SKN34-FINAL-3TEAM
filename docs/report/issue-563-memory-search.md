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
- #565 선택 연동 시험: 병합된 develop의 ai 서비스에서 EMBEDDING_PROVIDER=fake, INTERNAL_TOKEN=memory563-local-test로 서비스 실행. learning 테스트에 MEMORY_AI_URL을 지정하면 실제 HTTP→ai 라우터→임베딩 서비스→pgvector 저장→질문 검색을 실행한다. 환경 변수가 없으면 이 시험만 명시적으로 제외한다.

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

## 실제 외부 모델 추가 검증 (2026-11-12)

구현 커밋 `7f85fad5`와 병합된 #565 AI 서비스를 사용했다. 로컬 AI 서비스의 제공자를 OpenAI로 설정하고 `text-embedding-3-small`의 1536차원 벡터를 실제로 요청했다. 실제 학생 데이터 대신 합성 글만 전송했으며, 운영 DB와 AWS 서버는 사용하지 않았다.

- `MemorySearchTest`: 13건 통과, 실패·제외 0. 이 중 외부 연동 시험 1건은 실제 learning 클라이언트 → AI HTTP API(`purpose=MEMORY`) → OpenAI → pgvector READY 저장 → 질문 임베딩 → 해당 시도 검색까지 검증했다. 나머지 시험은 기존 DB·고정 벡터 검증이다.
- 외부 연동 1건의 임베딩·저장·질문 검색 소요 시간: 1,004ms. 브라우저 응답 시간이나 운영 부하 성능을 의미하지 않는다.
- 별도 의미 검색 점검: 합성 기록 12개(도서관·환경·친구·과학·수학·안전 각 2개), 관련 질문 8개와 무관 질문 2개. 실제 임베딩으로 문서 코사인 순위를 계산했다. 이 점검은 회차 묶음·권한을 포함하는 DB API 시험과 구분한다.
- 관련 질문의 예상 주제 문서가 1위인 경우: 7/8. 무관 질문은 2/2 모두 초기 기준값 0.35 미만이었다. 작은 합성 표본이므로 서비스 정확도로 일반화하지 않는다.
- 실패 예: “강에 사는 생물을 지키기 위해 한 일”은 하천 쓰레기 관련 문서를 찾지 못했고 최고 유사도도 0.269로 기준값 미만이었다. 기준값을 이 예시에 맞춰 임의로 낮추지 않았다.
- 문서 12개 일괄 임베딩 HTTP: 1,288.4ms. 질문 10개의 개별 임베딩 HTTP: 142.2~211.7ms. 전체 검색 응답 시간과 구분한다.
- 로컬 재현 증거: 실행 로그·JUnit XML·합성 질문별 순위 결과를 보관했다. API 키는 문서·커밋에 포함하지 않았다.

실제 외부 모델 연동은 가능하며 통과했다. 관련도 기준 최종 조정과 키워드 기준선 대비 개선 평가는 #568 대표 평가셋으로 별도 수행해야 한다. 이번 실행에서는 RabbitMQ 사용량 이벤트 전달을 검증하지 않았다.

## 남은 범위

- 실제 외부 임베딩 호출·DB 저장·검색은 아래 추가 검증에서 통과했다. 대표 평가셋 품질 검증·사용량 이벤트 전달·운영 환경 확인은 별도다.
- #568 평가셋에 따른 관련도 기준 최종 조정은 미완료다.
- #565 PR #580 병합 후 fake 제공자로 38건을 재검증했으며, 이후 실제 OpenAI 제공자로 아래 연동 검증을 추가했다.


## 이슈 원문 체크리스트 대조

아래 체크는 로컬 검증과 실제 외부 제공자 연동 검증 범위다. 운영 배포·대표 평가셋 품질 승인 완료를 뜻하지 않는다.

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
- [x] 학습 완료 뒤 주기 작업으로 `READY`가 되고 검색 결과에 나옴 — 합성 완료 기록·실제 ai 서비스·OpenAI 제공자까지 검증
- [x] 두 작업 인스턴스가 같은 행을 중복 임베딩하지 않음 — 두 스레드·두 DB 연결의 동시 선점으로 1건만 반환 확인
- [x] `ci-db-schema`·learning 시험·계약 검사 통과, 결과서에 쓸 적재 수·소요 시간 기록 — 로컬 동일 검사, 원격 CI 미실행

### 확인 필요
- [ ] 관련도 기준값(평가셋으로 조정, #568) — 구현용 0.35는 설정·문서에 확정했으나 평가셋 품질 조정은 별도
- [x] 주기·배치 크기·재시도 한도 기준안 — 1분·64행/요청당 8글·첫 시도 포함 5회
- [x] pgvector 매퍼 방식(형변환 vs 드라이버 의존성 승인) — MyBatis 형변환, 새 드라이버 없음
