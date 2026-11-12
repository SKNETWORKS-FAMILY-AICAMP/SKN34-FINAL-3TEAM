# EKS 데모 관측 구성

`cluster.json`은 현재 클러스터와 같은 eksctl `ClusterConfig`다(1.35, application 노드그룹, add-on 버전, Pod Identity). VPC·subnet ID와 공개 접근 CIDR은 placeholder이며 `infrastructure/aws/demo_stack.py render-eksctl`이 채운다. 기존 클러스터는 콘솔에서 만들어 eksctl CloudFormation stack이 없으므로, 이 파일은 **새 환경 생성과 `demo_stack.py plan`의 대조 기준**이고 기존 클러스터를 eksctl로 관리하지 않는다. `demo-observed.json`은 2026-11-03 AWS API의 선택 필드만 저장한 인벤토리다. `gp3.json`은 Kubernetes StorageClass manifest다. EKS API 공개 접근 허용 CIDR(`publicAccessCidrs`)은 작업자 공인 IP이므로 `__OPERATOR_PUBLIC_IP_n__`으로 치환했다. 실제 값은 `aws eks describe-cluster`로 확인한다.

- 계정 `347161580747`, 리전 `ap-northeast-2`, 클러스터 `sagomungchi-demo-eks`, Kubernetes 1.35.
- 관리형 노드그룹 2개, 모두 ON_DEMAND t3.medium, private subnet, 디스크 20GiB(2026-11-04 PM 결정, `cluster.json`).
  - `application`: 2대(min 2 / max 3). 앱·ESO·LB Controller·CoreDNS 등.
  - `platform-observability`: 2대 고정, label·taint `workload=platform:NoSchedule`. EBS PVC가 2a(RabbitMQ·Prometheus·Grafana)와 2b(Redis)에 있어 AZ마다 1대가 필요하다. Spot은 쓰지 않는다(회수 시 replica 1개인 상태 저장 서비스가 멈추고, EBS가 AZ에 묶여 다른 AZ로 옮길 수 없음). Spot은 #211에서 앱 노드에 조건부로 다룬다.
  - 이전 구성은 application 1개(11/03 2→3대)였다. 분리 적용 절차는 아래 "노드그룹 분리 적용"을 따른다.
- VPC CNI의 `enableNetworkPolicy=true`; CoreDNS, kube-proxy, EBS CSI, Pod Identity Agent, node monitoring add-on의 실제 버전은 JSON에 기록했다.
- public/private API endpoint 모두 활성. public CIDR은 관측 시점 작업자 IP 제한으로, 이후 접속 IP가 바뀌면 별도 접근 검토가 필요하다.
- IRSA 대신 EKS Pod Identity를 사용한다(2026-11-04 설계 반영). 클러스터별 OIDC provider와 역할마다 OIDC 주소를 넣는 trust가 필요 없고, 연결을 EKS API 한곳에서 관리해 재생성·감사가 쉽다. JSON의 namespace·ServiceAccount·roleArn 연결을 그대로 확인한다. IAM 역할·정책은 [AWS IaC](../aws/README.md#iac-eksctl--aws-cli-스크립트-185)가 정의한다.
- LB Controller는 1.14.1 chart / v2.14.1, ESO는 2.14.0 chart / v2.14.0. values는 [prod](../gitops/environments/prod/README.md)에 있다.
- Karpenter는 1.15.1 chart(OCI `public.ecr.aws/karpenter/karpenter`), kube-system, Pod Identity 역할 `sagomungchi-demo-karpenter-controller-role`. metrics-server는 EKS add-on(`cluster.json`).

## 재생성 범위

VPC·subnet·route·NAT·SG·IAM·RDS·S3·ECR은 [AWS IaC](../aws/README.md#iac-eksctl--aws-cli-스크립트-185), 클러스터는 `cluster.json`이 정의한다. 2026-11-03 `plan`에서 55개 항목이 현재 자원과 일치했다. 같은 계정에서 `apply`는 이미 있는 자원을 건너뛰며, 현재 객체를 다른 IaC가 소유하도록 import하지 않는다. 새 계정 재생성은 실행하지 않았으므로 성공을 주장하지 않는다. eksctl은 작업자 IAM 사용자의 access entry를 자동으로 만들며, 콘솔에서 만든 현재 클러스터의 `student` access entry와 같은 권한인지는 생성 후 확인한다.

노드 자동 확장은 Karpenter 1.15.1(NodePool `application-burst`, 평소 0대)과 core·learning·ai HPA로 한다(2026-11-05, [#211·#372](../../docs/report/infra.md#6-karpenter와-앱-hpa-211372)). 관리형 노드그룹 2개는 크기를 자동으로 바꾸지 않는다. `demo_stack.py pause`는 워크로드를 0으로 줄인 뒤 NodePool `limits`를 0으로 바꾸고, 남은 NodeClaim을 지운 다음 Karpenter 컨트롤러를 0개로 줄인다. 노드그룹 축소 중 Pending이 된 kube-system Pod 때문에 Karpenter 노드가 생기지 않게 하기 위해서다. `resume`은 노드 Ready 뒤 컨트롤러 replica와 NodePool `limits`를 state 파일 값(없으면 `demo-stack.json`의 `karpenter.defaults`)으로 되돌린 다음 워크로드를 복구한다. 노드를 0으로 줄여도 EKS control plane·NAT·RDS·EBS 비용은 남는다. RDS 복원 테스트와 데이터 백업을 확인하기 전 클러스터/PVC를 삭제하지 않는다.

### IAM 추가 확인 (2026-11-03)

`iam get-role`, `list-attached-role-policies`, `list-role-policies`로 Pod Identity 역할 6개와 노드 역할을 읽었다. report·scoring·ESO·LB Controller의 trust에는 클러스터 ARN·namespace·ServiceAccount 조건이 있다. EBS CSI·VPC CNI 역할은 조회 당시 조건이 없었다. 저장소의 trust 원문(`iam/eks-ebs-csi-role.trust.json`, `iam/eks-vpc-cni-role.trust.json`)에 같은 형식의 클러스터·`kube-system`·SA(`ebs-csi-controller-sa`, `aws-node`) 조건을 추가했으며, 실제 반영은 아래 적용 절차의 IAM 단계로 한다. association의 SA 연결과 trust policy 자체의 제한을 구분한다. 이번에는 IAM을 변경하지 않았으며 조건 보강은 add-on 동작과 권한 영향을 검토한 뒤 진행한다.

| 역할 (접두사 `sagomungchi-demo-`) | 확인한 권한 연결 |
|---|---|
| `report-s3-role` | inline `sagomungchi-demo-report-s3-access`: reports 버킷 reports/*의 GetObject·PutObject·DeleteObject, 해당 prefix의 ListBucket |
| `scoring-s3-role` | inline `sagomungchi-demo-scoring-s3-read`: models 버킷 ListBucket·GetObject |
| `external-secrets-role` | managed `sagomungchi-demo-external-secrets-db-read`, inline ai/app/google/rabbitmq-read 4개. 정책 본문 전체 감사는 미완료 |
| `lb-controller-role` | inline `AWSLoadBalancerController-v2-14-1`. 정책 본문 전체 감사는 미완료 |
| `eks-ebs-csi-role` | AWS managed `AmazonEBSCSIDriverPolicyV2` |
| `eks-vpc-cni-role` | AWS managed `AmazonEKS_CNI_Policy` |
| `eks-node-role` | EC2 trust, AWS managed `AmazonEKSWorkerNodePolicy`·`AmazonEC2ContainerRegistryPullOnly` |

report·scoring inline policy 본문도 조회했다. 이 두 정책에는 GetObjectVersion이 없으므로 기존 앱 역할이 과거 S3 버전 복구 권한까지 가진다고 가정하지 않는다. 클러스터 서비스 역할·access entry·조직 SCP·endpoint policy 등을 포함한 유효 권한 전체 검토와 생성 코드 보존은 남아 있다.

조회 예시:

```powershell
aws eks describe-cluster --name sagomungchi-demo-eks --region ap-northeast-2 --profile sagomungchi-provided
aws eks list-nodegroups --cluster-name sagomungchi-demo-eks --region ap-northeast-2 --profile sagomungchi-provided
aws eks list-pod-identity-associations --cluster-name sagomungchi-demo-eks --region ap-northeast-2 --profile sagomungchi-provided
```

## 노드그룹 분리 적용 (2026-11-04 결정)

application 1그룹(3대)에서 위 2그룹으로 옮기는 순서다. 상태 저장 서비스가 수 분 멈추며 데이터는 PVC에 남는다.

1. **IAM trust 보강**(작업자): EBS CSI·VPC CNI 역할 trust를 저장소 원문으로 갱신한다. Pod Identity 연결의 namespace·SA와 같으므로 add-on 동작은 바뀌지 않아야 하며, 직후 `ebs-csi-controller`·`aws-node` Pod가 정상인지 확인한다.
   ```powershell
   aws iam update-assume-role-policy --role-name sagomungchi-demo-eks-ebs-csi-role --policy-document file://infrastructure/aws/iam/eks-ebs-csi-role.trust.json --profile sagomungchi-provided
   aws iam update-assume-role-policy --role-name sagomungchi-demo-eks-vpc-cni-role --policy-document file://infrastructure/aws/iam/eks-vpc-cni-role.trust.json --profile sagomungchi-provided
   ```
2. **platform 그룹 생성**: `python infrastructure/aws/demo_stack.py --profile sagomungchi-provided apply --confirm-account 347161580747`는 없는 `platform-observability`만 만든다(private subnet 2a·2b, label·taint, 2/2/2). `aws eks wait nodegroup-active` 후 노드 2대가 Ready이고 **2a·2b에 1대씩**인지, taint가 붙었는지 확인한다. 한 AZ에 몰리면 다음 단계로 가지 않는다.
3. **이동 준비**: RabbitMQ 미처리 메시지가 0인지 확인한다(`pause` dry-run의 pending queues). 리포트 생성 등 진행 중 작업이 없을 때 한다.
4. **이동**: `platform-data`(platform)·`observability`(observability)를 prod values로 `helm upgrade`한다. RabbitMQ·Redis는 StatefulSet 순차 재시작, Prometheus·Grafana는 `Recreate`라 PVC 다중 연결 충돌이 없다. 새 Pod가 platform 노드에 뜨고 PVC가 Bound, RabbitMQ 큐·Redis 데이터·Grafana 로그인이 유지되는지 확인한다. 문제가 있으면 이전 revision으로 `helm rollback`한다(이전 노드는 아직 남아 있음).
5. **application 축소**: 줄이기 전에 **노드별로** 남는 노드의 여유 메모리가 옮겨 갈 Pod 중 가장 큰 예약(현재 scoring 1Gi)보다 큰지 확인한다. 총량 합계로 판단하지 않는다. 지울 노드를 `kubectl drain`으로 비운 뒤 `aws autoscaling terminate-instance-in-auto-scaling-group --should-decrement-desired-capacity`로 그 인스턴스만 종료하고, 노드그룹을 min 2 / desired 2 / max 3으로 맞춘다(크기만 줄이면 임의 노드가 종료된다).
6. **확인**: `demo_stack.py plan`(nodegroup 2개 OK), 앱 6개 Ready, CloudFront 로그인→학습 제출→리포트, Grafana 경보 상태.

### 적용 결과 (2026-11-04 11:22~12:05 KST)

- EBS CSI·VPC CNI trust 갱신 후 controller 재시작과 새 노드의 aws-node가 정상(권한 오류 0).
- `platform-observability` 2대 생성(2a·2b 1대씩, taint 확인). RabbitMQ·Redis·Prometheus·Grafana·Collector를 이동했고 PVC 재연결, RabbitMQ 큐 32개·연결 5개 유지, 앱 재시작 0. RabbitMQ 초기화 Job은 같은 정의로 한 번 재실행됐다(chart 파일 해시 차이로 이름 변경).
- application 첫 축소 때 scoring(예약 2Gi)이 남은 노드(여유 1.8~1.9Gi)에 들어가지 못해 약 5분 Pending이었다. 3대로 되돌려 복구했다. 실측(합성 논술 3회 추론) working set 629MiB, 프로세스 414MiB, 캐시 포함 최고 1,195MiB라 예약을 1Gi(상한 2Gi 유지)로 낮추고 재배포했다. 이후 빈 노드를 지정해 종료하고 2/2/3으로 맞췄다.
- 최종: application 2대 + platform-observability 2대, 앱 6개 Ready, CloudFront 200, `demo_stack.py plan` 57/57.

## 데모 종료·축소·재개 실행안 (#185)

2026-11-03 작성한 **미실행 계획**이다. 아래 정상 종료·재개 순서는 `python infrastructure/aws/demo_stack.py pause|resume --kubeconfig <파일> --state <저장소 밖 파일>`로 자동화했다. 기본은 현재 상태와 단계만 출력하고(2026-11-03 dry-run 확인), `--execute --confirm-account 347161580747`일 때만 RabbitMQ 미처리 메시지 확인 → 워크로드 0 → RDS·EBS snapshot → 노드그룹 0/0/3 → RDS 정지를 실행한다. resume은 저장한 replica·노드 수로 되돌린다. 유입 차단·Grafana silence는 스크립트에 없으므로 작업자가 먼저 처리한다. 현재 노드그룹·Pod Identity 구조를 바꾸지 않는다. 서비스 중단 일시·재개 일시·실행 담당·백업 보관 위치를 기록한 뒤 실행하며, 이번 문서 정리만으로 노드 축소·RDS 정지·자원 삭제를 실행하지 않는다.

### 선택지와 남는 비용

| 선택지 | 가용성·복구 영향 | 줄어드는 비용 | 계속 발생하는 비용 |
|---|---|---|---|
| 현재 2노드 유지 | 데모 계속 사용 가능 | 없음 | 현재 자원 비용 |
| 앱 replica만 0 | API 중단, 노드·기반 구성 유지 | LLM 호출 등 사용량 감소 가능 | EC2·EKS·NAT·ALB·RDS·저장소 등 고정 비용은 유지 |
| 워크로드 정상 종료 후 노드 0 + RDS 일시 정지 | 전체 API 중단. 데이터와 클러스터 메타데이터를 보존하고 재개 | 워커 EC2 인스턴스 시간, 정지 상태 RDS 인스턴스 시간 | EKS control plane·NAT·ALB·EBS/PVC·RDS 저장소/백업·S3·ECR·Secrets Manager·로그·공인 IPv4 및 해당 사용량 |
| 클러스터·NAT 등 철거 후 재생성 | 복원·주소 변경·OAuth 재설정 필요. 현재 재생성 준비 미완료 | 실제 삭제한 자원의 시간 요금 | 보존한 snapshot·S3·ECR·Secret·로그·미해제 EIP 등 |

단기 휴지에는 데이터·클러스터를 유지하는 세 번째 안을 검토한다. **운영 중 노드를 2→1로 줄이는 것은 이번 권장안이 아니다.** 현재 앱 예약량과 AZ별 PVC 때문에 한 노드에 정상 배치된다는 근거가 없다. 노드 0은 서비스를 유지하는 축소가 아니라 계획된 전체 중단이다.

RDS 정지는 최대 연속 7일이며 이후 자동 재시작한다. 정지 중에도 저장소·백업 비용은 남고 재시작은 수분~수시간 걸릴 수 있다. 재개 시간을 보장하거나 일주일 이상 정지 비용이 유지된다고 계산하지 않는다. [AWS RDS 정지 문서](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_StopInstance.html)

NAT는 정지 버튼이 있는 자원이 아니다. 시간 요금을 없애려면 삭제가 필요하지만 재생성·라우팅 복구와 외부 호출 장애가 따르므로 단기 휴지에서는 유지한다. 삭제해도 EIP가 자동 해제되지 않을 수 있다. [AWS NAT 관리](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateway-working-with.html)

월 절감액을 아직 측정하지 않았다. 실행 전 실제 리전 단가·지원 요금 구간·약정/크레딧·정지 시간을 기준으로 `워커 인스턴스 시간 감소 + RDS 인스턴스 시간 감소 - 추가 snapshot/보관 비용`을 계산한다. 전체 청구액을 0으로 표시하지 않는다.

### 종료 전 보존 목록

- Git SHA·미커밋 변경 보관, 앱/migration 이미지 digest·ECR 존재, 웹 build 산출물·S3 version ID, Helm release revision·비밀을 제외한 values, Deployment/StatefulSet replica 수와 nodegroup min/desired/max를 기록한다. 현재 application은 2/2/2(목표 3/3/3), 앱 6개와 RabbitMQ·Redis·관측 Deployment는 각각 1 replica였으므로 실행 직전에 다시 읽는다.
- DB snapshot/PITR 범위와 복구 접근 권한, S3 버전 관리와 필요한 객체, EBS volume/snapshot ID·AZ·PVC 대응을 기록한다. RDS 자동 백업이 있다는 사실만으로 실제 복원 성공을 주장하지 않는다.
- 관측 Secret 2개는 ESO 외부 동기화 대상이 아니므로 현재 클러스터 삭제 전에 별도 안전한 보관·재주입 경로가 필요하다. Secret/Helm release 전체 YAML을 일반 파일로 내보내지 않는다.
- 관리형 노드그룹의 EC2 root disk는 종료 시 유지된다고 가정하지 않는다. 필요한 데이터가 PVC/S3/RDS 밖 노드 로컬에 없는지 확인한다.

2026-11-03 실제 PV 조회 결과는 다음과 같다. 네 PV 모두 reclaimPolicy=Delete이므로 PVC 삭제는 보존 수단이 아니다. Helm keep도 클러스터 삭제·디스크 장애의 백업을 대신하지 않는다.

| PVC | AZ | EBS volume |
|---|---|---|
| platform/data-rabbitmq-0 | ap-northeast-2a | vol-0a41b58532c1c5154 |
| platform/data-redis-0 | ap-northeast-2b | vol-0a58e2a4fd64d3dbe |
| observability/prometheus-data | ap-northeast-2a | vol-03c4e812d5045a4bb |
| observability/grafana-data | ap-northeast-2a | vol-03b9b41f992c07b4b |

### 정상 종료 순서

1. 중단 시간과 재개 담당을 확정하고 신규 로그인·학습·보고서 요청 유입을 막는다. 현재 유지보수 페이지/차단 설정은 준비돼 있지 않으므로 실행 전에 별도 수단을 정한다. CloudFront를 그대로 두면 정적 웹이 열려도 API는 실패할 수 있다.
2. 예약 작업·CronJob 및 자동 동기화/확장 controller 유무를 다시 확인하고 재기동 원인을 차단한다. 현재 Argo prod·KEDA는 미구성이고, core·learning·ai HPA와 Karpenter는 있다(#211). HPA는 replica를 0으로 줄인 Deployment를 다시 늘리지 않는다. Karpenter는 4.5단계에서 멈춘다. Grafana 외부 경보는 정해진 중단 기간만 silence하고 만료·재개 담당을 기록한다.
3. 기존 SSE·학습·AI·리포트 작업을 완료시킨다. 새 요청/생성자를 먼저 멈추되, report-worker가 호출하는 core·learning·ai와 DB/RabbitMQ는 drain 동안 유지한다. RabbitMQ ready/unacked, 실행 중 작업·outbox를 확인하고 처리 미완료 상태에서는 다음 단계로 진행하지 않는다. DLQ는 성공 큐처럼 비우거나 삭제하지 않고 건수·처리 계획을 보존한다.
4. worker와 앱을 정상 종료해 DB 쓰기·큐 소비가 멈춘 것을 확인한다. 앱 grace period를 기다리고 노드 강제 종료로 대신하지 않는다. replica 수를 0으로 변경한 값은 임시 운영 상태로 기록하며 prod 기본값에 덮어쓰지 않는다.
4.5. Karpenter를 멈춘다. NodePool `application-burst`의 `limits`를 CPU·메모리 0으로 바꾸고, NodeClaim이 있으면 지워 Karpenter 노드를 정리한 뒤 컨트롤러를 0개로 줄인다. 원래 replica·`limits`는 state 파일에 남긴다.
5. RDS 수동 snapshot을 만들고 available을 확인한다. RabbitMQ·Redis·Grafana·Prometheus는 정상 종료 후 Pod 종료·EBS 분리를 확인하고 필요한 EBS snapshot을 만들어 completed를 확인한다. snapshot에는 별도 비용이 들며 복원 시험이 없으면 그 한계를 기록한다. Redis AOF와 RabbitMQ 메시지 보존은 정상 종료·동일 PVC 재연결을 전제로 하며 임의 PVC 삭제를 하지 않는다.
6. 데이터 보존 확인 후 두 노드그룹을 min=0, desired=0(max 유지)으로 변경한다. **EKS scaling-config 변경은 PDB를 존중하는 안전한 순차 종료로 간주하지 않는다.** 앞 단계의 워크로드 종료가 선행돼야 한다. [AWS 관리형 노드그룹 scaling 주의사항](https://docs.aws.amazon.com/eks/latest/userguide/update-managed-node-group.html)
7. 노드·워크로드 중단과 DB 연결 종료를 확인한 뒤 RDS를 일시 정지한다. status=stopped, 정지 시각과 7일 자동 재시작 확인 시점을 기록한다. 자동 재정지 작업은 이번 범위에서 만들지 않는다.
8. nodegroup·RDS 상태와 보존 자원을 재조회하고 청구 대시보드에서 남는 비용을 확인한다. 검증 증거 없이 클러스터/PVC/RDS/S3/NAT를 삭제하지 않는다.

2026-11-06 실행 기록: Karpenter 단계가 스크립트에 들어가기 전이라 NodePool `limits` 0·컨트롤러 0개를 kubectl로 먼저 적용한 뒤 `pause --execute`를 실행했다. RabbitMQ 미처리 메시지 0, RDS snapshot `sagomungchi-demo-db-pause-20261106-100937`과 EBS snapshot 4개 완료, 노드그룹 2개 0대, RDS stopped, 계정 내 실행 중 EC2 0대를 확인했다. `application` 노드 2대는 CoreDNS·EBS CSI·metrics-server PDB(허용 0) 때문에 약 15분 뒤 종료됐다. state 파일은 작업자 PC(저장소 밖)에 있다.

### 재개 순서와 완료 기준

1. NAT·라우팅·Secret·ECR·S3가 유지되는지 확인하고 RDS를 시작해 available, endpoint·TLS·백업 설정을 확인한다.
2. 두 노드그룹의 min/desired/max를 pause 때 저장한 값으로 복구한다. 노드 Ready와 VPC CNI·CoreDNS·EBS CSI·Pod Identity Agent를 확인한다. **노드 수만으로 AZ 배치가 보장되는 것은 아니다.** 2a/2b 양쪽 PVC를 연결할 수 있는 노드가 있는지 확인한다. 없으면 볼륨 affinity를 지우지 말고 해당 AZ 용량 문제를 해결한다.
2.5. Karpenter 컨트롤러를 pause 전 replica로 되돌려 Ready를 확인하고, NodePool `limits`를 pause 전 값으로 되돌린다. 2026-11-06 state 파일처럼 Karpenter 값이 없으면 `demo-stack.json`의 `karpenter.defaults`(컨트롤러 1, CPU 4·메모리 16Gi)를 쓴다.
3. ESO 동기화·LB Controller 준비, RabbitMQ·Redis StatefulSet 원래 replica 복구와 PVC 연결·데이터 보존을 확인한다. 새 PVC나 비밀번호로 대체하지 않는다. 복원 DB가 아니라 동일 DB 재개라면 seed/migration을 무조건 재실행하지 않는다.
4. core·learning·report-api 등 의존 서비스를 복구하고 scoring·ai·report-worker를 원래 replica로 복구한다. 모델·프롬프트·큐·DB 연결과 모든 앱 readiness를 확인한다. observability도 원래 replica로 복구하고 datasource·경보 평가 상태를 확인한다.
5. 외부 유입 차단을 해제하기 전에 로그인→학습 제출→리포트 조회를 확인한다. 검증 계정·횟수를 미리 정해 사용 한도와 실제 데이터 영향을 기록한다. 경보 silence를 종료하고 잔여 작업·DLQ·오류를 점검한다.
6. 실제 중단/재개 시간과 실패 항목을 기록한다. 재개는 아직 실행하지 않았으므로 RTO 달성을 주장하지 않는다. 노드/PVC/DB 복귀 실패 시 공개 재개를 보류하고 원인 해결 또는 검증된 백업 복구로 전환한다.

장기 철거는 별도 단계다. 현재 eksctl 전체 생성 설정·RDS bootstrap·Secret 복구·초기 데이터·새 환경 복원 검증이 미완료이므로 **클러스터 삭제 후 재생성 안은 지금 실행 가능한 축소안으로 취급하지 않는다.** 초기 순서는 [prod 배포 절차](../gitops/environments/prod/README.md#초기-배포-재현-절차-185)를 따른다.
