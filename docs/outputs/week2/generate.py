"""2주차 시스템 구성도 PNG 생성.

실행: uv run --no-project --with diagrams python docs/outputs/week2/generate.py
필요: Graphviz(dot) PATH 등록. 기준 문서: docs/design/architecture.md, docs/design/api-spec.md 4장
"""

import os
from pathlib import Path

from diagrams import Cluster, Diagram, Edge, Node
from diagrams.aws.compute import EC2, ECR, EKS, EC2SpotInstance
from diagrams.aws.database import RDSPostgresqlInstance
from diagrams.aws.general import Users
from diagrams.aws.network import ALB, CloudFront, InternetGateway, NATGateway
from diagrams.aws.security import IAM, SecretsManager
from diagrams.aws.storage import ElasticBlockStoreEBSVolume, SimpleStorageServiceS3
from diagrams.k8s.compute import Job
from diagrams.k8s.network import Ing, Netpol
from diagrams.k8s.podconfig import Secret
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.database import Postgresql
from diagrams.onprem.gitops import Argocd
from diagrams.onprem.inmemory import Redis
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.queue import Rabbitmq
from diagrams.onprem.vcs import Github
from diagrams.programming.framework import Fastapi, React, Spring
from diagrams.saas.chat import Discord

GRAPHVIZ_BIN = r"C:\Program Files\Graphviz\bin"
if os.path.isdir(GRAPHVIZ_BIN) and GRAPHVIZ_BIN not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + GRAPHVIZ_BIN

OUT = Path(__file__).resolve().parent / "images"
FONT = "Malgun Gothic"

# 선 종류: 동기 HTTP / 메시지 / 저장소 / SSE
HTTP = "#1f6feb"
MSG = "#d9480f"
DATA = "#495057"
SSE = "#2b8a3e"


def diagram(name, title, direction="LR", **graph):
    return Diagram(
        title,
        filename=str(OUT / name),
        outformat="png",
        show=False,
        direction=direction,
        graph_attr={"fontname": FONT, "fontsize": "24", "pad": "0.5", "nodesep": "0.55",
                    "ranksep": "1.0", "dpi": "110", "splines": "spline", **graph},
        node_attr={"fontname": FONT, "fontsize": "13"},
        edge_attr={"fontname": FONT, "fontsize": "11"},
    )


def group(label, bg="#f8f9fa", border="#adb5bd", **graph):
    return Cluster(label, graph_attr={"fontname": FONT, "fontsize": "15", "bgcolor": bg,
                                      "pencolor": border, "style": "rounded", "margin": "18", **graph})


def box(label, fill="#ffffff", border="#868e96", size="12", **attrs):
    """아이콘이 없는 구성 요소(KEDA·OTel·Langfuse·외부 API 등)와 설명 상자."""
    base = {"shape": "box", "style": "rounded,filled", "fixedsize": "false", "labelloc": "c",
            "width": "1.6", "height": "0.6", "margin": "0.18,0.1"}
    return Node(label, fillcolor=fill, color=border, fontsize=size, **{**base, **attrs})


def note(label, **attrs):
    return box(label, fill="#fff9db", border="#e0b100", size="11", shape="note", style="filled", **attrs)


def http(label="", **attrs):
    return Edge(label=label, color=HTTP, fontcolor=HTTP, **attrs)


def msg(label="", **attrs):
    return Edge(label=label, color=MSG, fontcolor=MSG, style="dashed", **attrs)


def data(label="", **attrs):
    return Edge(label=label, color=DATA, fontcolor=DATA, style="dotted", **attrs)


def external_apis():
    with group("외부 서비스", bg="#fff4e6", border="#f08c00"):
        llm = box("LLM API\n(Claude, llm/ 래퍼로 교체 가능)")
        toss = box("토스페이먼츠\n테스트 환경")
        google = box("Google OAuth\n(로그인)")
    return llm, toss, google


def overview():
    with diagram("01-overview", "사고뭉치 전체 시스템 구성도 (운영: AWS)"):
        users = Users("학생 · 학부모 · 관리자\nReact Web")

        with group("AWS Cloud", bg="#fdf6ec", border="#ff9900"):
            cdn = CloudFront("CloudFront\n웹·API 단일 도메인")
            web = SimpleStorageServiceS3("S3\n웹 정적 파일 · 미션 장면")
            alb = ALB("ALB\n(LB Controller Ingress)")

            with group("Amazon EKS", bg="#eef4ff", border="#4c6ef5"):
                with group("namespace: app", bg="#ffffff"):
                    core = Spring("core-service\n유일한 공개 API · 인증\n대화 · 알림 · 결제 · 관리자")
                    learning = Spring("learning-service\n미션 · 학습 시도\n규칙 판정 · 기록 조회")
                    ai = Fastapi("ai-service\n판정 근거 · 되묻기\n분석 에이전트(LangGraph)")
                    scoring = Fastapi("scoring-service\nM2 · M1 모델 추론")
                    report = Fastapi("report-service\nreport-api · report-worker")
                with group("namespace: platform", bg="#ffffff"):
                    mq = Rabbitmq("RabbitMQ\n명령 큐 + 이벤트")
                    redis = Redis("Redis\nSSE 중계 · 캐시")

            rds = RDSPostgresqlInstance("RDS PostgreSQL\ncore_db · learning_db · report_db")
            files = SimpleStorageServiceS3("S3\n리포트 파일 · 모델 가중치")

        llm, toss, google = external_apis()

        users >> http("HTTPS") >> cdn
        cdn >> web
        cdn >> http("/api/*") >> alb >> http() >> core
        core >> Edge(label="SSE", color=SSE, fontcolor=SSE, style="bold", constraint="false") >> users

        core >> http("HTTP") >> [learning, ai, report]
        learning >> http() >> ai >> http() >> scoring
        report >> http() >> ai

        core >> msg("명령·이벤트") >> mq
        [report, ai, scoring] >> msg() >> mq
        core >> data() >> redis
        core >> data("서비스별 DB") >> rds
        [learning, report] >> data() >> rds
        [report, scoring] >> data() >> files

        ai >> Edge(color="#f08c00") >> llm
        core >> Edge(color="#f08c00") >> [toss, google]


def aws():
    with diagram("02-aws", "AWS 인프라 구성도", direction="TB", ranksep="0.8"):
        users = Users("사용자")
        llm, toss, google = external_apis()
        gha = GithubActions("GitHub Actions\n(OIDC로 AWS 인증)")

        with group("AWS Region", bg="#fdf6ec", border="#ff9900"):
            cdn = CloudFront("CloudFront\n/api/* 캐시 비활성\norigin 응답 60초")
            web = SimpleStorageServiceS3("S3\n웹 정적 파일 · 미션 장면")
            files = SimpleStorageServiceS3("S3\n리포트 파일 · 모델 가중치")
            ecr = ECR("ECR\n서비스 이미지 (노드 pull)")
            secrets = SecretsManager("Secrets Manager\nLLM · 토스 · JWT 키\n(External Secrets 주입)")
            iam = IAM("IAM\nIRSA · GitHub OIDC")

            with group("VPC", bg="#f1f8f1", border="#2b8a3e"):
                igw = InternetGateway("Internet Gateway")
                with group("Public Subnet", bg="#e6f4ea", border="#40c057"):
                    alb = ALB("ALB\nidle 120초")
                    nat = NATGateway("NAT Gateway\n(단일 AZ 1개)")
                with group("Private Subnet", bg="#e7f0ff", border="#4c6ef5"):
                    with group("EKS (eksctl, 관리형 control plane)", bg="#ffffff", border="#4c6ef5"):
                        eks = EKS("EKS\nadd-on: VPC CNI · CoreDNS\nkube-proxy · EBS CSI")
                        with group("노드그룹 application"):
                            app_nodes = EC2("core · learning · ai\nscoring · report\n(Cluster Autoscaler)")
                        with group("노드그룹 platform-observability"):
                            plat_nodes = EC2SpotInstance("Spot\nRabbitMQ · Redis\n관측 · Argo CD")
                    ebs = ElasticBlockStoreEBSVolume("EBS gp3\nRabbitMQ · Redis PV")
                    rds = RDSPostgresqlInstance("RDS PostgreSQL\n서비스별 DB\n백업 일 1회 · PITR 7일")

        users >> http("HTTPS") >> cdn
        cdn >> web
        cdn >> http("/api/*") >> alb >> http() >> app_nodes
        eks - Edge(style="invis") - app_nodes
        app_nodes >> data() >> rds
        plat_nodes >> data() >> ebs
        app_nodes >> data("IRSA") >> files
        app_nodes >> Edge(color="#f08c00", constraint="false") >> nat
        nat >> Edge(color="#f08c00", label="외부 호출", fontcolor="#f08c00") >> igw
        igw >> Edge(color="#f08c00") >> [llm, toss, google]
        ecr >> Edge(style="dashed") >> app_nodes
        secrets >> Edge(style="dashed") >> app_nodes
        iam >> Edge(style="dashed") >> app_nodes
        gha >> Edge(label="이미지 push", style="dashed") >> ecr


def services():
    with diagram("03-msa-eda-kubernetes", "서비스 · 메시징 · Kubernetes 구성도 (MSA + EDA + K8s)",
                 direction="TB", nodesep="0.5", ranksep="1.0"):
        web = React("React Web")
        llm, toss, google = external_apis()

        with group("Amazon EKS", bg="#eef4ff", border="#4c6ef5"):
            ingress = Ing("Ingress\n(ALB)")

            with group("namespace: app  (노드그룹 application)", bg="#ffffff", border="#4c6ef5"):
                with group("core-service  ·  HPA(min 2) · PDB"):
                    core = Spring("core-service\n유일한 공개 API\nOutbox · ShedLock")
                    core_db = Postgresql("core_db\n(RDS)")
                with group("learning-service  ·  HPA(min 2) · PDB"):
                    learning = Spring("learning-service\n규칙 판정 · 기록 조회\nS3: 미션 장면")
                    learning_db = Postgresql("learning_db\n(RDS)")
                with group("ai-service  ·  HPA(min 2) · 상태 없음"):
                    ai = Fastapi("ai-service\n판정 근거 · 되묻기\n분석 에이전트")
                with group("scoring-service  ·  HPA(min 1) · 상태 없음"):
                    scoring = Fastapi("scoring-service\nM2 · M1 추론\nS3: 모델 가중치")
                with group("report-service  ·  같은 이미지, Deployment 2개"):
                    report_api = Fastapi("report-api\nHPA(min 1) · 조회")
                    report_worker = Fastapi("report-worker\n생성 · Outbox\nS3: 리포트 파일")
                    report_db = Postgresql("report_db\n(RDS)")
                    keda = box("KEDA ScaledObject\n큐 길이 기반 0~N", fill="#e7f5ff", border="#1c7ed6")
                with group("공통 리소스 (app-service chart)", bg="#f8f9fa"):
                    Netpol("NetworkPolicy\n기본 거부 + 호출 관계만")
                    Secret("ExternalSecret\n→ Secret")
                    Job("migration-job\nArgo CD PreSync\nFlyway · Alembic")

            with group("namespace: platform  (노드그룹 platform-observability)", bg="#ffffff",
                       border="#d9480f"):
                with group("RabbitMQ  (StatefulSet + EBS gp3)", bg="#fff4e6", border="#d9480f"):
                    mq = Rabbitmq("RabbitMQ")
                    box("cmd.direct: 명령 (작업 큐, 소비자 1)\n"
                        "events.topic: 이벤트 (fan-out, 소비자 N)\n"
                        "dlx: <큐>.retry.1·2·3 (1·5·15분) 후 <큐>.dlq",
                        fill="#ffe8cc", border="#d9480f")
                redis = Redis("Redis\nSSE 중계 Pub/Sub")

            with group("namespace: observability · argocd", bg="#ffffff"):
                box("OTel Collector · Prometheus\nGrafana · Langfuse · Argo CD")

        note("범례\n"
             "── 파랑: 동기 HTTP (내부 토큰 + X-User-Id · X-User-Role · X-Student-Scope)\n"
             "      타임아웃 · 서킷 브레이커, 재시도는 ai의 LLM 호출만\n"
             "- - 주황: 메시지 (CloudEvents 봉투, 수동 ACK, 멱등 소비, Outbox: core · report)\n"
             "··· 회색: 저장소 (서비스별 DB, 다른 서비스 DB 직접 접근 금지)\n"
             "━━ 초록: SSE (피드백 · 분석 대화 · 알림, 15초 heartbeat)")

        # 진입과 SSE
        web >> http("HTTPS") >> ingress >> http() >> core
        core >> Edge(label="SSE", color=SSE, fontcolor=SSE, style="bold", constraint="false") >> web

        # 동기 HTTP (api-spec 4장 호출 관계)
        core >> http("미션·시도·피드백") >> learning
        core >> http("분석 대화 (SSE)") >> ai
        core >> http("리포트 조회") >> report_api
        learning >> http("판정·되묻기") >> ai
        ai >> http("에이전트 도구", constraint="false") >> learning
        ai >> http("M2·M1") >> scoring
        report_worker >> http("기록 조회") >> learning
        report_worker >> http("서술·저녁 질문") >> ai
        [learning, report_worker] >> http("삭제 완료 보고", style="dashed", constraint="false") >> core

        # 메시지 (architecture.md 1.4): 서비스별 발행·소비를 한 선으로 묶음, 큐 매핑은 설명 문서 표
        core >> msg("발행: report.generate · student.deleted · model.version.activated\n"
                    "소비: report.started·completed·failed · llm.usage.recorded", dir="both") >> mq
        mq >> msg("소비: report.generate · student.deleted\n발행: report.started·completed·failed",
                  dir="both") >> report_worker
        mq >> msg("소비: student.deleted") >> learning
        mq >> msg("발행: llm.usage.recorded\n소비: model.version.activated (Pod별 큐)", dir="both") >> ai
        mq >> msg(dir="both") >> scoring
        keda >> Edge(label="0~N 확장", color="#1c7ed6", fontcolor="#1c7ed6") >> report_worker

        # 저장소
        core >> data() >> [core_db, redis]
        learning >> data() >> learning_db
        [report_api, report_worker] >> data() >> report_db

        # 외부
        ai >> Edge(color="#f08c00") >> llm
        core >> Edge(color="#f08c00") >> [toss, google]


def layered():
    with diagram("04-layered", "레이어드 아키텍처 (기능 단위 패키지 + 기능 내부 4계층)", direction="TB",
                 ranksep="0.8"):
        with group("backend: <x>-service / <기능>/  (예: learning-service / answer · judgment)",
                   bg="#ffffff", border="#4c6ef5"):
            with group("Presentation", bg="#e7f5ff", border="#1c7ed6"):
                pres = box("Spring: controller · consumer · scheduler\nPython: router.py · consumer.py\n"
                           "HTTP·메시지·스케줄 수신, DTO 검증, ACK", fill="#ffffff")
            with group("Application", bg="#ebfbee", border="#2f9e44"):
                app = box("Spring: service · facade\nPython: service.py · graph.py · nodes/\n"
                          "업무 흐름, 트랜잭션 경계, Outbox 기록", fill="#ffffff")
            with group("Infrastructure", bg="#fff4e6", border="#e8590c"):
                infra = box("Spring: repository · client · messaging\nPython: repository.py · clients/ · "
                            "messaging/ · llm/\nDB · 외부 API · 브로커 · LLM · PG · S3", fill="#ffffff")
            with group("Domain", bg="#f3f0ff", border="#7048e8"):
                domain = box("Spring: domain  /  Python: models.py · state.py\n"
                             "엔티티 · 값 객체 · 상태 전이 규칙\n프레임워크 의존 없음", fill="#ffffff")

        pres >> Edge(color="#2f9e44", style="bold") >> app >> Edge(color="#2f9e44", style="bold") >> infra
        [pres, app, infra] >> Edge(style="dashed", color="#7048e8", label="참조") >> domain
        pres >> Edge(label="금지: 계층 건너뛰기", color="#e03131", fontcolor="#e03131",
                     style="dashed", constraint="false") >> infra

        with group("예시: learning 답변 제출 (architecture.md 2.5)", bg="#f8f9fa"):
            c = box("AnswerController\n요청 검증 · Idempotency-Key", fill="#e7f5ff")
            s = box("AnswerService\n@Transactional 답변 버전 저장", fill="#ebfbee")
            f = box("FeedbackFacade\n판정 PENDING→RUNNING\nAiClient 호출(트랜잭션 밖)", fill="#ebfbee")
            d = box("Answer\n버전 증가 · 덮어쓰기 금지", fill="#f3f0ff")
            r = box("AnswerRepository\nMyBatis → PostgreSQL", fill="#fff4e6")
            ac = box("AiClient\n→ ai-service", fill="#fff4e6")
            c >> s >> r
            s >> d
            c >> f >> ac

        with group("서비스별 적용 강도 · 공통 규칙", bg="#f8f9fa"):
            note("core · learning · report: 4계층 전부 (DB · 업무 규칙 · Outbox 보유)\n"
                 "ai · scoring: Domain 제외 3계층 (상태 없음)\n"
                 "기능 간 호출은 상대 기능 service로만, 여러 기능 흐름은 facade로 조합\n"
                 "트랜잭션은 Application에서만 시작, 트랜잭션 안 외부 HTTP·AMQP 호출 금지\n"
                 "오류 응답 RFC 9457 Problem Details (전 서비스 공통)")

        with group("frontend/web", bg="#ffffff", border="#1098ad"):
            fp = React("presentation\n페이지 · 컴포넌트")
            fdata = box("data\nAPI 클라이언트 · SSE · TanStack Query 훅", fill="#e3fafc")
            fdom = box("domain\n타입 · 화면 규칙", fill="#e3fafc")
            fp >> fdata
            [fp, fdata] >> Edge(style="dashed", label="참조") >> fdom
            fdata >> http("core-service 공개 API만") >> pres


def cicd_observability():
    with diagram("05-cicd-observability", "CI/CD (GitOps) · 관측 구성도"):
        with group("CI: GitHub", bg="#f8f9fa"):
            repo = Github("모노레포\nbackend · frontend · contracts")
            actions = GithubActions("GitHub Actions\n경로 필터 → 변경 서비스만\n테스트 · 빌드 · 계약 검사")
            gitops = Github("infrastructure/gitops/\nenvironments/<env>/\n이미지 태그 갱신 커밋")
        with group("이미지 레지스트리", bg="#f8f9fa"):
            ghcr = box("GHCR\n(local)")
            ecr = ECR("ECR\n(prod, OIDC)")

        with group("CD: Argo CD (GitOps)", bg="#eef4ff", border="#4c6ef5"):
            argo = Argocd("Argo CD\nroot-app · ApplicationSet")
            charts = box("Helm chart\napp-service · platform-data\nobservability")
        with group("배포 대상", bg="#f8f9fa"):
            kind = box("kind (local)\nsagomungchi-local\ningress-nginx · Calico\nstub(LLM · 토스)",
                       fill="#e7f5ff", border="#1c7ed6")
            eks = EKS("EKS (prod)\nAWS LB Controller\nCluster Autoscaler")
        secrets = SecretsManager("Secrets Manager\n→ External Secrets")

        repo >> actions >> Edge(label="이미지 push") >> [ghcr, ecr]
        actions >> gitops >> Edge(label="자동 동기화") >> argo
        charts >> Edge(style="dashed") >> argo
        argo >> Edge(label="배포") >> [kind, eks]
        ghcr >> Edge(label="pull", style="dashed") >> kind
        ecr >> Edge(label="pull", style="dashed") >> eks
        secrets >> Edge(style="dashed") >> eks

        with group("관측 (namespace: observability)", bg="#f3f0ff", border="#7048e8"):
            apps = box("app 서비스\ncore · learning · ai · scoring · report", fill="#ffffff")
            otel = box("OpenTelemetry\nCollector", fill="#ffffff")
            prom = Prometheus("Prometheus\n서비스 지표 · 큐 길이 · DLQ")
            grafana = Grafana("Grafana\n대시보드 · Alerting")
            langfuse = box("Langfuse\nLLM 호출 · 토큰 · 비용 · trace", fill="#ffffff")
        discord = Discord("팀 디스코드\n경보 웹훅")
        note("traceparent: HTTP 헤더 + 이벤트 봉투 양쪽 전파 → 동기·비동기 단일 trace\n"
             "경보: 오류율 · 지연 · 작업 적체 · 월 LLM 비용 예산 80%\n"
             "백업: RDS 일 1회 + PITR 7일, RPO 5분 · RTO 4시간")

        apps >> otel >> prom >> grafana >> Edge(label="경보") >> discord
        apps >> Edge(label="ai · scoring") >> langfuse


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    overview()
    aws()
    services()
    layered()
    cicd_observability()
