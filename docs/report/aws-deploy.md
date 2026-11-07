# AWS 데모 배포 (#185·#211·#212·#372)

계정 347161580747 / ap-northeast-2. 기존 AWS 구성을 저장소에 보존하고 설계와의 차이를 결정·정리한 기록이다. 경보·관측 구성과 Discord 연결 검증은 [ops-observability](ops-observability.md), 부하 시험은 [load-test](load-test.md), CD 배포는 [cd-release](cd-release.md).

## 저장 위치

- [prod Helm values·Secret 참조·정책·초기 배포 절차](../../infrastructure/gitops/environments/prod/README.md)
- [EKS 인벤토리·노드그룹·중단/재개 절차](../../infrastructure/eks/README.md)
- [CloudFront·ALB redacted 설정·RDS/S3 인벤토리·IaC 스크립트](../../infrastructure/aws/README.md)

수집한 values는 배포 상태를 보존한 것이며, 새 계정을 처음부터 만드는 완성된 IaC는 아니다. 비밀 값·Kubernetes Secret data·Helm release Secret·CloudFront origin header 원문은 기록하지 않는다.

## 구성 결정

| 항목 | 결정 | 시점 |
|---|---|---|
| IaC | eksctl(`infrastructure/eks/cluster.json`) + AWS CLI 스크립트(`demo_stack.py` plan·apply·pause·resume). IAM trust·정책 원문은 `infrastructure/aws/iam/` | 11-03 |
| 진입 | 기본 cloudfront.net 도메인, CloudFront→ALB HTTP 유지(ALB SG는 CloudFront prefix list만 허용, origin 헤더 규칙) | 11-03 |
| 노드그룹 | 2개 모두 On-Demand t3.medium: `application` 2대(최대 3), `platform-observability` 2대(2a·2b 1대씩, `workload=platform:NoSchedule`). 상태 저장 서비스(replica 1, AZ 고정 EBS)에 Spot이 맞지 않아 설계의 Spot을 On-Demand로 바꿈. scoring 메모리 예약 2Gi → 1Gi | 11-04 (PM 승인) |
| Pod 권한 | 설계의 IRSA 대신 EKS Pod Identity. EBS CSI·VPC CNI trust에 클러스터·namespace·SA 조건 추가 | 11-04 |
| RDS | db.t4g.small Single-AZ 유지(최근 3일 CPU 최대 28%, 연결 최대 28). 서비스별 계정은 [db-dev-guide 8절](db-dev-guide.md#8-서비스별-db-계정-230) | 11-03 |
| 데모 외 기간 | 노드 0대 + RDS 정지(`demo_stack.py pause`/`resume`, Karpenter 정지 포함). 노드 0에도 EKS control plane·NAT·RDS 저장소·EBS 비용은 남음 | 11-03, 11-06 실행 |
| 배포 기준 | develop → main 릴리스 PR 병합 후 그 SHA만 배포(ECR 태그 `main-<sha>`) | 11-04 |
| 시연 계정 | `AUTH_NEW_ACCOUNT_DEMO=true`로 새 Google 부모를 `is_demo=true` 저장. 기존 테스트 계정은 일회성 SQL로 보정(학부모 1·학생 2) | 11-03~04 |
| 결제 | 공용 문서 테스트 키를 `sagomungchi/demo/app/payment` Secret으로 ESO 연결. 일반 결제 승인만 시연 가능, 빌링·웹훅·주문 조회 복구는 실제 상점 계약 전까지 미검증 | 11-04 |
| 비밀 스캔 | Gitleaks 8.30.1, 루트 `.gitleaks.toml`은 generic-api-key 규칙에만 정확한 경로·값 예외. 재실행 도구 `infrastructure/aws/scan-repository-secrets.py` | 11-03 |

## 설계와 남은 차이

| 항목 | 현재 | 남은 일 |
|---|---|---|
| RDS | 비공개·암호화·자동 백업 7일, Single-AZ, 삭제 보호 off | PITR 실제 복원, RPO 5분·RTO 4시간 미검증 |
| 플랫폼 | RabbitMQ·Redis·관측 단일 replica, AZ 고정 PVC(RabbitMQ·Prometheus·Grafana 2a, Redis 2b) | EBS/PVC 삭제·AZ 장애 복구 미검증 |
| 진입 | CloudFront→ALB HTTP origin | custom domain·ALB TLS 미구성 |
| Secret | ESO·Secrets Manager 원격 key 참조 | 키 회전·장애 복구 시나리오 미검증 |
| NetworkPolicy | 서비스별 정책 있음, `namespaceDefaultDeny=false`, 일부 외부 연결은 넓은 CIDR·포트 | 설계 호출 표 전체·새 Pod 기본 거부 미검증 |
| S3·IAM 재생성 | 인벤토리·정책 원문 보존, `demo_stack.py apply`는 가짜 AWS 단위 테스트로 순서만 확인 | 새 계정 실제 생성 미실행 |
| NAT | 2a 한 곳(아래 #212) | 다중 AZ는 담당자 결정 사항 |

## 실제 서비스 검증

- 11-03: CloudFront URL에서 학부모 Google 로그인·답변 제출·AI 피드백·돌아보기, 주간 리포트 1·2판 생성(이전 판 유지), PDF·Markdown S3 생성
- 11-03: 클라이언트 IP 판정([검증 스크립트](../../infrastructure/aws/verify-viewer-ip.ps1)) — viewer IP 제한 카운터 +2, 위조 XFF +0. core 앱 계정은 `core_db`만 CONNECT
- 11-04: 부모 계정으로 주간 리포트 PDF·Markdown 실제 다운로드(서명 URL). 원문 비공개 중에는 버튼 비활성·안내 확인
- 11-04 main 재배포 후: 로그인·이용권 표시, 리포트 조회, 답변 3건 판정 `DONE`, 시도 완료, 5개 서비스 로그 오류 0. 시연 데이터 부모 1·학생 3 모두 `is_demo=true`, 결제·주문·구독 0건
- 비밀 스캔: Git 이력과 현재 파일 1,529개 0건(11-04)
- 미실행: 신규 Google 가입 실계정 확인, 공용 테스트 키 결제 승인, 새 클러스터 복원

## S3 Gateway 엔드포인트와 NAT 병목 점검 (#212, 2026-11-04)

10/29 멘토링의 "S3 엔드포인트 연결, core·NAT 구간 병목" 지적을 실제 계정에서 읽기 전용으로 점검했다. **AWS 자원은 생성·수정·삭제하지 않았다.** S3 Gateway 엔드포인트가 이미 있어서 새로 만들 필요가 없었다.

### S3 경로 현황

| 항목 | 조회 결과 |
|---|---|
| 엔드포인트 | `vpce-0dab53d8da86d39c8`(`sagomungchi-demo-vpce-s3`), `com.amazonaws.ap-northeast-2.s3`, Gateway, available, 2026-11-02 05:43 UTC 생성(NAT GW 생성 08:01 UTC보다 먼저) |
| 라우팅 | private1(2a) `rtb-01f53b33b57b1e55b`·private2(2b) `rtb-0599728dcf319a662` 모두 `pl-78a54011`(S3 prefix list) → vpce 경로 active. 0.0.0.0/0 → NAT보다 구체적인 prefix가 우선한다. public 라우팅 테이블에는 없음(노드·RDS가 없음) |
| 엔드포인트 정책 | 기본 전체 허용(`Principal *`, `Action *`, `Resource *`) |
| `aws:sourceVpce` 영향 | 저장소 IAM 정책 원문(`infrastructure/aws/iam/`)에 해당 조건 없음. reports·models·missions 버킷은 bucket policy 없음, web 버킷 policy는 CloudFront 배포 SourceArn 조건만 있어 VPC 경로와 무관 |
| 앱 클라이언트 | report(`app/clients/storage.py`)·scoring(`app/clients/model_artifacts.py`)는 `region_name=S3_REGION`(ap-northeast-2)로 regional endpoint `s3.ap-northeast-2.amazonaws.com`을 쓴다. prod values에 `S3_ENDPOINT_URL` 없음 |
| `demo_stack.py plan` | OK=58, 차이 없음(private route의 S3 endpoint 연결 대조 포함) |

**엔드포인트 정책은 기본 전체 허용을 유지한다.** 노드의 ECR 이미지 layer 다운로드도 AWS 소유 S3 버킷을 이 엔드포인트로 받으므로, 우리 버킷 4개로 좁히면 이미지 pull이 깨진다. 버킷 접근 제한은 이미 Pod Identity 역할 정책(scoring 읽기, report `reports/*` 읽기·쓰기)이 맡는다. 정책을 좁히려면 ECR layer 버킷 등 필요한 대상을 먼저 조사한 별도 작업으로 한다.

### S3 트래픽이 NAT를 거치지 않는다는 근거

1. **실제 대용량 다운로드와 NAT 지표 대조:** scoring Pod(`scoring-service-85d8c5f57f-p9kvw`, 2a 노드, emptyDir `/tmp` 새로 생성)가 17:53:53~17:54:12 KST에 models 버킷에서 `model.safetensors` 2개(442,539,656 + 442,524,276 bytes, 약 844MiB)를 받아 로딩하고 17:54:22에 Ready가 됐다. 같은 17:53·17:54 KST 1분 구간 NAT `BytesInFromDestination` 합은 0.04MiB, `BytesOutToDestination`은 0.02MiB였다. 844MiB가 NAT를 지났다면 이 구간에 그대로 나타났어야 한다.
2. **DNS가 prefix list 대역으로 해석:** report-api·report-worker·scoring Pod 안에서 버킷 호스트(`<bucket>.s3.ap-northeast-2.amazonaws.com`)를 해석한 IP 15개가 모두 `pl-78a54011` CIDR(3.5.184.0/21, 52.219.144.0/22, 52.219.202.0/23, 52.219.204.0/22)에 속했다.
3. **앱 권한으로 접근 확인:** 세 Pod에서 앱과 같은 설정(regional endpoint, Pod Identity)으로 `ListObjectsV2`(MaxKeys=1)를 호출해 HTTP 200을 받았다. 객체 본문은 읽거나 쓰지 않았다. report의 PUT 경로는 이번에 다시 실행하지 않았고, 기존 리포트 생성·다운로드 확인(위 절)을 근거로 둔다.

VPC Flow Logs는 VPC에 없다(`describe-flow-logs` 빈 목록). 비용이 들고 설정 변경이라 만들지 않았다. 따라서 패킷 단위 경로 기록은 없고 위 지표·DNS·라우팅이 근거다.

### NAT를 거치는 구간

Pod 사이 호출(core ↔ learning·ai·report·RabbitMQ·Redis)과 RDS는 VPC 내부라 NAT를 거치지 않는다. core가 내부 호출의 중심이지만 NAT와 관계된 것은 외부 호출뿐이다.

| 출발 | 대상 | 비고 |
|---|---|---|
| ai | LLM API | 판정·되묻기·리포트 서술. 요청·응답이 텍스트라 바이트가 작다 |
| core | 토스페이먼츠, Google OAuth token | 사용자 동작 단위의 짧은 HTTPS |
| ESO, Pod Identity 사용 Pod | Secrets Manager, STS·EKS Auth | Interface endpoint 없음 |
| kubelet | ECR API(`*.dkr.ecr`), ghcr.io·Docker Hub·quay 등 공개 레지스트리 | ECR layer 본문은 S3 엔드포인트, 공개 레지스트리 이미지는 NAT |
| Grafana | Discord webhook | 경보 발생 시만 |

### NAT 지표 (2026-11-02 17:00 ~ 2026-11-04 20:00 KST, 1시간 단위 51개)

| 지표 | 값 | 판단 |
|---|---|---|
| ActiveConnectionCount 최대 | 126 | 목적지별 동시 55,000 한도와 거리가 멀다 |
| ErrorPortAllocation 합 | 0 | 포트 고갈 없음 |
| PacketsDropCount 합 | 6 (모두 11-02 17시, 구성 직후 1시간) | 이후 0 |
| BytesInFromDestination 합 | 약 4.0GiB, 시간 최대 1.2GiB | 평균 3Mbps 미만, NAT 대역폭(기본 5Gbps)에 비해 매우 작음 |
| BytesOutToDestination 합 | 약 0.8GiB, 거의 전부 11-03 09시 1시간 | 원인 미확정(Flow Logs 없음) |
| IdleTimeoutCount 합 | 5,240 | 350초 이상 쉰 연결을 NAT가 정리한 횟수. 오류 지표는 아님 |

수신 바이트가 큰 시간은 노드·이미지 작업과 맞는다. 11-03 20시 910MiB는 관측 스택 배포(20:15~20:19), 11-04 11시 962MiB는 노드그룹 분리로 새 노드 2대가 생성된 시각(11:29)이다. 공개 레지스트리 이미지 pull로 보이지만 Flow Logs가 없어 대상까지 확정하지는 않았다.

**판단: 현재 NAT 병목은 없다.** 연결 수·포트·드롭·대역폭 모두 여유가 크다. 51시간 처리량 약 4.8GiB는 처리 요금 $0.059/GB 기준 약 $0.3이다. 남은 위험은 성능이 아니라 가용성이다. NAT가 2a 한 곳에만 있어서 2a 장애 시 2b 노드의 Pod도 LLM·결제·OAuth·Secret 갱신·이미지 pull을 못 한다. 2b Pod의 외부 호출은 AZ 간 전송($0.01/GB 양방향)이 붙지만 현재 양으로는 무시할 수준이다. 한계: 부하 시험은 하지 않았고, 연결 유지 기간이 350초를 넘는 HTTP 클라이언트의 stale 연결 오류 여부는 앱 로그로 따로 보지 않았다.

### 완화안 비교 (서울 단가: AWS Price List API 2026-11-04 조회, 월 730시간, 세금·크레딧 제외)

| 안 | 월 추가 비용 | 효과 | 한계 |
|---|---|---|---|
| A. 현재 유지(zonal NAT 1개, 2a) | $0 (현재 NAT $43.07 + EIP $3.65) | - | 2a 장애 시 전체 외부 호출 중단 |
| B. AZ별 zonal NAT(2b 추가, private2 기본 경로 변경) | 약 +$46.7 (NAT $0.059/h + 공인 IPv4 $0.005/h) | AZ 장애 격리, AZ 간 전송 제거 | 데이터 처리 단가는 같음 |
| C. Regional NAT GW(2개 AZ) | 약 +$43~47 (AZ마다 $0.059/h 과금, [VPC 요금](https://aws.amazon.com/vpc/pricing/)) | 하나의 NAT로 AZ 확장 | 기존 NAT 교체·라우팅 변경 필요, 신규 기능이라 eksctl·`demo_stack.py` 지원 확인 필요 |
| D. Interface 엔드포인트(Secrets Manager·STS·ECR api·dkr) | 약 +$76 (엔드포인트당 $0.013/h × 2 AZ) | AWS API 호출만 NAT에서 분리 | LLM·토스·OAuth는 그대로 NAT. 현재 양 대비 비쌈 |

**추천: 데모 기간(12/7까지)은 A 유지.** 병목 근거가 없고, 2a 장애 때는 RabbitMQ·Prometheus·Grafana의 EBS가 2a에 있어 서비스가 이미 함께 멈추므로 B·C의 가용성 이득이 현재 구성에서는 작다. 상태 저장 서비스의 AZ 의존을 줄이거나 실제 운영 전환을 결정할 때 B(가장 단순)를 다시 검토한다. **NAT 다중 AZ 적용 여부는 담당자 결정 사항으로 남기며 이번에 적용하지 않았다.**

조회 근거: EC2 `describe-vpc-endpoints`·`describe-route-tables`·`describe-nat-gateways`·`describe-prefix-lists`·`get-managed-prefix-list-entries`·`describe-flow-logs`, CloudWatch `get-metric-statistics`(AWS/NATGateway), S3 `list-objects-v2`(models 키·크기, reports는 최신 3개 시각·크기만), kubectl Pod 상태·scoring 로그·Pod 내 DNS 해석과 `ListObjectsV2`, Pricing `get-products`. Secret 값과 객체 본문은 조회하지 않았다.

## EKS 노드 자동 확장 Karpenter와 앱 HPA (#211·#372, 2026-11-05)

10/29 멘토링의 "EKS 도입 시 Karpenter 노드 오토스케일링까지 구성" 권고(#211)와, prod에 HPA·KEDA가 꺼져 있어 트래픽이 늘어도 Pod가 1개로 유지되고 Karpenter 노드가 생기지 않는다는 지적(#372)을 함께 처리했다. Karpenter는 트래픽을 보지 않고, 기존 노드에 자리가 없는 Pending Pod가 생길 때만 노드를 추가한다. 그래서 흐름은 트래픽 증가 → HPA가 Pod 증가 → 기존 노드 자리 부족 → Pending → Karpenter가 노드 추가 → 부하 종료 후 HPA 축소 → 빈 노드 정리다.

### 적용 전 상태 (11/05 09:40 KST 읽기 전용 조회)

| 항목 | 값 |
|---|---|
| 클러스터 | EKS 1.35(eks.27), access mode API. OIDC provider는 GitHub Actions용만 있고 Pod 권한은 Pod Identity만 사용 |
| `application` | 관리형 t3.medium On-Demand 2/2/3, 2a·2b 1대씩. 요청 2a 1300m/2426Mi(할당 가능 1930m/3292Mi, Pod 14/17), 2b 750m/1390Mi(Pod 10/17) |
| `platform-observability` | t3.medium 2/2/2, taint `workload=platform`. RabbitMQ·Prometheus·Grafana PV 2a, Redis PV 2b |
| 앱 | 6개 모두 replica 1, HPA·KEDA·PDB 꺼짐. metrics-server·KEDA 미설치 |
| 노드 이미지 | 앱·DaemonSet 이미지는 모두 ECR(S3 Gateway 엔드포인트 경유). 공개 레지스트리는 ESO(ghcr), LB Controller·Karpenter(public.ecr), platform·관측(Docker Hub)뿐 |

### 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 설치 | Karpenter 1.15.1 Helm(OCI), 기존 prod 방식과 같이 수동 Helm. values `environments/prod/karpenter.json` | 1.35는 1.9 이상 지원. prod는 Argo CD 미구성 |
| 노드 | t3.medium·t3.large On-Demand, 2a·2b. Spot·SQS 중단 알림 큐 미사용 | 앱이 replica 1·PDB 없음이라 Spot 회수가 곧 중단. t3a는 2b 미제공 |
| 상한 | NodePool `limits` CPU 4·메모리 16Gi(최대 약 2대). 최악 상시 2대 약 $156/월(t3.large $0.104/h, 서울 On-Demand) | 평소 0대 |
| 정리 | `WhenEmptyOrUnderutilized`, `consolidateAfter 5m`, 한 번에 1노드, `expireAfter 720h` | 부하 종료 후 비용이 남지 않게 함 |
| 기존 노드그룹 | 둘 다 유지. 컨트롤러는 `application` 노드에 replica 1(요청 200m/384Mi) | 컨트롤러가 자기가 만든 노드에 있으면 안 됨. 데모 안정성 |
| AZ·EBS | NodePool에 `workload=platform` taint를 넣지 않아 상태 저장 Pod는 Karpenter 노드에 가지 않음 | 2a·2b PV 제약 유지 |
| NAT | pull-through cache 미도입 | 앱·노드 기본 이미지가 ECR이라 새 앱 노드의 NAT 유입은 작다고 판단(실측 안 함) |
| HPA | core·learning·ai, 최소 1·최대 3·CPU 70%. scoring·report-api는 고정, report-worker KEDA는 후속 | 평소 비용 불변. scoring은 모델 로딩·메모리 1Gi |
| 축소 끊김 | D안: 최소 1 유지 + `application` 노드그룹 preferred nodeAffinity + ReplicaSet 기본 삭제 순서(최근 Pod부터) | 아래 설명 |

replica 1에서 노드를 정리하면 Kubernetes eviction은 Pod를 먼저 지우고 나서 새로 만들기 때문에, 새 Pod가 Ready가 될 때까지 요청을 받을 Pod가 없다. 롤링 배포(새 Pod 먼저)와 다르다. D안은 기본 Pod를 관리형 노드에 두고 늘어난 Pod만 Karpenter 노드에 올라가게 해서, HPA가 줄일 때 최근 Pod(Karpenter 노드)부터 지워지고 빈 노드는 eviction 없이 정리되게 한다. 부하 중 재배포·재시작으로 Pod 나이 순서가 바뀌거나 관리형 노드 장애로 기본 Pod가 Karpenter 노드에 가면 축소 때 한 번 끊길 수 있다. A안(최소 2 + PDB)은 모든 경우 끊김이 없지만 상시 요청 증가로 Karpenter 노드 1대(약 $38/월)가 계속 뜰 수 있어 보류했다.

### 적용 (2026-11-05 KST, 단계마다 승인 후 실행)

| 시각 | 단계 | 결과 |
|---|---|---|
| 16:46:03~16:46:46 | metrics-server EKS add-on v0.9.0-eksbuild.14 (`replicas 1`, `nodeSelector eks.amazonaws.com/nodegroup=application`) | ACTIVE, `kubectl top` 정상, 앱 재시작 0 |
| 17:24:31~17:25:09 | `demo_stack.py apply --confirm-account`로 IAM 역할 `sagomungchi-demo-karpenter-controller-role` | 이 역할만 생성. `plan`에서 trust·inline 원문 일치 |
| 17:27:30 | Pod Identity `kube-system/karpenter` | `plan` OK=61 |
| 17:37:20~17:37:41 | `helm install karpenter` 1.15.1, kube-system | revision 1, 컨트롤러 1개 Running(실사용 6m/80Mi), CRD 4개(NodePool·NodeClaim·EC2NodeClass·NodeOverlay), 권한 오류 0 |
| 17:39:30 | EC2NodeClass `application`·NodePool `application-burst` | 둘 다 Ready. instance profile 자동 생성, AMI `ami-0a3227d9c98935bcb`(기존 노드와 같음). 적용 직후 1초 동안 `no subnets found` 10건 후 `SubnetsReady=True`, 이후 오류 없음. NodeClaim 0 |
| 17:53:31~17:54:41 | learning-service revision 4 (`redeploy-app.ps1 -Apply`) | HPA `cpu 1%/70%`, replica 1 |
| 17:55:02~17:55:30 | ai-service revision 4 | HPA `cpu 2%/70%`, replica 1 |
| 17:55:46~17:56:53 | core-service revision 8 | HPA 생성, replica 1. CloudFront 200 |

세 앱 적용은 이미지 digest를 바꾸지 않았다. 적용 직전 live Helm values가 저장소 값과 같았고, 렌더링 차이는 Deployment `replicas` 줄 제거·affinity·HPA뿐이었다. affinity 때문에 각 앱이 롤링 재시작을 1회 했다. 적용 동안 Karpenter 노드는 생기지 않았고(NodeClaim 0, 노드 4대) 앱 재시작은 0이다. core의 OTel span 전송 실패 경고는 적용 전 Pod에도 있던 기존 현상이다.

같은 날 11:21~17:06 #361 부하 시험이 ai `OPENAI_BASE_URL`(LLM 스텁)과 core `JAVA_TOOL_OPTIONS`를 Helm 밖에서 바꿨다가 원복했다. HPA 적용은 원복을 확인한 뒤 진행했다.

### 한계와 남은 일

- **부하 시 노드 확장·축소 실측은 하지 않았다.** HPA의 Pod 증가, Karpenter 노드 생성·등록과 그 노드에서의 RDS·RabbitMQ 통신, 부하 종료 후 정리(HPA 축소 대기 5분 + `consolidateAfter` 5분), D안 삭제 순서, ai의 CPU 기반 확장은 2차 부하 시험 #384에서 확인한다.
- 데모 중단: `demo_stack.py pause`가 NodePool `limits` 0·NodeClaim 삭제·컨트롤러 0개를 처리하고 `resume`이 되돌린다([EKS 문서](../../infrastructure/eks/README.md)). 11-06 첫 중단은 스크립트 반영 전이라 같은 단계를 kubectl로 먼저 실행했다.
- HPA·affinity values는 main에 반영돼 있다(`environments/prod/*.json`).
- t3.medium은 노드당 Pod 17개 제한이 있어 CPU·메모리보다 Pod 수 때문에 먼저 Pending이 날 수 있다.
- 후속: scoring HPA, report-worker KEDA(KEDA 설치), Spot 혼합(replica 2·PDB 이후), 컨트롤러 replica 2.

조회·적용 근거: EKS `describe-cluster`·`describe-nodegroup`·`list-pod-identity-associations`·`describe-addon-versions`·`describe-addon-configuration`, EC2 `describe-subnets`·`describe-security-groups`·`describe-instances`·`describe-images`·`describe-instance-type-offerings`·`describe-spot-price-history`, SSM `get-parameter`(EKS AL2023 AMI), Pricing `get-products`, kubectl node·Pod·HPA·NodePool·EC2NodeClass 상태와 Karpenter 로그, Helm `get values`·`get manifest`·`template`·`--dry-run=server`. Secret 값은 조회하지 않았다.
