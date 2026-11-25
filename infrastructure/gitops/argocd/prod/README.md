# prod(EKS) Argo CD 진입점 (#855)

운영(EKS) 배포를 Argo CD로 옮기는 에픽 #859의 바탕이다. Argo CD 자체는 손으로 1회 Helm 설치하고, 그 뒤로는 이 폴더의 root app이 `main` 브랜치를 따라 플랫폼·앱 Application을 자동 동기화한다. 결정과 근거는 [infra 9.18.1](../../../../docs/report/infra.md#9181-argo-cd-설치-값과-진입점-855-2026-11-20).

| 파일 | 내용 | 적용 |
|---|---|---|
| [`../../environments/prod/argocd.json`](../../environments/prod/argocd.json) | argo-cd chart 10.11.7(Argo CD v3.5.7) values. dex·HA 끔, `application` 노드그룹 고정, 작은 자원 요청, Application health 확인, Discord 알림 | `helm install` 1회 |
| `project.yaml` | AppProject `sagomungchi-prod`. 출처는 이 저장소·ESO·LB Controller·Karpenter chart 저장소, 대상은 `argocd`·`app`·`platform`·`observability`·`external-secrets`·`kube-system` | `kubectl apply` 1회 |
| `root-app.yaml` | app-of-apps `sagomungchi-prod-root`. `main`의 `platform/*.yaml`(#856)과 `apps/*.yaml`(#857)만 읽음. 자동 동기화(prune 끔, selfHeal 켬) | `kubectl apply` 1회 |
| `platform/`, `apps/` | 하위 Application(#856·#857). 폴더가 비어 있어도 root app은 리소스 0개로 Synced | Git 병합 → 자동 동기화 |

- 저장소가 public이라 저장소 자격 증명은 없다. Argo CD가 클러스터 안에서 GitHub를 주기적으로(기본 120초 + 최대 60초 jitter) 읽으므로 EKS API 공개 접근 제한과 무관하다.
- Argo CD 자체는 root app이 관리하지 않는다(버전 변경도 손으로 `helm upgrade`). Ingress는 만들지 않고 `kubectl port-forward`로만 접속한다.
- 하위 Application은 `project: sagomungchi-prod`, `metadata.namespace: argocd`로 쓴다. root app은 `argocd` namespace에 Application을 만들 수 있으므로 하위 파일의 project 값은 PR 리뷰로 확인한다. AppProject는 하위 Application이 만들거나 바꿀 수 없다(`namespaceResourceBlacklist`).
- 하위 Application 순서는 `argocd.argoproj.io/sync-wave` 주석으로 정한다(플랫폼은 `"10"`보다 작은 값, 앱 ApplicationSet `"10"`, 에픽 #859 계약). `argocd.json`의 `resource.customizations.health.argoproj.io_Application`이 하위 Application의 health를 root app에 올려 주므로 앞 wave가 Healthy가 될 때까지 다음 wave를 시작하지 않는다(Argo CD 1.8부터 기본으로 꺼져 있음).

## 설치 (B 런북 7단계 앞, A는 11/25 재가동 때 먼저)

PowerShell 7, 저장소 루트. 모든 명령에 전용 kubeconfig를 쓴다. 클러스터(B 런북 6단계)와 자원 값 교체 PR(6a, A는 main 값 그대로)이 끝난 뒤 한다.

```powershell
$kubeconfig = '<EKS kubeconfig 절대 경로>'
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update argo
helm install argocd argo/argo-cd --version 10.11.7 -n argocd --create-namespace `
  --kubeconfig $kubeconfig -f infrastructure/gitops/environments/prod/argocd.json --wait --timeout 10m
kubectl --kubeconfig $kubeconfig -n argocd get pods   # 6개 Running(controller·repo-server·server·redis·applicationset·notifications)
```

알림 Secret(값은 저장소 밖 파일에서 읽고 출력하지 않는다). Discord 채널은 Grafana 경보와 같은 `aws-alerts`지만 **webhook은 Argo CD 전용**이다. 원본은 Secrets Manager `sagomungchi/demo/argocd/discord-webhook`의 `DISCORD_WEBHOOK_URL`이고, Grafana용 `observability/discord-alert-webhook`(원본 `sagomungchi/demo/observability/discord-webhook`) 값을 쓰지 않는다. 이유는 아래 "webhook URL이 로그에 남음"을 본다. 파일 끝에 줄바꿈을 넣지 않는다.

```powershell
kubectl --kubeconfig $kubeconfig -n argocd create secret generic argocd-notifications-secret `
  --from-file=discord-webhook-url='<저장소 밖 webhook URL 파일>'
```

진입점 적용(AppProject를 먼저):

```powershell
kubectl --kubeconfig $kubeconfig apply -f infrastructure/gitops/argocd/prod/project.yaml
kubectl --kubeconfig $kubeconfig apply -f infrastructure/gitops/argocd/prod/root-app.yaml
kubectl --kubeconfig $kubeconfig -n argocd get applications   # sagomungchi-prod-root Synced, 하위 Application 생성
```

## 접속과 admin 비밀번호

argocd CLI v3.5.7은 [GitHub 릴리스](https://github.com/argoproj/argo-cd/releases/tag/v3.5.7)의 `argocd-windows-amd64.exe`를 받아 `cli_checksums.txt`로 SHA256을 확인한다. 초기 비밀번호는 화면에 출력하지 않고 변수로만 쓴다.

```powershell
# 다른 창에서 유지
kubectl --kubeconfig $kubeconfig -n argocd port-forward svc/argocd-server 8080:443

$pw = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(
  (kubectl --kubeconfig $kubeconfig -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}')))
argocd login localhost:8080 --username admin --password $pw --insecure --grpc-web
argocd account update-password --current-password $pw   # 새 비밀번호는 프롬프트로 입력, 저장소 밖에 보관
Remove-Variable pw
kubectl --kubeconfig $kubeconfig -n argocd delete secret argocd-initial-admin-secret
```

웹 UI는 `https://localhost:8080`(자체 서명 인증서). Discord 알림의 Argo CD 주소도 이 port-forward 주소다.

## 알림

`argocd.json`의 기본 구독이 모든 Application(root·플랫폼·앱)에 대해 Discord로 보낸다.

| trigger | 조건 | 중복 방지 |
|---|---|---|
| `on-sync-succeeded` | 동기화 작업 `Succeeded` | 같은 revision 1회 |
| `on-sync-failed` | 동기화 작업 `Error`·`Failed` | 같은 revision 1회 |
| `on-health-degraded` | health `Degraded` | 상태가 바뀔 때 1회 |

설치 확인 때는 하위 Application이 없어 자동 동기화 작업이 생기지 않으므로 root app을 한 번 손으로 동기화해 알림 1건을 받는다.

```powershell
argocd app sync sagomungchi-prod-root --grpc-web
# 로그를 그대로 출력하지 않는다(아래 참고). URL을 가린 뒤 오류 줄만 본다
$log = kubectl --kubeconfig $kubeconfig -n argocd logs deploy/argocd-notifications-controller
($log | Select-String 'discord.com/api/webhooks').Count   # 보낸 알림 수와 같으면 정상
$log -replace 'https://discord(app)?\.com/api/webhooks/\S+', '<webhook>' | Select-String 'error' | Select-Object -Last 20
Remove-Variable log
```

### webhook URL이 로그에 남음 (#1003)

notifications-controller는 webhook 알림을 보낼 때마다 `2026/11/24 11:36:51 [DEBUG] POST https://discord.com/api/webhooks/<id>/<token>` 한 줄을 남긴다. 로그 수준·형식 설정으로 끌 수 없다.

- 원인: notifications-engine(v3.5.7이 쓰는 커밋 `0cff13b8a717`)의 webhook 서비스가 `go-retryablehttp` v0.7.8 `NewClient()`를 기본값 그대로 쓴다. 기본 Logger가 Go 표준 `log`라 Argo CD 로거(`notificationscontroller.log.level`·`log.format`)를 거치지 않고 요청마다 메서드와 URL을 찍는다. URL에서 가리는 것은 비밀번호 부분뿐이라 경로의 토큰은 그대로 나온다. webhook 서비스 옵션에는 Logger를 바꾸는 칸이 없고 upstream 최신 코드도 같다.
- 전송이 실패하면 오류 메시지(`request to {… URL} has failed …`)에도 URL이 들어간다.
- 대응: Argo CD 전용 webhook을 쓴다. 로그를 볼 수 있는 사람이 이 값을 알게 되더라도 Grafana 경보 webhook은 그대로이고, Argo CD 값만 따로 재발급하면 된다. Pod 로그는 클러스터 밖으로 모으지 않는다(Loki·Fluent Bit·CloudWatch 로그 수집 없음). 노드의 컨테이너 로그와 `pods/log` 권한(클러스터 관리자)으로만 볼 수 있다.
- 로그를 이슈·PR·메신저에 붙이지 않는다. 볼 때는 위 명령처럼 건수만 세거나 URL을 가린다. 값이 밖으로 나갔으면 Discord에서 Argo CD webhook을 재발급하고 `sagomungchi/demo/argocd/discord-webhook`과 `argocd-notifications-secret`을 바꾼 뒤 `kubectl -n argocd rollout restart deploy/argocd-notifications-controller`.

## 확인 (A 11/25, B 11/26~28)

1. Pod 6개 Running, 모두 `application` 노드그룹 노드에 배치(`kubectl get pods -n argocd -o wide`)
2. `sagomungchi-prod-root` Synced·Healthy, 출처 revision이 main 최신 SHA
3. Discord에 `[Argo CD prod] sagomungchi-prod-root 동기화 성공` 1건
4. 초기 admin Secret 삭제, 새 비밀번호로 로그인

되돌리기: `kubectl delete -f root-app.yaml`(하위 Application이 없을 때만) → `helm uninstall argocd -n argocd`. 하위 Application이 생긴 뒤에는 Application 삭제가 배포된 리소스까지 지울 수 있으므로 손으로 확인 뒤 한다. 막히면 기존 Helm 경로(`cd-release` deploy job·`redeploy-app.ps1`)로 첫 배포한다(12/7까지 유지).
