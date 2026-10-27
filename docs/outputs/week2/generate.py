"""2주차 시스템 구성도 PNG 생성.

실행: uv run --no-project --with diagrams python docs/outputs/week2/generate.py
필요: Graphviz(dot). 기준 문서: docs/design/architecture.md, docs/design/api-spec.md 4장
세부 설명은 시스템_구성도_사고뭉치.md에 두고, 그림에는 아이콘과 이름만 표시
"""

import os
from html import escape
from pathlib import Path

import diagrams
from diagrams import Cluster, Diagram, Edge, Node
from diagrams.aws.compute import EC2, ECR, EC2SpotInstance
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
ICONS = Path(diagrams.__file__).resolve().parent.parent
FONT = "Malgun Gothic"
BOLD = "Malgun Gothic Bold"

# 선 종류: 동기 HTTP / 메시지 / 저장소 / SSE / 외부 호출
HTTP = "#1c7ed6"
MSG = "#e8590c"
DATA = "#868e96"
SSE = "#2b8a3e"
EXT = "#f08c00"

# 영역 색: (배경, 테두리)
AWS = ("#fff9f0", "#ff9900")
K8S = ("#f0f5ff", "#4c6ef5")
NS = ("#ffffff", "#748ffc")
PLATFORM = ("#fff5ee", "#e8590c")
OUTSIDE = ("#fff8e6", "#f08c00")
GRAY = ("#f8f9fa", "#adb5bd")


def diagram(name, title, direction="LR", **graph):
    return Diagram(
        title,
        filename=str(OUT / name),
        outformat="png",
        show=False,
        direction=direction,
        graph_attr={"fontname": BOLD, "fontsize": "30", "labelloc": "t", "pad": "0.5", "nodesep": "0.6",
                    "ranksep": "0.9", "dpi": "65", "splines": "ortho", "forcelabels": "true",
                    "compound": "true", **graph},
        node_attr={"fontname": FONT, "fontsize": "15", "fixedsize": "false", "width": "0", "height": "0"},
        edge_attr={"fontname": FONT, "fontsize": "17", "penwidth": "2", "arrowsize": "1"},
    )


def group(label, colors=GRAY, **graph):
    bg, line = colors
    return Cluster(label, graph_attr={"fontname": BOLD, "fontsize": "20", "bgcolor": bg, "pencolor": line,
                                      "penwidth": "1.6", "style": "rounded", "margin": "20", **graph})


def cluster_id(label):
    return "cluster_" + label


def _box(cells, fill, line, width=2):
    """테두리 박스. 노드 바깥 여백이 없어 화살표 끝이 박스 테두리에 닿음."""
    return Node(f'<<TABLE STYLE="rounded" BORDER="{width}" CELLBORDER="0" COLOR="{line}" BGCOLOR="{fill}" '
                f'CELLSPACING="0" CELLPADDING="10">{cells}</TABLE>>', shape="plain")


def _name(title, size=18, color="#212529"):
    return f'<TR><TD><FONT FACE="{BOLD}" POINT-SIZE="{size}" COLOR="{color}">{escape(title)}</FONT></TD></TR>'


def comp(icons, title, fill="#ffffff", line="#adb5bd"):
    """아이콘(1개 이상)과 이름을 한 박스에 표시."""
    imgs = "".join(f'<TD FIXEDSIZE="TRUE" WIDTH="64" HEIGHT="64">'
                   f'<IMG SRC="{(ICONS / c._icon_dir / c._icon).as_posix()}" SCALE="TRUE"/></TD>' for c in icons)
    icon_row = (f'<TR><TD><TABLE BORDER="0" CELLSPACING="8" CELLPADDING="0"><TR>{imgs}</TR></TABLE>'
                f'</TD></TR>')
    return _box(icon_row + _name(title), fill, line)


def card(title, fill="#ffffff", line="#adb5bd"):
    """아이콘이 없는 구성 요소 (외부 API, OTel, 레이어 등)."""
    return _box(_name(title), fill, line)


def _line_sample(color, style):
    """범례 선 견본. 선 모양 문자는 낮은 dpi에서 그려지지 않아 색 칸으로 그림."""
    segments = {"solid": [36], "dashed": [8, 6, 8, 6, 8], "dotted": [3, 4, 3, 4, 3, 4, 3, 4, 3]}[style]
    cells = "".join(f'<TD FIXEDSIZE="TRUE" BGCOLOR="{color if i % 2 == 0 else "#ffffff"}" WIDTH="{w}" HEIGHT="3"></TD>'
                    for i, w in enumerate(segments))
    return f'<TABLE BORDER="0" CELLSPACING="0" CELLPADDING="0"><TR>{cells}</TR></TABLE>'


def legend(items, title="범례"):
    """items: (색, 선 모양 solid·dashed·dotted, 설명)."""
    rows = "".join(f'<TR><TD ALIGN="LEFT">{_line_sample(c, style)}</TD>'
                   f'<TD ALIGN="LEFT"><FONT POINT-SIZE="15">{escape(text)}</FONT></TD></TR>'
                   for c, style, text in items)
    return Node(f'<<TABLE STYLE="rounded" BORDER="1" CELLBORDER="0" COLOR="#adb5bd" BGCOLOR="#ffffff" '
                f'CELLSPACING="0" CELLPADDING="5"><TR><TD COLSPAN="2" ALIGN="LEFT"><FONT FACE="{BOLD}" '
                f'POINT-SIZE="17">{escape(title)}</FONT></TD></TR>{rows}</TABLE>>', shape="plain")


def edge(**attrs):
    """diagrams Edge 기본 글꼴(Sans-Serif 13pt)을 덮어씀. 직각 선은 label을 지원하지 않아 xlabel로 표시."""
    if "label" in attrs:
        attrs["xlabel"] = f' {attrs.pop("label")} '
    return Edge(**{"fontname": FONT, "fontsize": "17", **attrs})


def _edge(color, label, style, **attrs):
    if label:
        attrs["label"] = label
    return edge(color=color, fontcolor=color, style=style, **attrs)


def http(label="", **attrs):
    return _edge(HTTP, label, "solid", **attrs)


def msg(label="", **attrs):
    return _edge(MSG, label, "dashed", **attrs)


def data(label="", **attrs):
    return _edge(DATA, label, "dotted", **attrs)


def ext(label="", **attrs):
    return _edge(EXT, label, "solid", **attrs)


def invis():
    return edge(style="invis")


def externals():
    label = "외부 서비스"
    with group(label, OUTSIDE):
        llm = card("LLM API")
        toss = card("토스페이먼츠")
        google = card("Google OAuth")
    return cluster_id(label), llm, toss, google


def overview():
    with diagram("01-overview", "사고뭉치 전체 시스템 구성도"):
        users = comp([Users], "사용자")

        with group("AWS Cloud", AWS):
            with group("엣지", GRAY):
                cdn = comp([CloudFront], "CloudFront")
                web = comp([SimpleStorageServiceS3], "S3 (웹)")
            alb = comp([ALB], "ALB")

            with group("Amazon EKS", K8S):
                with group("namespace: app", NS):
                    core = comp([Spring], "core-service")
                    learning = comp([Spring], "learning-service")
                    report = comp([Fastapi], "report-service")
                    ai = comp([Fastapi], "ai-service")
                    scoring = comp([Fastapi], "scoring-service")
                with group("namespace: platform", PLATFORM):
                    mq = comp([Rabbitmq], "RabbitMQ")
                    comp([Redis], "Redis")

            with group("데이터 저장소", GRAY):
                rds = comp([RDSPostgresqlInstance], "RDS PostgreSQL")
                files = comp([SimpleStorageServiceS3], "S3 (파일)")
            rds >> invis() >> files

        ext_id, llm, _, _ = externals()
        legend([(HTTP, "solid", "동기 HTTP"), (MSG, "dashed", "메시지 (RabbitMQ)"), (DATA, "dotted", "저장소"),
                (EXT, "solid", "외부 API")])

        users >> http("HTTPS") >> cdn
        cdn >> data() >> web
        cdn >> http("/api/*") >> alb >> http() >> core
        core >> http() >> [learning, report]
        [core, learning] >> http() >> ai
        ai >> http() >> scoring

        # app 영역 → 오른쪽 영역 묶음 선
        app_id = cluster_id("namespace: app")
        scoring >> msg(ltail=app_id, lhead=cluster_id("namespace: platform")) >> mq
        scoring >> data(ltail=app_id, lhead=cluster_id("데이터 저장소")) >> rds
        scoring >> ext(ltail=app_id, lhead=ext_id) >> llm


def aws():
    with diagram("02-aws", "AWS 인프라 구성도", direction="TB"):
        users = comp([Users], "사용자")
        gha = comp([GithubActions], "GitHub Actions")
        ext_id, llm, _, _ = externals()

        with group("AWS Region", AWS):
            cdn = comp([CloudFront], "CloudFront")
            web = comp([SimpleStorageServiceS3], "S3 (웹)")
            files = comp([SimpleStorageServiceS3], "S3 (파일)")
            mgmt_label = "관리형 서비스"
            with group(mgmt_label, GRAY):
                ecr = comp([ECR], "ECR")
                comp([SecretsManager], "Secrets Manager")
                comp([IAM], "IAM")

            with group("VPC", ("#f4fbf4", "#2b8a3e")):
                igw = comp([InternetGateway], "Internet Gateway")
                with group("Public Subnet", ("#e9f7ec", "#40c057")):
                    alb = comp([ALB], "ALB")
                    nat = comp([NATGateway], "NAT Gateway")
                with group("Private Subnet", ("#edf2ff", "#4c6ef5")):
                    eks_label = "Amazon EKS"
                    # 진입 선이 왼쪽 위에서 들어오므로 영역 이름은 오른쪽에 둠
                    with group(eks_label, NS, labeljust="r"):
                        app = comp([EC2], "application 노드그룹")
                        plat = comp([EC2SpotInstance], "platform 노드그룹 (Spot)")
                    rds = comp([RDSPostgresqlInstance], "RDS PostgreSQL")
                    ebs = comp([ElasticBlockStoreEBSVolume], "EBS gp3")

        # 진입
        users >> http("HTTPS") >> cdn
        cdn >> data() >> web
        cdn >> http("/api/*") >> alb >> http() >> app
        # 외부 호출: 앱 → NAT → IGW → 외부 (위쪽 배치를 위해 선은 역방향으로 두고 화살표만 반대로 표시)
        nat - ext(reverse=True) - app
        igw - ext(reverse=True) - nat
        llm - ext(reverse=True, ltail=ext_id) - igw
        # 저장소
        app >> data() >> rds
        plat >> data() >> ebs
        app >> data() >> files
        # 배포·보안
        gha >> edge(label="이미지 push", style="dashed") >> ecr
        ecr >> edge(style="dashed", ltail=cluster_id(mgmt_label), lhead=cluster_id(eks_label)) >> app
        ecr >> invis() >> plat


def services():
    # 선 라벨이 박스와 겹치지 않도록 간격을 넓힘
    with diagram("03-msa-eda-kubernetes", "서비스 · 메시징 · Kubernetes 구성도 (MSA + EDA + K8s)",
                 nodesep="1.0", ranksep="1.4"):
        web = comp([React], "React Web")
        legend([(HTTP, "solid", "동기 HTTP"), (MSG, "dashed", "메시지 (RabbitMQ)"), (SSE, "solid", "SSE")])

        with group("Amazon EKS", K8S):
            ingress = comp([Ing], "Ingress")
            with group("namespace: app", NS):
                core = comp([Spring, Postgresql], "core-service")
                learning = comp([Spring, Postgresql], "learning-service")
                with group("상태 없는 서비스", GRAY):
                    ai = comp([Fastapi], "ai-service")
                    scoring = comp([Fastapi], "scoring-service")
                with group("report-service", GRAY):
                    report_api = comp([Fastapi, Postgresql], "report-api")
                    worker = comp([Fastapi], "report-worker (KEDA)")
                common = comp([Netpol, Secret, Job], "공통 리소스")

            with group("namespace: platform", PLATFORM):
                mq = comp([Rabbitmq], "RabbitMQ")
                comp([Redis], "Redis")

        # 진입과 SSE
        web >> http("HTTPS") >> ingress >> http() >> core
        core >> _edge(SSE, "SSE", "bold", constraint="false") >> web
        ingress >> invis() >> common

        # 동기 HTTP (api-spec 4장 호출 관계, report-worker → learning은 설명 문서에 표기)
        core >> http("미션 · 피드백") >> learning
        core >> http("리포트 조회") >> report_api
        core >> http("분석 대화") >> ai
        learning >> http("판정 · 되묻기", reverse=True) >> ai
        ai >> http("M2 · M1") >> scoring
        worker >> http("서술 생성") >> ai

        # 메시지: app 영역 전체와 RabbitMQ를 한 선으로 묶음 (메시지별 생산·소비는 설명 문서 표)
        core >> msg("명령 · 이벤트", reverse=True, ltail=cluster_id("namespace: app")) >> mq


def layered():
    blue, green, orange, purple, teal = "#1c7ed6", "#2f9e44", "#e8590c", "#7048e8", "#1098ad"

    def layer(name, color, fill, **attrs):
        return Node(f'<<TABLE STYLE="rounded" BORDER="2" CELLBORDER="0" COLOR="{color}" BGCOLOR="{fill}" '
                    f'CELLSPACING="0" CELLPADDING="14">{_name(name, 20, color)}</TABLE>>', shape="plain", **attrs)

    with diagram("04-layered", "레이어드 아키텍처 (기능 단위 패키지 + 기능 내부 4계층)", direction="TB"):
        with group("백엔드: <service>/<기능>/", NS):
            pres = layer("Presentation", blue, "#e7f5ff", group="layers")
            app = layer("Application", green, "#ebfbee", group="layers")
            infra = layer("Infrastructure", orange, "#fff4e6", group="layers")
            domain = layer("Domain", purple, "#f3f0ff")
        down = {"color": "#495057", "penwidth": "2.4"}
        pres >> edge(**down) >> app >> edge(**down) >> infra
        ref = {"color": purple, "style": "dashed"}
        pres >> edge(label="참조", fontcolor=purple, **ref) >> domain
        app >> edge(constraint="false", **ref) >> domain
        infra >> edge(constraint="false", **ref) >> domain

        with group("예시: learning 답변 제출 · 피드백", GRAY):
            ctrl = card("AnswerController", "#e7f5ff", blue)
            svc = card("AnswerService", "#ebfbee", green)
            facade = card("FeedbackFacade", "#ebfbee", green)
            repo = card("AnswerRepository", "#fff4e6", orange)
            ai_client = card("AiClient", "#fff4e6", orange)
            answer = card("Answer", "#f3f0ff", purple)
        ctrl >> edge() >> svc >> edge() >> repo
        svc >> edge(style="dashed", color=purple) >> answer
        ctrl >> edge() >> facade >> edge() >> ai_client

        with group("frontend/web", ("#f3fbfc", teal)):
            f_pres = card("presentation", line=teal)
            f_data = card("data", line=teal)
            f_domain = card("domain", line=teal)
        f_pres >> edge() >> f_data
        [f_pres, f_data] >> edge(style="dashed", color=teal) >> f_domain


def cicd_observability():
    with diagram("05-cicd-observability", "CI/CD (GitOps) · 관측 구성도"):
        with group("CI/CD (GitOps)", K8S):
            repo = comp([Github], "모노레포")
            actions = comp([GithubActions], "GitHub Actions")
            ghcr = card("GHCR (local)")
            ecr = comp([ECR], "ECR (prod)")
            gitops = comp([Github], "gitops 태그 커밋")
            argo = comp([Argocd], "Argo CD")
            kind = card("kind (local)", "#e7f5ff", HTTP)
            eks = card("EKS (prod)", "#fff4e6", "#ff9900")

        legend([("#7b8894", "solid", "빌드 · 배포 흐름"), ("#7b8894", "dashed", "이미지 pull")])
        repo >> edge() >> actions >> edge() >> [ghcr, ecr]
        actions >> edge() >> gitops >> edge() >> argo >> edge() >> [kind, eks]
        ghcr >> edge(style="dashed") >> kind
        ecr >> edge(style="dashed") >> eks

        with group("관측 (namespace: observability)", ("#f8f5ff", "#7048e8")):
            apps = card("app 서비스")
            otel = card("OpenTelemetry Collector")
            prom = comp([Prometheus], "Prometheus")
            grafana = comp([Grafana], "Grafana")
            langfuse = card("Langfuse")
        discord = comp([Discord], "팀 디스코드")

        apps >> edge() >> otel >> edge() >> prom >> edge() >> grafana >> edge() >> discord
        apps >> edge() >> langfuse


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    overview()
    aws()
    services()
    layered()
    cicd_observability()
