# #87 M2 채점 API 구현·검증

## 목적과 기준

서술형·논술형 답변을 실제 M2 모델로 채점해 #69 AI 판정에서 교차 확인할 점수·모델 버전을 제공한다.
로컬 `feature/scoring-m2-scores`는 #85·#86 구현을 이어받고 develop `c44ace8`을 병합했다.
GitHub PR·댓글·이슈 체크박스는 변경하지 않는다. 모델·합성 실행 결과는 저장소 밖에 보관한다.

2026-10-29 사용자가 전달한 담당자 답변을 구현 기준으로 삼는다.

- 태윤: 관리자 입력 → `rubric_version.keywords` 배열 → learning `question/keywords` → AI → scoring `prompt/text/grade/inputType/keywords`. 핵심어는 서술형만 사용, 없으면 비활성. 결과 예시 작성 승인. 실제 장애는 503·판정 처리 실패. M1 미학습으로 #88 계약만 진행.
- 수빈: 실제 2.0은 `score_cuts.json` 사용, 소수 원점수도 보존, 서술형 content_3도 모델 점수 사용. README의 규칙 점수 대체는 구형 설명이다.
- 이슈의 반올림·범위 자르기 문구는 2.0 컷 변환으로 대체한다. 컷이 없거나 손상된 모델을 반올림으로 조용히 대체하지 않는다.

## 코드·계약

- [API 4.3](../design/api-spec.md#43-scoring-service-호출-ai), [OpenAPI](../../contracts/openapi/scoring-service.yaml).
- M2Service는 기존 ModelRegistry·LoadedModel을 재사용한다. 승인 scope는 `judgment/grade-5/narrative`와 같은 정확 일치 값이다. 문항 단위 승인은 요청에 문항 ID가 없어 현재 구현 범위 밖이며, 이를 학년 승인으로 임의 확대하지 않는다.
- 초5·6만 지원한다. 모델/승인 범위 밖·핵심어 없는 서술형은 active:false. 논술형은 핵심어를 넣지 않는다.
- 학습 메타데이터의 max_length=512, 회귀 head, dataset, 핵심어 설정을 검사한다. 첫 문장에 학년·지시문·서술형 핵심어를 구성하고 글은 두 번째 문장으로 토큰화한다. 첫 문장을 임의로 잘라 의미를 바꾸지 않는다.
- `bisect_right(cuts, raw)+1`은 학습 `numpy.digitize(raw, cuts)+1`과 같은 경계 처리다. hol 1~4, 8항목 1~5. rawScores는 유한 원점수 그대로 반환한다. 두 유형의 content_1~3 의미가 다르므로 inputType을 함께 반환하고 항목을 동일 의미로 합산하지 않는다.
- CPU 작업은 run_in_threadpool, 서비스 단위 1개 동시 추론, 대기 최대 1초 이후 503. 실행 중 모델 교체 시 현재 요청은 캡처한 모델을 사용하고 다음 요청은 새 버전을 사용한다.
- 응답 모델은 name/version/revision. AI는 model.name@version을 versions.model에 연결하는 후속이 필요하다.
- 오류는 ApiError와 Problem Details 공통 처리 사용. 추론·설정 오류 로그에는 예외 유형만 기록한다. 브로커 발행은 제한된 백그라운드 태스크(최대128, 1초 제한), 실패해도 채점 응답은 성공한다. 사용량은 원문·학생 정보 없이 service=scoring, callType=M2, 토큰 null, 지연·성공 여부를 보낸다.
- API 요청 길이 제한은 문서와 Pydantic에서 동일하게 정의했다. `X-Student-Scope`는 모델 승인 scope가 아니며 요청에 학생 ID가 없어 별도 학생 조회를 수행하지 않는다.

## #69 전달용 응답 예시

아래 점수는 **형식 설명용 합성 예시**이며 실제 모델 출력이 아니다.

```json
{
  "active": true,
  "inputType": "NARRATIVE",
  "scores": {"hol": 3,"task_1": 3,"content_1": 3,"content_2": 3,"content_3": 3,"organization_1": 3,"organization_2": 3,"expression_1": 3,"expression_2": 3},
  "rawScores": {"hol": 3.0,"task_1": 3.3,"content_1": 3.4,"content_2": 3.0,"content_3": 3.0,"organization_1": 3.3,"organization_2": 3.4,"expression_1": 3.5,"expression_2": 3.5},
  "model": {"name": "m2-klue-narrative","version": "2.0","revision": 1}
}
```

비활성은 `{"active":false}`만 반환한다. 서비스는 점수를 DB에 저장하지 않는다. rawScores를 judgment.model_scores에 보존하는 처리는 #69·learning 연결 시 반영해야 한다.

## 이슈 요구 조건 대조

| 요청/완료 조건 | 구현·검증 근거 |
|---|---|
| 모델 선택·미활성·학년·scope | M2Service와 대역 API 테스트. scope 접두사·와일드카드 확장 없음 |
| 학습과 같은 입력·점수 변환 | train_info·score_cuts, pair only_second, 9개 항목 경계·극단값 테스트. 실제 2.0은 반올림 대신 승인된 컷 적용 |
| 이벤트 루프 차단 금지 | run_in_threadpool, 추론 중 모델 교체·이벤트 루프 진행 테스트 |
| name/version 응답 | 모델 snapshot을 응답 identity에 사용. 추론 도중 교체 시 기존 요청의 버전 보존 |
| 사용량·원문 로그 금지 | 공유 봉투/data 스키마 테스트, 성공·실패·브로커 단절 검증 |
| 401·400 Problem | HTTP 테스트 및 OpenAPI와 실제 스키마 대조 |
| CPU 지연·35초 예산 | 아래 실제 모델 검증 기록. AI·learning 전체 35초 E2E와 M2 단독 측정은 구분 |
| Ruff·pytest | 최종 실행 결과를 아래 기록 |

## 실제 모델 검증

`scripts/verify_scoring_m2.py`는 #85 검증 도구를 재사용한다. 실제 core 등록·활성화, PostgreSQL, RabbitMQ, MinIO, scoring 운영 이미지를 격리 Compose 프로젝트로 실행한다. 모델은 외부 tar에서 MinIO로만 올린다. 공유 모델 품질 승인이나 운영 S3 배포가 아니다.

```powershell
python -X utf8 scripts/verify_scoring_m2.py --archive C:/Users/playdata2/Desktop/m2_models_2.0.tar --core-root C:/Users/playdata2/Desktop/final/SKN34-FINAL-3TEAM --output C:/Users/playdata2/Desktop/final/tmp/issue87-real-20261029
```

합성 글 200·650·1200자, 유형별 워밍업3회+측정30회. 학습 latency.py의 글자 길이·반복·백분위 방식을 사용하되 HTTP·점수 변환까지 포함한다. 최종 실행은 아래 항목에 통과했다. 실제 AI Hub 학생 글은 사용하지 않았다.


### 2026-10-29 최종 결과

- scoring 전체 pytest **104 passed**, 41.96초. Ruff check/format 통과(서비스37파일). 공통 계약·스키마 unittest **58개 통과**. 수정 문서 상대 링크63개 유효, 충돌 표식·git diff --check 이상 없음.
- 실제 core 최신 소스 bootJar 빌드 성공(JDK21). scoring 운영 이미지 `local/scoring87:20261029` 빌드 성공.
- 모델 없음 readiness/401, 등록 후 파일 없음 DOWN→MinIO 업로드 후 UP, 실제 두 모델 versions 2.0 확인.
- 실제 HTTP 요청의 401/400, 초3·4/미승인 초6/핵심어 없는 서술형 inactive 통과. 6학년 승인된 모델의 활성 응답은 대역 단위 테스트에서 검증했다.
- 유형별 3개 길이 × (워밍업3+측정30) = **198회 실제 채점**. 모든 응답의 scores/rawScores/model을 런타임 OpenAPI로 검사하고, 점수9개 모두 해당 모델 컷과 대조했다.
- 실제 core 활성화 이벤트 → **2.1-check 응답**, 실제 rollback → **2.0 응답** 확인. 2.1-check는 같은 2.0 가중치로 메타데이터 교체를 검증한 것으로 새 학습 모델이 아니다.
- 실제 RabbitMQ 관찰 큐에서 **사용량 이벤트200건** 확인. 공유 봉투/data JSON Schema, M2/scoring, 토큰 null, 원문 비포함 확인. core의 DB 저장 행 수를 별도로 검사한 것은 아니다.
- RabbitMQ 중단 후 readiness DOWN 상태에서도 이미 로딩된 모델의 채점 HTTP200 확인(best-effort). 추론 장애503·실패 사용량은 대역 테스트로 검증했다.
- 최초 시도는 RabbitMQ4.3의 비영속·비독점 큐 제한으로 **검증 큐 생성**에서 중단됐다. 큐를 durable로 수정한 뒤 전체 시나리오를 재실행해 통과했다. 첫 실패 실행은 성공 건수에 합산하지 않는다.
- 전용 Compose 컨테이너·네트워크·볼륨 정리. 기존 사용자 프로젝트·데이터·S3는 변경하지 않았다. 모델 파일은 Git에 추가하지 않았다.

CPU x86_64, PyTorch2.14.1+cpu, OMP/MKL4스레드. 아래는 워밍업3회를 제외한 **HTTP 포함** 지연(ms)이다.

| 유형 | 글자 수 | 중앙값 | p95 | 최대 |
|---|---:|---:|---:|---:|
| NARRATIVE | 200 | 153.98 | 246.52 | 315.53 |
| NARRATIVE | 650 | 456.33 | 691.67 | 1138.87 |
| NARRATIVE | 1200 | 665.5 | 832.19 | 1682.59 |
| ESSAY | 200 | 152.99 | 227.47 | 307.95 |
| ESSAY | 650 | 407.4 | 504.63 | 725.56 |
| ESSAY | 1200 | 653.11 | 754.83 | 789.08 |

첫 서술형 준비 요청의 사용량 latencyMs는8400ms였다. 위 표의1.68초 최대값에 초기 준비 시간을 포함했다고 해석하지 않는다. 전체 HTTP 검증은35초 클라이언트 제한 안에 성공했지만, AI LLM 호출·learning 왕복을 더한 **전체35초 E2E는 미검증**이다. 배포 CPU·동시성에 따라 다시 측정해야 한다.

결과: 저장소 밖 `C:/Users/playdata2/Desktop/final/tmp/issue87-real-final-20261029/results.json`, `issue87-pytest-final.xml`.

**판정:** #87 scoring 구현·대역/실제 모델 API 검증은 완료. 이슈의 반올림 항목은 승인된2.0 컷 정책으로 대체 충족했다. 전체 AI 판정35초와 learning→AI 입력·원점수 저장은 담당 서비스 연결 후 확인할 미완료 항목이다. GitHub 체크박스를 전부 체크하거나 이슈를 종료하지 않았다.

## 남은 다른 서비스 작업

1. learning/DB·관리자 입력: keywords 저장 컬럼·관리 화면/API·question/keywords 전달. 최신 develop에는 아직 없다. 해당 서비스 담당 작업으로 구분하며 #87에서 타 서비스나 마이그레이션을 임의 추가하지 않는다.
2. #69 AI: 새 입력 전달, scores/rawScores/model 읽기, versions.model 및 model_scores 보존 연결, 503·시간 초과 시 처리 실패. 응답 예시는 로컬 문서에만 준비했고 전송하지 않았다.
3. 실제 learning→AI→scoring 전체 35초 예산·판정 교차 확인은 위 변경 이후 검증한다. M2 단독 통과로 전체 연동 완료를 주장하지 않는다.
4. #88은 다음 작업이다. 이번에 M1 라우터나 가짜 수학 점수는 추가하지 않는다.


## 최신 #85·#86 통합 후 최종 재검증

2026-10-29 develop `c364ed4` + #85 최종 `30ec760` + #86 최종 `c8a538c`를 모두 포함했다. #86 이전 코드를 별도로 덮어쓰지 않았다.

- scoring 전체 104개 통과(86.17초). 공통 74개·하위 검사 34개 통과(36.98초), Ruff·포맷·문서 링크 69개 검사 통과.
- 실제 core·MinIO·RabbitMQ·scoring 두 서버와 제공된 M2 2.0 모델을 사용했다. 원본 모델 파일·테스트 자격 증명은 Git 밖에 보존했다.
- 서술형/논술형 각각 200·650·1200자, 각 3회 준비 + 30회 HTTP 측정. 총 198개 기본 채점에서 응답 스키마·컷 변환·원점수를 확인했다.
- **#86에서 이관한 항목 통과:** 두 레플리카 각각 실제 M2 HTTP 응답이 활성화 후 2.1-check/revision 2, 롤백 후 2.0/revision 3을 반환했다. 2.1-check는 같은 2.0 가중치의 검증용 메타데이터다.
- 실제 RabbitMQ 사용량 이벤트의 스키마·토큰 null·원문 제외 확인. 브로커 중단 후에도 이미 로딩된 모델의 채점 응답 200 확인.
- 모델 품질·전체 learning→AI 판정 35초는 이 검증으로 완료 처리하지 않는다. #69 입력·저장·판정 연결은 후속이다.
- 결과: 저장소 밖 `tmp/issue87-release-real/results.json`, 테스트 `tmp/issue87-release-tests.xml`. 전용 Compose 자원 정리 완료.

이번 측정 최대 HTTP 지연은 1483.17ms, 스키마 대조한 실제 사용량 이벤트는 202개다. 전체 예산 검증과 구분한다.
