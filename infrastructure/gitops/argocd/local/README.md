# #171 local Argo CD applications

`root-app.yaml` registers the six `app-service` releases, local KEDA, local platform NetworkPolicy, and a metrics-only observability release. All Git sources pin `develop`. The target is the single local kind cluster `sagomungchi-local` ([kind setup](../../../kind/README.md)). To check an unmerged branch, use a temporary local copy whose Git `targetRevision` fields point at the pushed branch commit, and do not commit that copy.

Argo CD itself is a prerequisite in namespace `argocd`. The root app has no automated sync. Sync in this order after preparing the cluster and its credentials (`create-platform-secret.ps1`, then `create-app-secrets.ps1`, both reading the root `.env`):

1. Existing `platform-data` chart; verify Postgres, RabbitMQ definitions and MinIO initialization.
2. `local-keda` Application; verify its CRDs and operator. The `report-worker` ScaledObject cannot be applied before this.
   KEDA 2.21's `scaledjobs.keda.sh` CRD exceeds the client-side apply annotation limit. This local Application enables server-side apply and uses the chart's CRD-only `Replace=true` annotation so Argo CD 3.5 can create that CRD. Check CRD compatibility before upgrading KEDA; this setting is limited to the disposable local environment.
3. `local-platform-network` after platform initialization; verify allowed and denied paths before app traffic.
4. `local-observability` after the `observability-credentials` Secret exists. Sync optional `local-metrics-server` only for HPA verification; its kubelet TLS bypass is restricted to the disposable kind cluster.
5. Six app Applications after local images have been loaded and `app/app-service-credentials` exists. Core and learning migrations use dedicated Flyway images; report uses the report image's Alembic command.

No Application updates `.github/workflows`, publishes images, approves production deployment, or manages EKS resources. Those are #186 and #185. Local app values are resource-limited starting points, not evidence that the full platform, apps, model and observability can run together within the current Docker limit. A named PreSync migration Job runs for a new `migration.revision`; failed migrations block sync and are not ignored.

For HPA/PDB verification, apply `infrastructure/kind/hpa-check-values.yaml` over **one** API service's local values, after metrics-server reports CPU metrics. The regular local Argo applications keep HPA/PDB off to avoid scaling the whole stack on the 7.62GiB Docker allocation. The worker uses KEDA instead.
