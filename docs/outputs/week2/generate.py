"""2주차 시스템 구성도 PNG 생성.

실행: uv run --no-project --with diagrams --with pillow python docs/outputs/week2/generate.py [그림 이름 ...]
필요: Graphviz(dot). 기준 문서: docs/design/architecture.md, docs/design/api-spec.md 4장
세부 설명은 시스템_구성도_사고뭉치.md에 두고, 그림에는 아이콘과 이름만 표시
"""

import base64
import os
import subprocess
import sys
from contextlib import contextmanager
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
from PIL import Image

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


@contextmanager
def diagram(name, title, direction="LR", **graph):
    """dpi 130으로 그린 뒤 절반으로 축소. 낮은 dpi로 바로 그리는 것보다 글자·선이 선명함."""
    with Diagram(
        title,
        filename=str(OUT / name),
        outformat="png",
        show=False,
        direction=direction,
        graph_attr={"fontname": BOLD, "fontsize": "30", "labelloc": "t", "pad": "0.3", "nodesep": "0.5",
                    "ranksep": "0.8", "dpi": "130", "splines": "ortho", "forcelabels": "true",
                    "compound": "true", **graph},
        node_attr={"fontname": FONT, "fontsize": "15", "fixedsize": "false", "width": "0", "height": "0"},
        edge_attr={"fontname": FONT, "fontsize": "17", "penwidth": "2", "arrowsize": "1"},
    ) as d:
        yield d
    path = OUT / f"{name}.png"
    with Image.open(path) as image:
        small = image.resize((image.width // 2, image.height // 2), Image.LANCZOS)
    small.save(path, optimize=True)


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


def _icon_path(icon):
    return ICONS / icon._icon_dir / icon._icon


def comp(icons, title, fill="#ffffff", line="#adb5bd"):
    """아이콘(1개 이상)과 이름을 한 박스에 표시."""
    imgs = "".join(f'<TD FIXEDSIZE="TRUE" WIDTH="64" HEIGHT="64">'
                   f'<IMG SRC="{_icon_path(c).as_posix()}" SCALE="TRUE"/></TD>' for c in icons)
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
                    redis = comp([Redis], "Redis")

            with group("데이터 저장소", GRAY):
                rds = comp([RDSPostgresqlInstance], "RDS PostgreSQL")
                files = comp([SimpleStorageServiceS3], "S3 (파일)")

        ext_id, llm, toss, google = externals()
        legend([(HTTP, "solid", "동기 HTTP"), (MSG, "dashed", "메시지 (RabbitMQ)"), (DATA, "dotted", "저장소"),
                (EXT, "solid", "외부 API")])

        # 오른쪽 세 영역(platform·저장소·외부)은 가로로 펼쳐 app 영역 높이에 맞춤
        mq >> invis() >> redis
        rds >> invis() >> files
        llm >> invis() >> toss >> invis() >> google
        # S3(웹)은 CloudFront와 같은 열에 세로로 배치
        users >> invis() >> web

        users >> http("HTTPS") >> cdn
        cdn >> data(constraint="false") >> web
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
                # /api/* 선이 위쪽으로 들어오므로 영역 이름은 아래에 두고, 여백으로 NAT 선과 간격 확보
                with group("Public Subnet", ("#e9f7ec", "#40c057"), labelloc="b", margin="40"):
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
        # 배포·보안: 관리형 서비스를 EKS 노드와 같은 높이에 두어 오른쪽 아래 공백을 채움
        gha >> edge(label="이미지 push", style="dashed", constraint="false") >> ecr
        ecr >> edge(style="dashed", constraint="false", ltail=cluster_id(mgmt_label),
                    lhead=cluster_id(eks_label)) >> app
        alb >> invis() >> ecr


def services():
    # 선 라벨이 박스와 겹치지 않도록 간격을 넓힘
    with diagram("03-msa-eda-kubernetes", "서비스 · 메시징 · Kubernetes 구성도 (MSA + EDA + K8s)",
                 nodesep="0.8", ranksep="1.2"):
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
                redis = comp([Redis], "Redis")
        # platform 영역은 가로로 배치해 세로 공백을 줄임
        mq >> invis() >> redis

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

        legend_node = legend([("#7b8894", "solid", "빌드 · 배포 흐름"), ("#7b8894", "dashed", "이미지 pull")])
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
        # 범례는 관측 줄 오른쪽 빈 자리에 둠
        discord >> invis() >> legend_node


EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
AI = ("#f8f5ff", "#7048e8")
DASH = {"solid": "", "dashed": ' stroke-dasharray="7 5"', "dotted": ' stroke-dasharray="2 4"'}


def _svg_text(x, y, text, size=15, color="#212529", bold=False, anchor="middle"):
    weight = ' font-weight="700"' if bold else ""
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}"{weight}>'
            f'{escape(text)}</text>')


def _svg_group(x, y, w, h, label, colors):
    bg, line = colors
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{bg}" stroke="{line}" stroke-width="1.6"/>'
            + _svg_text(x + 14, y + 26, label, 17, bold=True, anchor="start"))


def _svg_node(x, y, w, title, keywords, icons=()):
    """아이콘 + 이름 + 키워드 한 줄. 아이콘이 없으면 낮은 박스."""
    h = 130 if icons else 80
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#ffffff" stroke="#adb5bd" '
           f'stroke-width="1.5"/>']
    size, gap = 52, 8
    left = x + (w - len(icons) * size - (len(icons) - 1) * gap) / 2
    for i, icon in enumerate(icons):
        data = base64.b64encode(_icon_path(icon).read_bytes()).decode()
        out.append(f'<image href="data:image/png;base64,{data}" x="{left + i * (size + gap)}" y="{y + 14}" '
                   f'width="{size}" height="{size}"/>')
    out.append(_svg_text(x + w / 2, y + h - 34, title, bold=True))
    out.append(_svg_text(x + w / 2, y + h - 14, keywords, 12, "#868e96"))
    return "".join(out)


def _svg_arrow(points, color, style="solid", label="", label_at=None, label_size=13, bold=False):
    """직각 화살표. points는 꺾이는 점 목록, 마지막 점에 화살촉."""
    d = "M" + " L".join(f"{x} {y}" for x, y in points)
    out = (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{DASH[style]} '
           f'marker-end="url(#a{color[1:]})"/>')
    if label:
        lx, ly = label_at
        weight = ' font-weight="700"' if bold else ""
        out += (f'<text x="{lx}" y="{ly}" font-size="{label_size}" fill="{color}"{weight} stroke="#ffffff" '
                f'stroke-width="4" paint-order="stroke">{escape(label)}</text>')
    return out


def system_icon():
    """제출용 한 장 요약. 박스 위치를 직접 지정해야 해서 Graphviz 대신 SVG로 그린 뒤 Edge로 PNG 변환.

    화살표는 오른쪽 또는 아래쪽: 행 A(요청 흐름) → 행 B(정적 파일 · 메시징 · 파일) → AWS 아래 외부 서비스
    (AI 처리 → RabbitMQ만 platform 제목을 피해 RabbitMQ · Redis 사이로 내려가 RabbitMQ 오른쪽으로 진입,
    외부 호출은 EKS → 왼쪽 Public Subnet의 NAT Gateway → 아래 외부 서비스)
    VPC 안은 ALB · NAT Gateway(Public), EKS · RDS(Private)만. CloudFront · S3는 VPC 밖 AWS 관리형 서비스
    """
    width, height = 2170, 980
    a, b = 280, 510  # 행 A · 행 B 노드 위쪽 y
    ac, bc = a + 65, b + 65  # 행 중앙 y
    body = [
        _svg_text(width / 2, 50, "사고뭉치 시스템 구성도", 28, bold=True),
        # 영역
        _svg_group(220, 80, 1920, 670, "AWS Cloud", AWS),
        _svg_group(240, 470, 194, 200, "Frontend", ("#f3fbfc", "#1098ad")),
        _svg_group(460, 120, 1430, 610, "VPC", ("#f4fbf4", "#2b8a3e")),
        _svg_group(480, 160, 180, 550, "Public Subnet", ("#e9f7ec", "#40c057")),
        _svg_group(690, 160, 1180, 550, "Private Subnet", ("#eef6fb", "#147eba")),
        _svg_group(710, 200, 890, 490, "Amazon EKS", K8S),
        _svg_group(730, 240, 380, 430, "앱 서버 (namespace: app)", NS),
        _svg_group(1140, 240, 440, 190, "AI 처리", AI),
        _svg_group(1140, 470, 440, 200, "namespace: platform", PLATFORM),
        _svg_group(440, 790, 810, 150, "외부 서비스", OUTSIDE),
        # 노드
        _svg_node(20, a, 175, "학생 · 학부모 · 관리자", "웹 브라우저", [Users]),
        _svg_node(262, a, 150, "CloudFront", "단일 도메인 · 경로 분기", [CloudFront]),
        _svg_node(495, a, 150, "ALB", "Ingress", [ALB]),
        _svg_node(495, b, 150, "NAT Gateway", "외부 호출 · 단일 AZ", [NATGateway]),
        _svg_node(262, b, 150, "Frontend (React)", "S3 정적 배포", [React, SimpleStorageServiceS3]),
        _svg_node(750, a, 150, "core-service", "공개 API · 인증 · SSE", [Spring]),
        _svg_node(940, a, 150, "learning-service", "미션 · 기록 · 규칙 판정", [Spring]),
        _svg_node(940, b, 150, "report-service", "주간 리포트 · KEDA", [Fastapi]),
        _svg_node(1160, a, 180, "ai-service (LangGraph)", "판정 · 되묻기 · 분석 에이전트", [Fastapi]),
        _svg_node(1380, a, 180, "scoring-service (M2)", "M2 점수 · M1 수학 점검", [Fastapi]),
        _svg_node(1160, b, 180, "RabbitMQ", "명령 · 이벤트", [Rabbitmq]),
        _svg_node(1380, b, 180, "Redis", "SSE 중계", [Redis]),
        _svg_node(1660, a, 190, "RDS PostgreSQL", "서비스별 DB", [RDSPostgresqlInstance]),
        _svg_node(1930, b, 190, "S3 (파일)", "미션 장면 · 리포트 · 가중치", [SimpleStorageServiceS3]),
        _svg_node(460, 840, 180, "LLM API", "OpenAI · Claude"),
        _svg_node(660, 840, 180, "Google OAuth", "로그인 · 재인증"),
        _svg_node(860, 840, 180, "토스페이먼츠", "구독 결제 (테스트)"),
        _svg_node(1060, 840, 170, "RunPod GPU", "M2 학습 → S3 가중치"),
        # 요청 흐름 (행 A, 오른쪽)
        _svg_arrow([(195, ac), (260, ac)], HTTP, label="HTTPS", label_at=(200, ac - 10)),
        _svg_arrow([(412, ac), (493, ac)], HTTP, label="/api/*", label_at=(420, ac - 10)),
        _svg_arrow([(645, ac), (748, ac)], HTTP),
        _svg_arrow([(900, ac), (938, ac)], HTTP),
        _svg_arrow([(1090, ac), (1158, ac)], HTTP),
        _svg_arrow([(1340, ac), (1378, ac)], HTTP),
        # 아래로 분기
        _svg_arrow([(385, a + 130), (385, b - 2)], DATA, "dotted", "정적 파일", (393, 445)),
        _svg_arrow([(825, a + 130), (825, bc), (938, bc)], HTTP),
        # 메시징
        _svg_arrow([(1090, bc), (1158, bc)], MSG, "dashed"),
        _svg_arrow([(1360, 430), (1360, bc), (1342, bc)], MSG, "dashed"),
        # 저장소
        _svg_arrow([(1600, ac), (1658, ac)], DATA, "dotted", "SQL", (1612, ac - 10)),
        _svg_arrow([(1600, bc), (1928, bc)], DATA, "dotted", "파일", (1612, bc - 10)),
        # 외부 호출: EKS → NAT Gateway → 외부 서비스
        _svg_arrow([(710, bc), (647, bc)], EXT),
        _svg_arrow([(570, b + 130), (570, 788)], EXT),
    ]

    items = [(HTTP, "solid", "동기 HTTP"), (MSG, "dashed", "메시지 (RabbitMQ)"), (DATA, "dotted", "저장소"),
             (EXT, "solid", "외부 API")]
    body.append('<rect x="40" y="790" width="230" height="150" rx="10" fill="#ffffff" stroke="#adb5bd"/>')
    body.append(_svg_text(56, 816, "범례", 15, bold=True, anchor="start"))
    for i, (color, style, text) in enumerate(items):
        y = 844 + i * 26
        body.append(f'<line x1="56" y1="{y - 4}" x2="96" y2="{y - 4}" stroke="{color}" stroke-width="2"{DASH[style]}/>')
        body.append(_svg_text(106, y, text, 13, anchor="start"))

    markers = "".join(
        f'<marker id="a{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>' for c in (HTTP, MSG, DATA, EXT))
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}" font-family="{FONT}, sans-serif"><defs>{markers}</defs>'
           f'<rect width="{width}" height="{height}" fill="#ffffff"/>{"".join(body)}</svg>')

    svg_path, png_path = OUT / "시스템구성도_아이콘형.svg", OUT / "시스템구성도_아이콘형.png"
    svg_path.write_text(svg, encoding="utf-8")
    if not EDGE.exists():
        print(f"Edge 없음: {svg_path.name}만 생성, PNG는 브라우저로 변환 필요")
        return
    subprocess.run([str(EDGE), "--headless", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}",
                    "--force-device-scale-factor=2", f"--screenshot={png_path}", svg_path.as_uri()],
                   check=True, capture_output=True)


FIGURES = {f.__name__: f for f in (overview, aws, services, layered, cicd_observability, system_icon)}

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    # 인자로 그림 이름을 주면 해당 그림만 생성 (예: system_icon)
    for name in sys.argv[1:] or FIGURES:
        FIGURES[name]()
