# 로컬 kind 클러스터 기준과 설치 절차

[이슈 #17](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/17)의 클러스터 설정이다. [아키텍처](../../docs/design/architecture.md#41-환경-구분)와 [자원 설계](../../docs/report/local-platform-resource-plan.md)를 따른다.

## 클러스터에 사용할 값

| 항목 | 확정한 기준 | 연결되는 설정 |
|---|---|---|
| 이름 / context | `sagomungchi-local` / `kind-sagomungchi-local` | 모든 kubectl·Helm 명령에서 context 명시 |
| 노드 | Linux control-plane 1개에서 workload도 실행 | 저장소별 replica 1개 |
| kind / Kubernetes | v0.33.0 / v1.35.8 | `local.yaml`의 공식 node image digest 고정 |
| IP 체계 / kube-proxy | IPv4 / iptables | Calico의 지원 방식 사용 |
| Pod 대역 | `10.244.0.0/16` | `calico-installation.yaml`의 IP pool과 동일 |
| Service 대역 | `10.96.0.0/12` | Pod·호스트·Docker 대역과 중복 금지 |
| API 진입 | `127.0.0.1:6443` | API server 주소·포트 고정 |
| HTTP / HTTPS 진입 | `127.0.0.1:80`, `127.0.0.1:443` | kind 포트 매핑과 controller hostPort 일치 |
| 노드 라벨 | `ingress-ready: "true"` | controller nodeSelector와 일치 |
| CNI | Calico v3.33.0, 기본 CNI 비활성 | Kubernetes 1.35용 CRD 설치 분기 사용 |
| Calico native v3 API | `MutatingAdmissionPolicy` feature gate와 beta API 활성화 | Kubernetes 1.35에서 기본 비활성인 admission 정책 API 제공 |
| Ingress | chart 4.15.1 / controller v1.15.1 | `ingress-nginx-values.yaml`, class `nginx` |
| Helm | v4.3.1 | Kubernetes 1.35가 공식 지원 범위에 포함 |
| kubectl | 기준 PC의 v1.36.1 사용 가능 | 서버 1.35와 한 minor 차이 허용 |

버전 표는 공식 문서의 호환 범위를 대조한 결과이며 이 조합의 실제 기동 성공을 의미하지 않는다. ingress-nginx를 유지한다는 사용자 결정을 반영했다. chart를 고정하면 기본 controller·admission 이미지와 digest도 해당 chart 버전의 정의를 사용한다. 고정 버전은 의도적인 업데이트 때 함께 검토한다.

## 2026-10-26 기준 PC의 사전 확인

| 조사 대상 | 확인한 대역·상태 |
|---|---|
| Windows Wi-Fi | `192.168.0.0/24` |
| WSL 인터페이스와 Docker Desktop Linux 경로 | `172.17.16.0/20` |
| Docker bridge | `172.17.0.0/16` |
| 기존 Docker 프로젝트 네트워크 | `172.18.0.0/16`, `172.19.0.0/16` |
| 후보 Pod / Service 대역 | 서로 및 위 대역과 중복 없음 |
| Windows 활성 IPv4 경로 | 두 후보 대역으로 향하는 별도 VPN 경로는 관찰되지 않음 |
| TCP 80·443·6443 | LISTEN 없음, Windows 예약 범위에도 포함되지 않음 |

기본 경로 `0.0.0.0/0`는 모든 주소를 포함하므로 중복 판정 대상에서 제외한다. loopback·link-local·multicast 등은 Pod·Service 대역 후보와 구분한다. 기존 WSL·Docker 대역 자체의 관계를 수정하는 작업은 수행하지 않았다.

이 결과는 현재 연결된 네트워크 기준이다. 같은 PC 사양이어도 다른 Wi-Fi·VPN·Docker 네트워크를 사용하면 다시 확인한다. kind가 새로 만드는 Docker `kind` 네트워크의 subnet도 생성 후 확인한다. 기존 Docker 네트워크를 삭제하거나 새 대역으로 강제 재생성하지 않는다.

Windows에서 다시 확인할 명령:

```powershell
Get-NetIPAddress -AddressFamily IPv4
Get-NetRoute -AddressFamily IPv4
docker network ls
# 위 목록의 ID를 대상으로 docker network inspect <ID> 실행
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in @(80,443,6443) }
netsh interface ipv4 show excludedportrange protocol=tcp
```

## 설치 전 준비

- Docker Desktop Linux Engine과 WSL 2가 필요하다. kind v0.33.0·Helm v4.3.1의 Windows amd64 공식 배포 파일과 checksum을 확인해서 도구를 준비한다.
- Secret 준비 스크립트는 PowerShell 7 이상이 필요하며 Windows 기본 PowerShell 5.1에서는 실행할 수 없다. 미설치 시 `winget install --id Microsoft.PowerShell --source winget`으로 설치하고 새 터미널에서 `pwsh --version`으로 7 이상인지 확인한다. 스크립트는 아래 절차의 `pwsh -File` 명령으로 실행한다. [공식 설치 안내](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows)를 따른다.
- 기존 `sagomungchi-local` 클러스터·context가 있으면 생성 명령을 실행하기 전에 소유권과 상태를 확인한다. 삭제·덮어쓰기해서 진행하지 않는다.
- [자원 설계](../../docs/report/local-platform-resource-plan.md)의 메모리·디스크 여유를 확보한다. 다른 작업의 컨테이너·WSL·프로그램을 자동으로 중단하거나 데이터를 정리하지 않는다.
- 아래 명령은 저장소 루트에서 실행한다. API·HTTP·HTTPS는 loopback에서만 노출한다. 다른 PC·모바일 기기 접근은 별도 요구사항과 설계가 필요하다.

## 실제 설치 순서

### 1. kind 생성

```powershell
kind create cluster --config infrastructure/kind/local.yaml
```

기본 CNI를 껐으므로 이 시점의 Node NotReady와 CoreDNS 미준비는 Calico 설치 전 상태일 수 있다. Calico 설치 전에 전체 Node Ready를 기다리는 옵션으로 절차를 막지 않는다.

### 2. Calico 설치

Kubernetes 1.35는 Calico 공식 안내의 `v3_projectcalico_org-v1beta1.yaml` 분기를 사용한다. native v3 CRD의 기본값 처리를 위해 kind 설정에서 `MutatingAdmissionPolicy` feature gate와 `admissionregistration.k8s.io/v1beta1` API를 활성화한다. CRD와 Operator를 준비한 뒤, 기본 `192.168.0.0/16` 예시 대신 저장소의 Installation으로 Pod 대역을 지정한다. `APIServer` 리소스는 native v3 모드의 검증 webhook을 준비하며, Goldmane·Whisker 관측 UI는 추가하지 않는다.

```powershell
kubectl --context kind-sagomungchi-local create -f https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/v3_projectcalico_org-v1beta1.yaml
kubectl --context kind-sagomungchi-local create -f https://raw.githubusercontent.com/projectcalico/calico/v3.33.0/manifests/tigera-operator.yaml
kubectl --context kind-sagomungchi-local wait --for=condition=Established crd/installations.operator.tigera.io --timeout=120s
kubectl --context kind-sagomungchi-local apply -f infrastructure/kind/calico-installation.yaml
kubectl --context kind-sagomungchi-local wait --for=condition=Ready nodes --all --timeout=300s
```

최초 설치에 사용하는 `create` 명령이다. 재실행 중 AlreadyExists·연결 오류가 나면 기존 자원과 버전을 확인하고, 오류를 무시하는 연결 명령을 추가하지 않는다. Node Ready 외에 Calico rollout·CoreDNS·실제 NetworkPolicy 동작은 최종 검증에서 별도로 확인한다.

### 3. ingress-nginx 설치

```powershell
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update ingress-nginx
helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx --version 4.15.1 --namespace ingress-nginx --create-namespace --kube-context kind-sagomungchi-local -f infrastructure/kind/ingress-nginx-values.yaml --wait --timeout 5m
```

이 설정은 controller의 hostPort 80·443을 kind 노드에 연결한다. Service는 ClusterIP이고 별도의 cloud-provider-kind·LoadBalancer·NodePort를 추가하지 않는다. `publish-status-address`는 로컬 Ingress 상태 주소를 loopback으로 표시하기 위한 값이다. 뒤에서 실제 요청을 보낼 앱의 Ingress에는 `ingressClassName: nginx`를 명시한다. HTTPS 포트가 열리는 것과 신뢰할 수 있는 인증서가 구성되는 것은 별도다.

### 4. 저장소 배포와 검증으로 연결

저장소 루트에서 `pwsh -File infrastructure/kind/create-platform-secret.ps1`로 `.env`의 계정 여섯 개를 `platform` namespace의 Secret에 준비한 뒤 [platform-data 설치 절차](../gitops/charts/platform-data/README.md#설치와-확인)를 따른다.

- chart의 CIDR·Ingress class를 별도 값으로 중복 정의하지 않는다. 앱은 표준 Service DNS로 연결한다.
- 로컬 core ingress 허용 규칙은 Ingress controller의 namespace·Pod 라벨에 맞춰 작성한다. 운영 ALB의 IP 허용 조건을 그대로 복사하지 않는다.
- 최종 검증에서 Node·CNI·DNS, 실제 허용·차단 통신, HTTP 라우팅, HTTPS 처리, 저장소·Job 결과를 확인한다. 앱 미구현 상태의 임시 테스트 backend 결과와 실제 core·SSE·쿠키 검증을 구분한다.
- 볼륨은 kind 노드의 수명과 연결된다. 별도 보존 구성을 하지 않은 상태에서 클러스터를 삭제하면 데이터를 잃을 수 있다. 이 문서는 자동 삭제 절차를 제공하지 않는다.

## 로컬 자원 공유

16GB급 PC에서는 전체 Compose와 kind 실행을 분리하고, 사용하지 않는 로컬 클러스터는 노드 컨테이너를 정지해 보관할 수 있다. 다음 명령은 노드 컨테이너를 삭제하지 않으며 같은 노드를 다시 시작한다.

```powershell
docker stop --timeout 30 sagomungchi-local-control-plane
docker start sagomungchi-local-control-plane
kubectl --context kind-sagomungchi-local wait --for=condition=Ready nodes --all --timeout=180s
kubectl --context kind-sagomungchi-local -n platform get pods,jobs,pvc
```

Compose를 중단할 때 업무 데이터를 유지하려면 `docker compose down`을 사용하고 `--volumes`를 붙이지 않는다. 선택 MinIO도 실행했다면 `docker compose -f compose.yaml -f compose.minio.yaml down`으로 중단한다. 기존 데이터 볼륨의 삭제와 클러스터 삭제는 별도의 작업으로 다룬다.

## 이후 구현이 맞춰야 할 항목

| 구현 대상 | 맞춰야 하는 기준 |
|---|---|
| Calico | kind의 Pod CIDR과 동일한 IP pool |
| Ingress controller | 노드 라벨·hostPort·loopback 포트 매핑·class·자원 예산 |
| platform-data | `platform` namespace, replica 1, 기존 Secret 참조, 자원·PVC 예산 |
| RabbitMQ 초기화 | 기존 definitions 파일과 Service·Secret 연결 |
| MinIO 초기화 | 단일 MinIO 볼륨 안의 확정 버킷 세 개 |
| 후속 앱 chart | `app` namespace, `*.platform` Service DNS, 로컬 class `nginx` |
| 최종 검증 | 명시적 context 사용, 다른 프로젝트의 클러스터·Docker 데이터 보존 |

## 근거

- [kind v0.33.0과 node image digest](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0), [kind 설정](https://kind.sigs.k8s.io/docs/user/configuration/)
- [Calico 지원 버전·IP pool 조건](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements), [kind 설치의 Kubernetes 버전별 분기](https://docs.tigera.io/calico/latest/getting-started/kubernetes/kind), [v3.33.0 기본 Installation 예시](https://github.com/projectcalico/calico/blob/v3.33.0/manifests/custom-resources.yaml)
- [Calico native v3의 admission API 요구사항](https://docs.tigera.io/calico/latest/operations/native-v3-crds)
- [ingress-nginx 호환표](https://github.com/kubernetes/ingress-nginx#supported-versions-table), [chart 4.15.1 values](https://github.com/kubernetes/ingress-nginx/blob/controller-v1.15.1/charts/ingress-nginx/values.yaml)
- [Helm v4.3.1](https://github.com/helm/helm/releases/tag/v4.3.1), [Helm 지원 범위](https://helm.sh/docs/topics/version_skew/), [kubectl version skew](https://kubernetes.io/releases/version-skew-policy/#kubectl)
