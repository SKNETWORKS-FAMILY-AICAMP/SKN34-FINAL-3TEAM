# #186 CD 배포 승인·이력과 이전 버전 복구

문서 버전: v1.1.0 (2026-11-02). develop `4410007` 기준, 실행 없는 준비 도구·CI·인계 자료. 현재 #186 담당자는 `20220348-kim`이며 이 브랜치는 부분 작업 인계용이다.

## 확정 정책

사용자가 전달한 담당자 답변을 기준으로 한다.

- 이전 승인 앱이 현재 DB 스키마·데이터와 호환될 때만 새 승인을 받아 이미지 버전을 복귀한다.
- 비호환 및 미확인은 모두 복귀 차단이다. DB 버전 번호만으로 호환성을 판정하지 않는다.
- API·이벤트 계약, 진행 중 학습·결제 작업 영향과 검증 근거를 함께 기록한다.
- DB 자동 downgrade 및 백업 자동 복원은 구현하지 않는다.
- 비호환은 수정 버전 배포 또는 데이터 복구 등 별도 계획을 작성하고 승인받는다.
- 운영 승인자는 미정이다. 담당자를 추정하여 지정하거나 승인 없이 실행하지 않는다.

## 이번 구현

- `scripts/cd_release.py`: 변경 서비스의 불변 이미지 digest, 전체 Git SHA, 대상 버전·사유, 여섯 호환성 검토 항목, 이전 승인 기록의 누락을 검증한다. UTC 시각·계획 해시·차단 사유를 JSON으로 남긴다.
- `infrastructure/cd/policy.json`: 승인자 공란, 실행 비활성, Environment 보호 설정·인프라 준비 미확인으로 둔다.
- `scripts/tests/test_cd_release.py`: 호환 계획, 비호환·미확인·근거 누락, 승인 기록 불일치, DB 변경 명령 거부, 이미지 digest·레지스트리 검사, 입력의 승인 위조 방어를 검증한다.
- `.github/workflows/cd-candidate.yml`: 기존 `_spring.yml`, `_python.yml`, `_web.yml`을 재사용하는 후보 검사. 이 준비 파일·도구·정책 변경 PR과 수동 실행만 대상으로 한다. 서비스 소스 변경은 기존 서비스별 CI 경로 필터를 유지한다. 배포 시점 전체 후보 검사는 별도로 수행한다.

**계획 입력의 `compatible`이나 이전 승인 기록 문자열은 사람이 작성한 선언이다. 실제 호환성 또는 GitHub 승인 완료를 증명하지 않는다.** 이 도구의 `valid=true`는 필수 입력 형식이 갖춰졌다는 의미뿐이다. `executable`은 항상 false이며, policy 값을 바꿔도 배포되지 않는다. 실제 GitHub 승인·환경 보호 조회·검증 증거 대조 실행기는 후속 연결 대상이다.

## 선행 연결과 구현 순서

1. #171은 병합·종료되었다. 아래 실제 chart 연결표를 사용한다. prod values는 #185에서 제공될 때 연결하며 없는 운영 구조를 임의 생성하지 않는다.
2. #185 ECR·OIDC IAM·Argo CD prod 환경·시연 URL이 제공되면 기존 테스트 통과 SHA의 이미지를 빌드·푸시하고 digest를 기록한다. 로컬 K8s 이미지는 GHCR을 사용한다. 비밀 키를 JSON·문서에 적지 않는다.
3. GitHub Environment의 실제 필수 승인자·허용 배포 ref·보호 설정을 확인한다. 승인 게이트 **뒤에서** GitOps 변경을 수행해야 Argo CD가 승인 전에 동기화하지 않는다. 승인자가 없는 Environment 자동 생성에 의존하지 않는다.
4. 배포 계획은 대상 SHA·이미지 digest·현재 배포 버전·DB 상태·증거에 묶어 승인한다. 실행 직전 현재 상태가 달라졌다면 재검토한다. 환경 단위 직렬화로 배포/복귀의 경합을 막는다.
5. 배포 이력에 수행자·승인 근거·UTC 시각·소스 SHA·전후 이미지·GitOps 커밋·Argo 동기화 결과·기능 확인 결과를 남긴다. 현재 로컬 계획 JSON은 이 실제 배포 이력을 대체하지 않는다.
6. 실제 시연 URL에서 로그인·학습 제출·리포트 조회를 확인한다. health 응답만으로 완료 처리하지 않는다. 합성 계정·토스 테스트 거래를 사용하고 원문·토큰은 증거에 남기지 않는다.
7. 승인된 이전 버전 복귀, 비호환 차단, 미확인 차단을 실행 환경에서 검증한다. DB 복구가 필요하면 일반 롤백과 분리된 승인 계획으로 진행한다.

## DB 호환성 검토 시 반드시 포함할 기존 제약

- #131 `20261030_04`: 기존 report-worker 중지 → migration → 새 worker 순서. 이전 worker와 새 NOT NULL 카운터 스키마의 혼합 실행 미지원. downgrade 시 실패·격리·수동 재처리 메타데이터가 사라진다.
- report 삭제 guard 제거는 삭제된 학생의 재생성 차단을 잃을 수 있어 무조건 롤백 금지.
- core·learning 앱 자동 migration은 꺼져 있다. 운영 DB 초기화·Flyway 이력 수정으로 버전을 맞추지 않는다.
- 기존 모델 버전 rollback 검증은 앱 배포 rollback 검증을 대신하지 않는다.

## 완료 조건 추적

| #186 요구사항 | 현재 상태 |
|---|---|
| 서비스별 이미지 빌드·푸시 | 기존 빌드 CI 재사용 준비, GHCR/ECR 실제 푸시 미구현·미실행 |
| GitOps 태그 갱신 → Argo CD | #171 구조 확인 완료, 실제 파일 갱신·승인·동기화는 미구현 |
| 운영 승인 게이트·배포 이력 | 정책·계획 기록 준비, 실제 승인자·보호 설정·배포 기록 미완료 |
| 배포 후 로그인·제출·조회 | 미실행 |
| 롤백 절차·호환성 기준 | 정책 문서화·계획 검증 구현, 실행기 미연결 |
| 정상 롤백·차단 리허설 | 합성 계획 단위 테스트만, 실제 환경 리허설 미실행 |

#186의 승인→배포→기능 확인 1회 및 롤백 리허설 완료 조건은 아직 충족하지 않는다. 사용자 요청으로 부분 작업 브랜치만 푸시한다. PR 생성·이슈 종료·레지스트리 업로드·실제 배포·DB 변경은 수행하지 않는다.

## 로컬 검증 기록 (2026-10-30)

- 기준: develop `d651aa1`, 작업 브랜치 `feature/cd-approval-rollback`.
- 저장소 계약·검증 테스트 94개 통과(기존 83개 + 이번 계획 검증 11개). 실제 배포 테스트가 아니다.
- CLI를 별도 Python 프로세스로 실행해 UTC 시각·계획 해시·실행 차단 기록 생성 확인.
- YAML 파싱·기존 reusable workflow 참조 경로·read-only 권한 확인. GitHub Actions 실행 및 actionlint 검증은 아직 수행하지 않았다.
- Windows sandbox의 기본 임시 폴더 권한 오류가 있어 테스트 실행에만 TMP/TEMP를 쓰기 가능한 작업 폴더로 지정한 뒤 재실행했다. 제품 코드의 테스트 생략은 추가하지 않았다.
- 재현: `python -m unittest discover -s scripts/tests -v`. Python 3.12 및 기존 계약 테스트 의존성 필요. Windows 임시 폴더 오류 시 쓰기 가능한 TMP/TEMP를 지정한다.


## #171 실제 연결 구조와 #185 인계 항목

| 대상 | 확인한 저장소 계약 | 후속 실행기에서 할 일 |
|---|---|---|
| 앱 이미지 | `infrastructure/gitops/charts/app-service`: `image.repository` + `image.digest` 또는 `image.tag` | GHCR/ECR에 게시한 실제 digest로 연결 |
| report 공유 이미지 | `environments/local/report-api.yaml`, `report-worker.yaml` 모두 report-service 이미지 | 두 Deployment를 같은 릴리스 digest로 함께 갱신. worker는 `python -m app.worker` |
| core·learning migration | `infrastructure/gitops/migrations/{core,learning}.Dockerfile` 및 chart `migration.image`, `migration.revision` | 앱 SHA와 대응하는 migration 이미지 확인. 이전 앱 복귀 때 migration Job을 함께 되돌리거나 DB downgrade하지 않음 |
| report migration | chart의 PreSync migration Job, Alembic | #131 worker 정지/순차 배포 제약 검토. 같은 report 이미지에 포함된 migration 경로 확인 |
| Argo CD | `infrastructure/gitops/argocd/local/`, local 서비스별 values | 승인 이후 GitOps 커밋, 실제 동기화/상태 기록. 현재 파일은 변경하지 않음 |
| 웹 | Vite 정적 빌드, 운영 S3/CloudFront는 #185 범위 | 이번 5개 backend 이미지 목록과 구분하여 웹 배포·복구 정책 연결 |
| prod | 저장소에 prod values·EKS 구성 없음, #185 OPEN | OIDC role·ECR 저장소·대상 환경·URL·Secret 공급 및 실제 준비 상태 확인 |

승인자와 GitHub Environment 보호 설정이 확정되기 전에는 실행 게이트를 연결하지 않는다. 실행 가능한 배포 워크플로를 미리 켜거나 AWS 리소스를 생성하지 않는다.

## 계획 예시와 재현

`infrastructure/cd/plan.example.json`은 **합성 입력**이다. SHA/digest/릴리스는 실제 아티팩트가 아니며 호환성은 unknown, 승인 근거는 공란이다. 실제 계획 작성 시 검증 근거를 채우되 선언만으로 실행 승인이 성립하지 않는다.

```sh
python -m unittest discover -s scripts/tests -p test_cd_release.py -v
python scripts/cd_release.py --plan infrastructure/cd/plan.example.json --policy infrastructure/cd/policy.json --output /tmp/cd-plan-record.json
```

CLI 종료 코드 0은 JSON 계획의 형식 유효성만 뜻한다. 호환 여부는 `blocks`를 읽어야 하며 `executable`은 항상 false다. 입력 오류는 코드 2와 차단 기록을 남긴다. 출력과 입력 경로가 같으면 입력을 덮어쓰지 않고 거부한다. 기록에는 계획·정책 SHA-256, UTC 시각과 차단 사유가 포함되며 수행자·실제 승인·배포 이력을 대신하지 않는다.

`cd-candidate.yml`은 해당 브랜치의 준비 파일 push, 준비 파일 변경 PR, 수동 실행에서 검사한다. 기존 `_spring.yml`·`_python.yml`·`_web.yml`을 재사용하고 합성 계획 차단 기록을 7일 artifact로 보관한다. `contents: read`이며 packages/id-token 쓰기 권한이나 deploy 명령은 없다.


## 최신 검증 기록 (2026-11-02)

- 기준 `4410007`, 브랜치 `feature/cd-release-preparation`. #209 병합을 포함한 최신 develop을 반영했다.
- `python -O -m unittest discover -s scripts/tests -q`: **107개 통과**(기존 계약 검사 94 + CD 계획 검사 13), 실패·생략 없음.
- 변경 Python Ruff check/format 및 `git diff --check` 통과.
- workflow YAML 파싱, 기존 재사용 workflow 입력 이름, policy 선행 의존성, contents 읽기 전용 권한 대조 통과. actionlint 및 실제 원격 Actions 전체 실행 결과는 이번 로컬 검증에 포함하지 않는다.
- 예시 CLI 실행은 valid=true, executable=false, 비호환/미확인·근거 누락·승인 미연결 차단 사유를 기록했다. JSON 형식 오류와 JSON 배열/null 입력도 코드 2로 차단 기록을 남기는 테스트를 통과했다.
- 최초 Windows sandbox 임시 폴더 권한으로 CLI 테스트가 실패했으나 정상 권한에서 전체 재실행해 통과했다. 테스트를 생략하지 않았다.
- 실제 이미지 build/push, GitHub Environment 승인, GitOps 커밋, Argo CD sync, 운영 DB 변경, 실제 로그인·학습·리포트 동작 및 롤백 리허설은 실행하지 않았다. #186 원격 체크박스와 종료 상태는 변경하지 않는다.
