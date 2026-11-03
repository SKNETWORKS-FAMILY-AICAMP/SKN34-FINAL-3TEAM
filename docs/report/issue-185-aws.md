# AWS 데모 배포 설정과 설계 차이 (#185)

기준: 2026-11-03, 계정 347161580747 / ap-northeast-2. 최초 작업은 **기존 AWS 구성을 읽어 저장소에 보존하고 설계 누락을 점검**했다. 이후 관측 배포·Discord 연결·demo 표시 보정까지 진행했으며 각 절에 실제 수행 범위를 기록했다. 최초 점검 절의 미배포 표기는 해당 시점에만 적용된다.

## 저장 위치

- [prod Helm values·Secret 참조·정책](../../infrastructure/gitops/environments/prod/README.md)
- [EKS 관측 인벤토리·gp3](../../infrastructure/eks/README.md)
- [CloudFront·ALB redacted 설정·RDS/S3 인벤토리](../../infrastructure/aws/README.md)

수집한 values는 현재 배포 상태를 보존한다. 전체 AWS를 새 계정에서 만들 수 있는 완성된 IaC가 아니다. 비밀 값·Kubernetes Secret data·Helm release Secret·CloudFront origin header 원문은 기록하지 않았다.

## 설계 대비 점검

| 항목 | 현재 근거 | 차이·남은 작업 |
|---|---|---|
| EKS | 1.35, Ready 노드 2대 | eksctl 생성 설정·리소스 관리 책임 문서화 미완료 |
| 노드그룹 | application 1개, t3.medium ON_DEMAND, min=desired=max=2 | 설계의 platform-observability 분리·Spot 미구성 |
| add-on | VPC CNI NetworkPolicy=true, CoreDNS·kube-proxy·EBS CSI·Pod Identity Agent ACTIVE | 장애·업그레이드 검증은 별도 |
| IAM | Pod Identity 연결. report/scoring/ESO/LBC trust는 cluster·namespace·SA 제한, EBS CSI/VPC CNI trust는 해당 조건 없음 | 설계 IRSA와 다름. add-on trust 조건 검토 및 IAM policy·trust 생성 코드 관리 미완료 |
| VPC | private 노드, public ALB, available NAT 1개 | VPC/SG/route 전체 IaC·AZ 장애 검증 미완료 |
| RDS | 서비스별 DB/migration·TLS·권한 검증, 비공개·암호화·백업 7일 | Single-AZ, 삭제 보호 off. PITR 실제 복원 및 RPO 5분/RTO 4시간 미검증 |
| S3 | web/missions/reports/models, 버전 관리·Public Access Block | 버킷/IAM/lifecycle 전체 재생성 코드 미완료 |
| 진입 | CloudFront 한 도메인, /api 캐시·압축 off, origin 60초·ALB 120초, XFF preserve | ALB origin HTTP. custom domain·ALB TLS 미구성 |
| Secret | ESO 12개 Ready, Secrets Manager 원격 key 참조 | 키 회전·장애 복구 시나리오 미검증. 토스 실연동 키/결제는 미구성 |
| 앱 | 6개 deployment Ready 1/1, digest 고정 | HPA·KEDA·앱 PDB 없음. 고가용성/부하 기준 충족으로 해석하지 않음 |
| 플랫폼 | RabbitMQ·Redis Running, gp3 PVC Bound, Pod 교체 데이터 보존 검증 | 단일 replica, EBS/PVC 삭제 및 AZ 장애로부터 복구 미검증 |
| 배포 | 수동 Helm, CodeBuild→ECR, 수동 S3 웹 배포 | prod Argo CD·Cluster Autoscaler·GitHub OIDC 자동 배포 없음 |
| 관측 | EKS node monitoring add-on, 최소 Collector·Prometheus·Grafana 배포 및 RabbitMQ 수집 | Grafana→Discord 경보 활성화. JVM/전체 앱 계측·CloudWatch datasource·Langfuse 미구성 |
| 환경 분리 | demo 이름·별도 AWS DB/S3, 앱 demo 문항 사용 | 운영/데모 통계 혼입의 전체 데이터 감사·토스 테스트 분리 검증 미완료 |
| 소스 재현성 | 이미지 digest와 현재 values 보존 | core·웹 이용권 수정 미커밋. 현재 develop 전체가 배포된 것은 아님 |

현재 values의 service별 NetworkPolicy는 존재하지만 `namespaceDefaultDeny=false`이며, 일부 외부 서비스 연결은 넓은 CIDR/포트 허용을 사용한다. 기존 합성 연결 테스트는 RabbitMQ·Redis의 지정 허용/차단 경로만 증명한다. 설계 호출 표 전체와 새 Pod의 기본 거부를 검증했다고 간주하지 않는다.

## 실제 서비스 검증 이력

- CloudFront URL에서 Google 학부모 로그인, 무료 이용권 표시, 실제 답변 제출·AI 피드백·돌아보기 저장 확인.
- 주간 2026-11-02~11-08 보고서 1판(학습 1건) 생성, 추가 학습 후 부모 재생성 API로 2판(제출·완료 3건) 생성. 이전 판 유지 확인.
- 2판 PDF·Markdown의 S3 생성·운영자 다운로드, PDF 두 페이지 렌더링 확인.
- 자녀 원문 비공개는 유지. **부모 signed URL 다운로드 성공 경로는 미검증**이며 운영자 S3 다운로드와 구분한다.
- 프론트 표시 문제는 별도 이슈 대기. 돌아보기 표시 임시 수정은 사용자 요청으로 원복했고 이번 AWS 변경에 포함하지 않는다.

## 이후 AWS 작업 순서

1. IAM·VPC·RDS·S3의 생성/관리 범위와 비용·데모 종료 후 축소 방식을 확정한다.
2. 운영 경보·로그 보존과 RDS 복원·PVC/S3 백업 복구 검증을 우선 준비한다. 알림 담당·보존 기간·복원 시험 비용과 종료 조건을 확정한 뒤 실제 구성·시험한다.
3. 위 근거를 바탕으로 노드그룹 분리·Autoscaler·앱 확장과 Secret 회전 범위를 정하고 승인된 범위만 구성한다. 현재 resources는 실측 성능 목표가 아니다.
4. 이미지/웹 소스의 미커밋 변경을 별도 작업으로 정리한 뒤 자동 배포·GitOps 전환을 진행한다.
5. 저장소 전체 및 이력의 전용 비밀 스캔, 환경 분리 감사, 남은 실제 API 경로 검증 후 #185 완료 여부를 판단한다.

이번 점검만으로 #185를 완료·종료하지 않는다. 변경 파일의 자격 증명 패턴 검사와 저장소 전체 이력 비밀 스캔은 서로 다른 검증이다.

## 후속 읽기 전용 점검 (2026-11-03)

- 기존 AWS profile의 STS 계정이 347161580747임을 확인했다. 첫 샌드박스 호출은 signin endpoint 연결에 실패했으나 외부 실행 재시도는 성공했다. 재로그인은 필요하지 않았다.
- IAM 역할 7개의 trust/정책 연결, VPC subnet·route·S3 endpoint·RDS SG, RDS 설정·자동 스냅샷·PITR 범위, S3 암호화·lifecycle·bucket policy, 서울 리전 경보·EKS 로그 보존·Backup plan을 조회했다. 상세 결과와 복구 순서는 [AWS 문서](../../infrastructure/aws/README.md), IAM 차이는 [EKS 문서](../../infrastructure/eks/README.md)에 기록했다.
- 서울 리전 CloudFormation stack·CloudWatch 경보·AWS Backup plan은 빈 목록이다. S3 lifecycle 네 개와 비웹 bucket policy 세 개 조회는 각각 NoSuchLifecycleConfiguration·NoSuchBucketPolicy로 부재를 확인했다. 다른 리전·외부 도구·별도 snapshot·Terraform 관리 부재까지 입증하지 않는다.
- 자동 스냅샷 available 2개와 PITR 범위를 확인했지만 복원 실행·RPO/RTO 검증은 하지 않았다. IAM 생성 주체, 전체 policy·SG·NACL, EBS 백업은 추가 조사 대상이다.
- 변경은 이 보고서와 AWS/EKS README 세 문서에 한정했다. 프론트·배포 values·AWS 리소스·기존 미커밋 변경은 수정하지 않았다. 커밋·push·재배포·알림 발송·유료 복원 자원 생성은 수행하지 않았다.

## 이번 정리의 최종 검증

이 절은 최초 설정 보존 작업의 검증 이력이다. 이후 경보 준비 작업은 아래 별도 절을 따른다.

- 실제 AWS 조회: EKS 노드·add-on·Pod Identity, Helm release, 앱 readiness, ESO 동기화, PVC, RDS·S3·CloudFront 현황을 확인했다. 배포 변경은 실행하지 않았다.
- 로컬 설정 검증: 앱 6개와 platform-data 총 7개 values에 대해 저장소 chart의 `helm lint`와 `helm template` 성공. chart icon 권장 메시지만 있으며 실패는 없다.
- 보존 파일 검증: JSON 파싱, 새 문서의 상대 링크, 민감한 앱 환경변수의 Secret 참조, ExternalSecret 12개·SecretStore 2개 구성 확인. Kubernetes Secret 객체는 포함하지 않았다.
- 비밀 검사: 보존 파일에서 실제 origin header 원문 부재를 값 비교로 확인했고, AWS access key·OpenAI project key·private key 패턴 검사를 통과했다. 이는 제한된 패턴 검사이며 저장소 전체·Git 이력의 전용 비밀 스캔을 대신하지 않는다.
- `git diff --check` 통과. 기존 프론트·이용권 수정은 보존했고 이번 작업에서 변경하지 않았다.
- 미실행: 설정 재배포·신규 환경 복원, 외부 ESO/LB Controller chart 재렌더링, 전체 앱 테스트·브라우저 E2E. 이번에는 앱 동작을 바꾸지 않았으며 현재 상태 조회와 저장소 설정 검증으로 한정했다.

## 운영 경보 준비 (2026-11-03)

이 절의 SNS/Lambda 방안은 이후 사용자가 기존 설계 유지를 선택해 보류했다. 현재 배포 상태는 다음 절을 따른다.

- 최근 24시간 ALB·RDS·EKS 로그 지표와 서울 리전 공개 단가를 실제 AWS API로 조회했다. ALB는 14개 구간, RDS·로그는 288개 구간으로 표본 범위가 다르다. 조회 결과와 임계값·비용·누락 처리·한계는 [설정안](../../infrastructure/aws/monitoring-plan.md)에 기록했다.
- 경보 6개의 미적용 JSON을 준비했다. 실제 AWS 경보는 아직 생성하지 않았다. JSON의 action은 비어 있고 비활성이다.
- 사용자는 Discord 서버 `최종`을 지정했고 새 채널을 직접 만들 예정이다. `aws-alerts`를 제안했으며 채널 ID·웹훅은 아직 받지 않았다. 연결 도구는 읽기 전용이다.
- SNS→Lambda→Discord 중계는 새 실행 역할·Secret을 포함하므로 구체적 권한·비용과 14일 로그 보존의 삭제 영향을 제시했다. 구현·적용·수신 시험은 범위 확정 후 진행한다.
- 이번 작업은 프론트·앱·배포 values·AWS 설정을 변경하지 않았고 커밋·push를 수행하지 않았다. 실제 알림 수신·장애 감지 검증, 원격 CI, 앱 테스트는 실행하지 않았다.

## 기존 노드 최소 관측 배포 (2026-11-03 20:15~20:19 KST)

사용자가 기존 설계 유지·현재 노드 우선 배포·자원 부족 시 증설 논의를 승인했다. Collector·Prometheus·Grafana를 observability namespace/release revision 1로 실제 배포했다. 노드 2대와 기존 앱 예약량·이미지는 유지했다. SNS·Lambda·CloudWatch alarm을 생성하지 않았다.

- chart에 선택적 PVC, Prometheus 용량 보존 한도, Grafana alerting provisioning과 조건부 HTTPS egress를 추가했다. local emptyDir 기본값은 유지한다. prod는 CPU 250m·메모리 544Mi 예약, gp3 4Gi+1Gi를 사용하며 공개 단가 $0.0912/GB-month 기준 추가 저장소는 월 약 $0.456(세금·크레딧 제외)이다.
- platform에 Prometheus→RabbitMQ:15692만 허용하는 별도 정책을 적용했다. Helm keep으로 관측 PVC를 보존하며 기존 platform PVC는 변경하지 않았다.
- 실제 Collector·Prometheus·Grafana 3개 Ready 1/1, PVC 2개 Bound. RabbitMQ·Collector scrape up, RabbitMQ ready messages=0, memory/watermark 약 0.208을 조회했다. Grafana Prometheus datasource health OK.
- 합성 gauge `issue185_pipeline_check=7`을 OTLP로 보내 Collector→Prometheus 수신을 확인했다. 이는 실제 앱 JVM/HTTP 계측 검증이 아니다.
- Grafana·Prometheus Pod를 재생성한 뒤 기존 Grafana 인증·datasource health와 재생성 이전 시각(20:16:51 KST)의 gauge=7 조회에 성공했다. PVC 백업·삭제·AZ 장애 복원 시험은 아니다.
- 기존 앱 6개는 같은 Pod로 Ready, restart=0을 유지했고 두 노드 MemoryPressure=False였다. 두 노드 kubelet working set은 조회 순간 각각 약 2269MiB였다. 기존 top 명령은 metrics-server 부재로 실패했으며 kubelet stats를 사용했다. 관측 Pod 3개는 2a 노드에 배치되어 해당 노드의 Pod 슬롯 17개가 찼다. 앱 rolling update·장애 재배치 여유까지 충분하다고 판단하지 않는다.
- 최종 로컬 검사: local/prod Helm lint·template 통과, 내장 YAML·PVC/정책/Secret 참조·경보 3개 구조 검사 통과. Python YAML 파서 부재와 샌드박스 임시 경로 차이로 최초 검사 실패 후 임시 PyYAML 도구·고정 경로로 재검증했다. production 의존성은 추가하지 않았다.
- **Discord 미완료:** aws-alerts 채널은 확인했으나 현재 계정에 웹훅 관리 메뉴가 없다. 관리자의 웹훅 제공 전까지 prod와 실제 배포 모두 `grafana.alerting.enabled=false`다. 경보 3개의 실제 평가·Discord 전송·복구 알림은 미검증이다. Secret 값·클립보드는 읽지 않았다.
- 미실행: 부하·장시간 운영·학습/추론/PDF 동시 실행, 실제 앱 계측, ALB/RDS Grafana 연결, Langfuse, 원격 CI. 프론트 수정·기존 앱 재배포·커밋·push는 하지 않았다. #185는 미완료다.

## Discord 연결 활성화 (2026-11-03)

- 사용자가 복사한 웹훅을 화면·Git·일반 파일에 출력하지 않고 서버 1557590050034684007, 채널 1567131552121356388(최종/aws-alerts)인지 메타데이터로 확인했다. observability/discord-alert-webhook Secret에만 저장했다.
- prod alerting을 활성화하고 Helm revision 2 배포를 완료했다. lint·렌더링·Kubernetes server dry-run을 통과했다. dry-run의 기존 Helm 객체 last-applied annotation 경고는 실제 apply 변경을 뜻하지 않는다.
- 운영 경보 3개는 Grafana 실제 평가에서 health=ok, state=inactive였다. 직접 Alertmanager 합성 입력은 400/404로 실패해 메시지가 전송되지 않았으며, 별도 임시 합성 평가 규칙으로 전환했다.

- 실제 통지 검증: 임시 rule issue185-discord-verification의 vector(1) 평가가 health=ok·firing이 되었고 20:36:40 KST에 [Firing 메시지](https://discord.com/channels/1557590050034684007/1567131552121356388/1567140453336354932)가 도착했다. vector(0)으로 규칙 수정 후 inactive·health=ok를 확인했고 20:41:40 KST에 [Resolved 메시지](https://discord.com/channels/1557590050034684007/1567131552121356388/1567141711832940605)가 도착했다.
- Resolved의 grafana_state_reason은 Updated였다. 따라서 규칙 수정에 따른 상태 초기화·resolved 전송 경로를 검증한 것이며, 실제 자원 임계값이 자연 회복한 장애 시나리오로 해석하지 않는다. 알림 묶음 간격 5분에 맞춰 수신됐다.
- 검증 후 임시 규칙을 삭제하고 운영 규칙 UID 3개만 남은 것을 API로 확인했다. 검증용 loopback port-forward를 종료했다. 운영 contact point와 경보는 계속 활성화되어 있다.
- 관측 Deployment 3개 Ready, PVC 2개 Bound, 기존 앱 6개 Ready·restart=0 유지. 파일 내 실제 Discord webhook URL 부재 검사(관련 infra 31개 파일), 문서 링크 검사 및 git diff --check 통과. Secrets Manager의 기존 비밀값은 조회하지 않았다.
- 커밋·push·프론트 변경·노드 증설 없음. 실제 앱 장애·장시간 부하·ALB/RDS Grafana 계측은 미검증이며 #185 완료로 판단하지 않는다.

## #185 원문 범위 후속 검증 (2026-11-03 20:57~21:08 KST)

사용자가 #185 원문 작업을 먼저 진행하고 관련 후속 이슈는 나중에 처리하도록 지정했다. #186 자동 배포·롤백, #187 전체 경보·추적, #211 Karpenter의 추가 구현은 진행하지 않았다. 관리형 노드그룹 2개·IRSA와 현재 구성의 차이는 아직 미결정이다.

### 클라이언트 IP (#185 추가 댓글)

- [검증 스크립트](../../infrastructure/aws/verify-viewer-ip.ps1)로 실제 CloudFront 기기 등록 API를 호출했다. 유효하지 않은 형식의 코드를 사용해 기기·페어링을 생성하지 않았다.
- 실제 viewer IP의 Redis 제한 카운터가 정확히 +2, 위조 XFF 주소의 카운터는 +0이고 두 응답 모두 PAIRING_CODE_INVALID였다. ALB XFF preserve·CloudFront prefix list 구성과 실제 core의 IP 판정을 연결해 확인했다.
- 최초 kubeconfig alias 확인과 PowerShell의 problem+json byte[] 처리에서 검증 도구 오류가 있었다. 수정 후 성공했다. 실패 조사 요청도 한도 일부를 사용했으며 카운터를 삭제하거나 한도를 바꾸지 않았다.

### 시연 데이터와 DB 권한

- [read-only SQL](../../infrastructure/aws/audit-demo-data.sql)에서 학부모 1명·학생 2명이 is_demo=false였고 결제·주문·구독은 모두 0건이었다. 사용자가 모두 테스트용 데이터라고 확인했다.
- [일회성 보정 SQL](../../infrastructure/aws/mark-confirmed-demo-data.sql)은 대상 건수·학부모 연결·결제 부재를 검사한 트랜잭션 안에서 학부모 1명·학생 2명만 true로 변경했다. 관리자 1명의 flag와 실제 학습·리포트 내용은 변경하지 않았다. 첫 Job은 Kubernetes 명령 인자의 $$ 처리 때문에 구문 오류로 실패했고 커밋되지 않았다. dollar-quote 태그 수정 후 UPDATE 1·UPDATE 2·COMMIT과 후속 집계를 확인했다.
- core 앱 계정의 CONNECT는 core_db=true, learning_db=false, report_db=false였다. 다른 앱 계정 전체의 권한을 이번 단계에서 다시 검사한 것은 아니다.
- 이 보정은 기존 데이터에만 적용된다. 신규 Google 가입 계정을 자동으로 demo 표시하거나 실사용자 가입을 차단하는 기능은 추가하지 않았다. 데모 환경을 실운영 데이터 저장소로 재사용해서는 안 되며, 새 시연 계정 준비 시 flag를 다시 확인한다. PG 테스트 결제 실호출과 매출 집계 전체 감사는 수행하지 않았다.

### 비밀 스캔·재배포 절차

- Gitleaks 8.30.1 공식 배포 파일을 받아 공개 SHA256 checksum과 대조했다. 최초 Git 이력 481개 커밋 12건, 현재 파일 14건 검출은 합성 테스트 키·계약 SHA256·빈 환경변수 이름·공개 CloudFront OAC ID였다.
- 루트 `.gitleaks.toml`은 기본 탐지 규칙을 유지하고 generic-api-key 규칙에만 정확한 파일 경로와 정확한 검출값을 AND 조건으로 예외 처리한다. 테스트 디렉토리 전체 제외는 하지 않는다. 전역 allowlist의 파일 건너뛰기를 대조 검사에서 발견해 규칙별 targetRules로 제한했다. 같은 파일 경로에 새로운 합성 AWS 형식 키를 넣으면 탐지됨을 확인했다.
- [재실행 도구](../../infrastructure/aws/scan-repository-secrets.py)는 로컬에 존재하는 모든 Git 참조의 이력과 추적/미추적·Git 무시 제외 현재 파일을 별도 검사한다. 보고서는 저장소 밖에 100% redaction으로 저장한다. 원격의 미수신 참조·GitHub 서비스 측 secret scanning·Git 무시된 개인 .env·실제 키 유효성 조회는 포함하지 않는다.
- [앱 재배포 도구](../../infrastructure/gitops/environments/prod/redeploy-app.ps1)는 계정·EKS endpoint·ECR digest·기존 Helm release 상태를 검사한다. 기본 server dry-run은 앱 6개 모두 통과했다. 실제 앱 재배포·장애 복구·새 클러스터 재생성 성공을 뜻하지 않는다. 적용은 별도의 -Apply로 명시한다.

최종 검증: 규칙별 예외로 수정한 뒤 Git 이력 481개 커밋과 현재 파일 1,516개 모두 Gitleaks exit=0이었다. PowerShell 두 스크립트 구문 검사·git diff --check를 통과했고 앱 6개 Ready 1/1을 확인했다. 이번에 생성한 일회성 Job 3개는 삭제했다. 원격 CI·실제 앱 재배포·새 클러스터 복원은 실행하지 않았다.

남은 #185 항목: 노드그룹·IRSA 차이 결정, eksctl 생성 설정 및 기존 자원 관리 경계, DB/Secret/OAuth/웹까지 포함한 초기 배포 재현, 데모 종료 후 축소 방식 확정, 부모 권한 리포트 다운로드의 실제 경로 확인. 기존 로그인·학습 제출·리포트 생성 검증은 위 이력대로이며 이번 단계에서 한도를 소비하는 학습·재생성을 반복하지 않았다. #185 전체 완료·종료 및 커밋·push는 하지 않았다.

## 초기 배포·데모 종료 절차 정리 (2026-11-03)

사용자가 브라우저 다운로드 확인과 노드그룹·IRSA 결정을 제외하고 초기 배포 재현 절차·데모 종료/축소안 작성을 요청했다. 이 단계는 문서 작업이며 실제 설치·축소·DB 정지·백업 생성은 수행하지 않았다.

- [prod README](../../infrastructure/gitops/environments/prod/README.md)에 대상 계정/입력, 기반 자원→Secret→플랫폼→DB/migration→앱/초기 데이터→CloudFront/OAuth/웹→최종 검증 순서를 추가했다. 기존 환경 재배포와 빈 환경 초기 설치를 구분했다.
- 기존 migration Job 4개의 성공 상태·고정 이미지 digest를 읽기 전용으로 확인해 기록했다. prod migration=false, 공통 migration Job의 RDS CA mount 부재, 수동 Helm에서 Argo PreSync가 선행 실행을 보장하지 않는 점을 실행 전 준비 사항으로 명시했다. RDS 계정 bootstrap·초기 운영 데이터 seed·미커밋 core/웹 빌드 입력·전체 인프라 생성 코드는 여전히 미완료다.
- [EKS README](../../infrastructure/eks/README.md)에 유지/앱만 중단/노드0+RDS정지/철거 비교, 남는 비용, 정상 종료·백업·재개 순서와 실패 시 중단 기준을 작성했다. 단기 휴지는 제안이며 실행 결정은 하지 않았다. RDS 7일 자동 재시작과 scaling-config의 PDB 미준수 주의는 AWS 공식 문서와 대조했다.
- 실제 PV 4개의 Delete reclaim policy와 EBS AZ를 조회했다. RabbitMQ·Prometheus·Grafana는 2a, Redis는 2b이므로 재개 시 양쪽 AZ에서 PVC를 연결할 노드가 필요하다. 2→1 운영 축소나 PVC affinity 제거를 해결책으로 제시하지 않았다.
- 브라우저·앱·IAM·노드·DB·S3 내용은 변경하지 않았다. 검증은 문서 상대 경로/링크·기존 설정과 설명 대조·git diff --check로 한정한다. 실제 신규 배포·종료/재개·복원 성능·부모 다운로드·원격 CI는 미실행이다.

이번 범위의 절차 작성은 완료했으며, 절차가 있다는 이유로 초기 배포 재현 성공이나 #185 전체 완료를 주장하지 않는다. 실제 실행 전 미완료 선행 조건과 중단/재개 일시·담당·백업 보관 위치를 확정해야 한다.

## IaC·RDS 초기화·중단 자동화 (2026-11-03)

사용자가 IaC 방식을 eksctl + AWS CLI 스크립트로, 데모 외 기간 축소를 "노드 0대 + RDS 정지"로 정했다. 도메인은 기본 cloudfront.net, CloudFront→ALB는 HTTP를 유지한다(ALB SG는 CloudFront prefix list만 허용, origin 헤더 규칙 적용 확인). 이번 단계는 저장소 작업이며 AWS 자원은 변경하지 않았다.

- [eksctl 설정](../../infrastructure/eks/cluster.json)과 [AWS 정의·스크립트](../../infrastructure/aws/README.md#iac-eksctl--aws-cli-스크립트-185)를 추가했다. 실제 IAM trust·정책 원문 16개를 `infrastructure/aws/iam/`에 보존했다.
- `demo_stack.py plan`(읽기 전용)을 실제 계정에 실행해 VPC·subnet 4·NAT·IGW·S3 endpoint, S3 4, ECR 7, Secret 이름 11, RDS·SG·subnet group, IAM 역할 8, EKS·노드그룹·add-on 6·Pod Identity 7의 **55개 항목이 모두 일치**했다. `apply`는 가짜 AWS 단위 테스트로 빈 계정 생성 순서, 완성된 계정에서 변경 호출 0건, private route의 NAT·S3 endpoint 연결을 확인했다. 실제 새 계정 생성과 eksctl 실행은 하지 않았다(eksctl 미설치, `--dry-run` 미검증).
- RDS 초기화: `rds-bootstrap.sql`을 로컬 PostgreSQL 17.11의 비-superuser 관리자로 두 번 실행해 멱등성, app 계정 DML 허용·DDL 거부·다른 DB 접속 거부, migration 이력 테이블 권한 회수를 확인했다. 실제 RDS에서는 실행하지 않았다(`rds-bootstrap` dry-run에서 입력 Secret 6개·`rds-ca` 존재 확인).
- migration: app-service chart에 Job 전용 `migration.extraVolumes`·`extraVolumeMounts`를 추가했다(기존 local·prod 렌더링 결과 동일). `environments/prod/migrations/`에 core·learning·report Job 입력을 두었고 helm lint 통과. core-migrate 고정 digest는 V23까지라 빈 DB 재현에는 재빌드가 필요하다.
- 중단·재개: `pause`/`resume` dry-run을 실제 클러스터에 실행해 노드그룹 2/2/2, RDS available, RabbitMQ 미처리 메시지 0, 대상 워크로드 11개·PV 4개를 확인했다. `--execute`는 실행하지 않았다.

### 데모 사양 판단 근거 (결정 대기)

| 항목 | 2026-11-03 조회 | 해석 |
|---|---|---|
| 노드 메모리 예약 | 2a 2970Mi(90%), 2b 3054Mi(92%) | 새 Pod·rolling update 여유가 거의 없음 |
| Pod 슬롯 | 2a 17/17, 2b 12/17 | 2a 노드는 Pod를 더 받을 수 없음. AZ 고정 PVC(RabbitMQ·관측 2a, Redis 2b) 때문에 재배치도 제한 |
| RDS(최근 3일, 1시간 단위) | CPU 최대 28%, 여유 메모리 최소 약 956MiB, 연결 최대 28 | db.t4g.small 유지 가능 |
| 공개 단가(서울, On-Demand) | t3.medium $0.052/h, t3.large $0.104/h, db.t4g.small $0.051/h, db.t4g.medium $0.102/h | 세금·크레딧·저장소 제외 |

예산은 조직 SCP가 `budgets:ViewBudget`을 막아 조회하지 못했다.

**결정(2026-11-03):** 사용자가 노드그룹을 t3.medium **3대**(min/desired/max 3)로 정했다. RDS는 db.t4g.small Single-AZ를 유지한다. 추가 비용은 공개 단가 기준 노드 1대 $0.052/h(월 약 $38, 세금·크레딧·EBS 제외)다. 노드그룹 1개·Pod Identity 구조는 데모 사양으로 유지하며, 설계의 `platform-observability` 그룹·IRSA와의 차이는 이 결정으로 받아들인다. `cluster.json`·`demo-stack.json`은 3대 기준이다.

**적용(2026-11-03 23:18 KST):** 사용자 승인 후 `eks update-nodegroup-config`로 application을 3/3/3으로 변경했다. update 0f021ef6는 Successful, 23:19에 새 노드(2b)가 Ready였다. DaemonSet 5종 3/3 Ready, 기존 앱 6개는 같은 Pod·restart 0으로 유지, CloudFront 200, `demo_stack.py plan` 55/55 일치. 새 노드는 Pod 5개·메모리 예약 4%로 여유가 생겼으나 **2a 노드는 여전히 Pod 17/17·메모리 예약 90%**다. 2a PVC를 쓰는 RabbitMQ·Prometheus·Grafana는 2a 노드에만 배치될 수 있으므로, 새 Pod 배치·rolling update는 새 노드로 가는 무상태 앱부터 여유가 생긴 것이다. 기존 Pod는 재배치하지 않았다.

## 남은 항목 처리 (2026-11-04)

- **신규 Google 가입자 demo 표시:** `feature/demo-signup-flag`(5538173)에 `AUTH_NEW_ACCOUNT_DEMO`(기본 false)를 추가했다. true인 환경에서만 새 Google 부모를 `is_demo=true`로 저장하고 기존 계정은 바꾸지 않는다. 학생은 기존처럼 부모 값을 따른다. JDK 21 컨테이너의 Testcontainers로 관련 테스트 27개(신규 1개 포함)가 통과했다. AWS 반영은 core 재빌드가 필요하며, 현재 배포 core의 미커밋 이용권 수정이 정리된 뒤 진행한다.
- **토스 테스트 결제:** 저장소 입력만 준비했다([prod README](../../infrastructure/gitops/environments/prod/README.md#다음-core-재배포-입력-토스신규-가입자-demo-185-미적용)). Secret 값 입력 전이라 AWS·클러스터에는 적용하지 않았다.
- **eksctl 검증:** eksctl 0.231.0 공식 배포 파일을 checksum으로 확인하고, `render-eksctl` 결과로 `eksctl create cluster --dry-run`을 실제 계정에 실행해 exit 0을 확인했다. 정규화된 출력에 버전 1.35, add-on 6개 버전, Pod Identity 7개, 노드그룹 t3.medium 3/3/3·20GiB·private, 서비스 역할·노드 역할, VPC·subnet 4개가 그대로 유지됐다. dry-run은 자원을 만들지 않는다.
- **결제 Secret (2026-11-04 01:47 KST):** 사용자가 로컬 `.env`의 공용 문서 테스트 키(`test_gsk_docs_`, MID `tgen_docs`)와 빌링 암호화 키로 `sagomungchi/demo/app/payment`를 직접 생성했다(값 비출력). `demo-stack.json`에 추가했고 `plan` 56/56 일치. 공용 키라 일반 결제 승인만 시연 가능하고 빌링·웹훅·주문 조회 복구는 실제 상점 계약 전까지 미검증이다. ESO 권한·ExternalSecret·core env는 다음 core 재배포 때 적용하며, 웹 재빌드에는 공개 클라이언트 키 `TOSSPAYMENTS_CLIENT_KEY`(`test_gck_docs_`)가 필요하다.
- 남은 사용자 작업: 부모 계정 다운로드 확인, 이용권 수정 정리. core-migrate 재빌드와 시연 데이터 재감사는 그 다음 순서다.

## PR 병합 전 사전 확인 (2026-11-04)

- PR #320·#321·#322를 develop ef79289에 로컬 merge한 트리로 core·core-migrate 이미지와 웹을 빌드했다(push 없음). core jar의 `new-account-demo`·이용권 API·V26, core-migrate의 V1~V26, 웹의 공개 클라이언트 키 포함과 시크릿 키 형태 문자열 부재를 확인했다.
- V26(보호자 이관)은 unique index·CHECK 제약을 추가하므로 [사전 점검 SQL](../../infrastructure/aws/check-v26-preconditions.sql)을 만들었다. 로컬 PostgreSQL에 V25까지 적용한 스키마에서 위반 0·최신 25로 동작을 확인했고, 실제 RDS에서는 배포 직전에 실행한다. 이관 기능은 `app.guardian-transfer.enabled`가 없으면 로드되지 않는다.
- ESO 결제 정책 추가는 세션 권한 규칙상 작업자가 직접 실행한다. 재배포 절차는 [prod README](../../infrastructure/gitops/environments/prod/README.md#다음-core웹-재배포-절차-320321322-병합-후)에 정리했다.

## 부모 리포트 다운로드 실제 확인 (2026-11-04)

- 학생이 원문 비공개일 때 부모 화면의 PDF·Markdown 버튼이 비활성이고 "원문 비공개 중에는 기존 파일을 제공하지 않습니다" 안내가 표시됨을 CloudFront 실제 화면에서 확인했다(`parentSharingEnabled=false`).
- 학생 화면에서 "학부모님께 공개할게요"로 바꾼 뒤 부모 계정으로 주간 리포트 2판(2026-11-02~11-08)의 **PDF·Markdown을 실제로 내려받았다.** 부모 서명 URL 다운로드 경로가 동작한다.
- 내려받은 PDF는 2쪽이며 Markdown과 내용이 같다: 수치 3개(표본 부족이라 비율 대신 개수, 분자/분모 3/3), 생각 유형 5개, 전후 변화 수치, 돌아보기 3건. 2판은 비공개 상태에서 생성됐으므로 원문 자리는 "원문 비공개"로 남아 있다. 파일은 생성 시점의 공개 범위를 따르며, 공개 후 원문이 들어간 파일을 보려면 새 판 생성(학부모 재생성 한도 사용)이 필요하다. 재생성은 하지 않았다.
- 확인 후 공개 설정은 사용자가 원래대로(비공개) 되돌리기로 했다.
