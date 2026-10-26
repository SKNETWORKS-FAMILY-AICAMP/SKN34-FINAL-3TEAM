# 이슈 #17 로컬 플랫폼 설계 변경 근거

[아키텍처](../design/architecture.md#41-환경-구분)의 로컬 Kubernetes 환경을 구체화한 설정과 근거를 기록한다. 실행 절차는 [kind](../../infrastructure/kind/README.md)·[platform-data](../../infrastructure/gitops/charts/platform-data/README.md), CPU·메모리·볼륨 값은 [자원 설계](local-platform-resource-plan.md)와 [local values](../../infrastructure/gitops/environments/local/platform-data.yaml)를 따른다.

## 환경 경계

- 로컬은 kind 단일 노드에 PostgreSQL·RabbitMQ·Redis·MinIO를 배포한다. 운영은 기존 RDS·S3 및 RabbitMQ·Redis StatefulSet 설계를 유지한다.
- 저장소 구성은 `platform-data` chart 하나로 관리하고 PostgreSQL·MinIO는 로컬 values에서 활성화한다. 앱 배포·Argo CD·관측 플랫폼·AWS 자원 생성은 이 설정의 범위에 포함하지 않는다.
- 로컬 API·HTTP·HTTPS는 loopback에 노출한다. 다른 PC·모바일 기기에서 접근하려면 별도의 진입 설계가 필요하다.

## Kubernetes·CNI·Ingress 조합

| 구체화한 내용 | 근거와 영향 |
|---|---|
| kind v0.33.0 / Kubernetes v1.35.8 | 유지하기로 한 ingress-nginx v1.15.1의 E2E 테스트 범위가 Kubernetes 1.35까지이므로 1.35 계열을 선택했다. 해당 kind 릴리스의 공식 노드 이미지 digest로 실행 내용을 고정한다. |
| Calico v3.33.0 / IPv4·iptables | Calico의 Kubernetes 1.35 테스트 범위에 맞췄다. 기본 CNI를 비활성화해 네트워크 제공자를 중복 설치하지 않는다. |
| `MutatingAdmissionPolicy` feature gate·beta API 활성화 | Calico native v3 CRD의 기본값 처리에 필요한 기능이다. Kubernetes 1.35에서 기본 비활성이므로 클러스터 생성 설정에 명시한다. `APIServer` 리소스는 이 모드에서 검증 webhook을 준비한다. |
| Pod `10.244.0.0/16`, Service `10.96.0.0/12` | 기준 PC의 Wi-Fi·WSL·Docker 대역과 겹치지 않는 값을 선택했다. Calico 기본 예시 `192.168.0.0/16`은 기준 Wi-Fi 대역을 포함하므로 사용하지 않는다. Pod 대역과 Calico IP pool을 동일하게 관리하고 다른 네트워크에서는 중복 여부를 다시 확인한다. |
| ingress-nginx controller v1.15.1 / chart 4.15.1 | 이슈에 지정한 controller를 로컬에서 유지한다. 프로젝트 유지보수 종료 상태를 전제로 버전을 명시적으로 고정하며, 버전 고정이 보안 패치 제공을 의미하지는 않는다. 운영의 AWS Load Balancer Controller·ALB 설계는 변경하지 않는다. |

## MinIO 이미지와 버킷

기존 설계는 로컬 S3 대역으로 MinIO를 지정하지만 이미지 배포처와 버킷 이름은 정하지 않았다. 커뮤니티판의 소스 전용 배포 전환을 고려해 로컬 서버에는 사전 빌드된 Chainguard 공개 이미지를 사용한다. linux/amd64 digest를 [공통 values](../../infrastructure/gitops/charts/platform-data/values.yaml)의 `minio.image`에 고정하며 별도 소스 빌드·이미지 배포 계층을 추가하지 않는다. 이미지 업데이트는 digest를 의도적으로 바꾸는 방식으로 수행한다.

서버 이미지에 shell·curl이 있다고 가정하지 않는다. 버킷 초기화는 RabbitMQ 초기화에도 사용하는 `curlimages/curl:8.17.0`에서 S3 SigV4 요청으로 수행한다. 인증은 curl 설정 stdin으로 전달하고 명령 인자·로그에 비밀번호를 넣지 않는다. 기존 버킷을 소유한 경우에만 재실행 성공으로 처리하며 다른 오류는 실패로 남긴다.

| 버킷 | 분리 이유 |
|---|---|
| `sagomungchi-local-missions` | learning이 관리하는 미션 장면 파일을 구분한다. |
| `sagomungchi-local-reports` | 학부모 권한 확인 후 제공할 리포트 파일을 구분한다. |
| `sagomungchi-local-models` | 모델 버전별 가중치와 추론 서비스의 사용 범위를 구분한다. |

세 버킷은 단일 MinIO Pod·2Gi PVC를 공유한다. 버킷 분리 자체가 앱의 사용자별 권한 검사를 대체하지 않으며, 버킷별 정책은 실제 소비 서비스의 요구와 함께 적용한다. 운영 S3 이름과 정책은 AWS 자원 작업에서 별도로 확정한다.

## 초기화와 자격 증명

- RabbitMQ 계정을 먼저 기동한 뒤 Job이 관리 API로 기존 `definitions.json`을 반영한다. 계정을 JSON에 기록하지 않으면서 default-user 생성과 definitions 로딩 순서를 분리하기 위한 선택이다.
- 큐·exchange·binding과 재시도 단계는 기존 JSON만 기준으로 사용한다. `default_queue_type`을 전역 quorum으로 강제하지 않아 Pod별 exclusive 브로드캐스트 큐와 충돌하지 않도록 한다.
- PostgreSQL의 `init.sql`·RabbitMQ의 `definitions.json`은 원래 위치에 보존하고 Helm `.Files`와 Compose 마운트가 같은 파일을 읽는다. 추가 초기화 스크립트도 두 실행 경로가 공유한다.
- `.env`에서 PostgreSQL·RabbitMQ·MinIO의 여섯 계정 키만 `platform/platform-data-credentials` Secret으로 준비한다. 기존 Secret과 값이 다르면 자동 덮어쓰지 않는다. 환경 변수 변경만으로 기존 DB·브로커 계정이 회전되지 않기 때문이다.
- 활성 저장소의 requests·limits와 필수 설정이 없으면 렌더링을 중단한다. 저장소·초기화 실패를 임의 데이터나 정상 응답으로 대체하지 않는다.

## 데이터 보존과 자원 운영

StatefulSet·PVC로 프로그램 실행과 데이터를 분리하고, StatefulSet 삭제·축소 시 PVC를 보존한다. 이는 kind 노드 자체의 삭제로부터 데이터를 보호하는 설정은 아니다. 로컬 provisioner에서는 PVC 용량 요청이 실제 디스크 quota를 강제하지 않을 수 있으므로 호스트 여유 공간도 확인한다.

4코어·8스레드·16GB급 PC의 플랫폼 메모리 계획 예산은 약 6GiB다. 앱·모델 추론·관측 도구와 동시 실행 가능한 용량을 보장하는 값은 아니다. 전체 Compose와 kind 실행은 분리하고, 미사용 kind 노드는 삭제하지 않고 정지해 보관할 수 있다. Compose의 MinIO 볼륨 준비 단계는 해당 볼륨 루트의 소유권만 서버 사용자에 맞추며 기존 파일을 삭제하지 않는다.

## 근거

- [ingress-nginx 지원 버전](https://github.com/kubernetes/ingress-nginx#supported-versions-table), [종료 공지](https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/), [kind v0.33.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0)
- [Calico Kubernetes 요구사항](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements), [native v3 CRD·admission 정책 조건](https://docs.tigera.io/calico/latest/operations/native-v3-crds)
- [MinIO 커뮤니티 배포 방식](https://github.com/minio/minio#source-only-distribution), [Chainguard MinIO 배포본](https://images.chainguard.dev/directory/image/minio/overview), [curl SigV4](https://curl.se/docs/manpage.html#--aws-sigv4)
