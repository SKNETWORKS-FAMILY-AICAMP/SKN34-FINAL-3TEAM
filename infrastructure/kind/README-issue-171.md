# #171 전용 kind 검증 환경

`issue-171-verification.yaml`은 기존 `sagomungchi-local`과 다른 클러스터·API 포트(16443)·HTTP/HTTPS 호스트 포트(18080/18443)·Pod/Service CIDR를 지정한다. Calico 설치에는 같은 Pod CIDR의 `calico-issue-171-installation.yaml`을 사용한다. 이미지와 Calico/Ingress 버전은 기존 [kind 기준](README.md)과 같다. 기존 클러스터와 PVC·Secret·네트워크를 재설정하거나 삭제하지 않는다.

사용자와 무거운 검증 실행 시점을 조율한 뒤 현재 Docker 네트워크·포트·메모리·디스크 여유를 다시 읽는다. #171 노드에 쓸 별도 Docker bridge 이름은 `kind-issue171`으로 한다. kind의 `KIND_EXPERIMENTAL_DOCKER_NETWORK`는 [공식 소스에서도 미지원 실험 기능](https://github.com/kubernetes-sigs/kind/blob/main/pkg/cluster/internal/providers/docker/provider.go)이므로, 실제 생성 전에 현재 kind 버전에서 지원되는지와 네트워크 충돌 여부를 확인한다. 실패하면 기존 공유 네트워크를 수정해 우회하지 않고 검증 환경 계획을 다시 정한다.

기동 전 검증 대상:

- `kind-sagomungchi-issue171` context와 `sagomungchi-issue171-control-plane` 노드가 없는지 확인
- 16443·18080·18443·19000 포트와 Docker subnet이 사용 중인지 확인
- 플랫폼 Secret과 앱 Secret은 이 **전용 클러스터**에만 새 테스트 값으로 생성. 사용자가 허락한 동일한 테스트 계정 원본을 `platform`·`app` namespace에서 각각 참조하고 기존 클러스터의 값을 읽거나 복사하지 않음
- 앱 이미지는 `:local`로 빌드한다. Docker의 다중 플랫폼 캐시 이미지에서는 `kind load docker-image`가 누락 digest로 실패했으므로 `docker image save --platform linux/amd64 -o <임시 archive> <이미지:local>` 뒤 `kind load image-archive <임시 archive> --name sagomungchi-issue171`로 전용 클러스터에만 로드하고 archive를 지운다
- Helm·kubectl 명령은 모든 호출에 `--kube-context kind-sagomungchi-issue171` 또는 `--context kind-sagomungchi-issue171`을 명시. Argo CD와 KEDA는 앱보다 먼저 설치

한 번에 전체 앱·모델·관측을 기동할 메모리 예산은 검증되지 않았다. platform → migration/core·learning → 나머지 API → worker/KEDA → 관측 순으로 자원을 측정하고, 자원 부족을 임의의 Ready 응답으로 감추지 않는다. 전용 클러스터 정리는 직접 만든 이름의 자원만 대상으로 하며 별도 요청 없이 기존 `sagomungchi-local`을 중단하지 않는다.

Secret은 새 테스트 값만 적은 파일을 Git 밖에 준비한 뒤 `pwsh -File infrastructure/kind/create-issue-171-secrets.ps1 -EnvFile <절대 경로>`로 생성한다. 키 목록은 `issue-171-secrets.env.example`에 있다. 스크립트는 context 이름과 노드 이름을 검사하고, 값은 kubectl의 UTF-8 stdin으로만 전달한다. 전용 클러스터의 세 Secret이 이미 있으면 값을 대조하고 불일치 시 덮어쓰지 않는다. 첫 검증에서 세 Secret을 전용 클러스터에 준비했고 원본 값 파일은 제거했다. 현재 자원·남은 검증 범위는 `docs/report/issue-171-app-deployment.md`를 따른다.
