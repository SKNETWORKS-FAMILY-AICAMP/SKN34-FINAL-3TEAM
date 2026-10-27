"""2주차 시스템 구성도 PNG 생성.

실행: uv run --no-project --with diagrams python docs/outputs/week2/generate.py
필요: Graphviz(dot). 기준 문서: docs/design/architecture.md, docs/design/api-spec.md 4장
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
        graph_attr={"fontname": BOLD, "fontsize": "34", "labelloc": "t", "pad": "0.6", "nodesep": "0.8",
                    "ranksep": "1.1", "dpi": "130", "splines": "ortho", "forcelabels": "true", "compound": "true", **graph},
        node_attr={"fontname": FONT, "fontsize": "15", "fixedsize": "false", "width": "0", "height": "0"},
        edge_attr={"fontname": FONT, "fontsize": "19", "penwidth": "2", "arrowsize": "0.9"},
    )


def group(label, colors=GRAY, **graph):
    bg, line = colors
    return Cluster(label, graph_attr={"fontname": BOLD, "fontsize": "22", "bgcolor": bg, "pencolor": line,
                                      "penwidth": "1.6", "style": "rounded", "margin": "24", **graph})


def cluster_id(label):
    return "cluster_" + label


# 노드 둘레 여백: 직각 선이 글자에 붙지 않도록 함
BOX = {"shape": "none", "margin": "0.22,0.14"}


def _html(rows):
    return f'<<TABLE BORDER="0" CELLSPACING="0" CELLPADDING="3">{"".join(rows)}</TABLE>>'


def _text_rows(title, desc):
    rows = [f'<TR><TD><FONT FACE="{BOLD}" POINT-SIZE="19">{escape(title)}</FONT></TD></TR>']
    rows += [f'<TR><TD><FONT POINT-SIZE="16" COLOR="#495057">{escape(line)}</FONT></TD></TR>'
             for line in desc.splitlines()]
    return rows


def comp(icons, title, desc="", size=80):
    """아이콘(1개 이상) + 굵은 이름 + 설명. 아이콘과 글자 사이 간격을 표로 고정."""
    imgs = "".join(
        f'<TD FIXEDSIZE="TRUE" WIDTH="{size}" HEIGHT="{size}">'
        f'<IMG SRC="{(ICONS / c._icon_dir / c._icon).as_posix()}" SCALE="TRUE"/></TD>'
        for c in icons)
    rows = [f'<TR><TD><TABLE BORDER="0" CELLSPACING="10" CELLPADDING="0"><TR>{imgs}</TR></TABLE></TD></TR>',
            '<TR><TD HEIGHT="4"></TD></TR>']
    return Node(_html(rows + _text_rows(title, desc)), **BOX)


def card(title, desc="", fill="#ffffff", line="#868e96"):
    """아이콘이 없는 구성 요소 (외부 API, KEDA, OTel 등)."""
    body = "".join(_text_rows(title, desc))
    return Node(f'<<TABLE STYLE="rounded" BORDER="1" CELLBORDER="0" COLOR="{line}" BGCOLOR="{fill}" CELLSPACING="0" '
                f'CELLPADDING="8"><TR><TD><TABLE BORDER="0" CELLSPACING="0" CELLPADDING="2">{body}'
                f'</TABLE></TD></TR></TABLE>>', **BOX)


def table(title, header, rows, line="#adb5bd", head_fill="#f1f3f5"):
    """여러 열 표. 선 대신 세부 정보를 그림 안에 정리할 때 사용."""
    cells = "".join(f'<TD BGCOLOR="{head_fill}" ALIGN="LEFT"><FONT FACE="{BOLD}" POINT-SIZE="16">'
                    f'{escape(h)}</FONT></TD>' for h in header)
    body = "".join("<TR>" + "".join(f'<TD ALIGN="LEFT"><FONT POINT-SIZE="16">{escape(c)}</FONT></TD>'
                                    for c in r) + "</TR>" for r in rows)
    return Node(f'<<TABLE BORDER="1" COLOR="{line}" BGCOLOR="#ffffff" CELLBORDER="1" CELLSPACING="0" '
                f'CELLPADDING="7"><TR><TD COLSPAN="{len(header)}" ALIGN="LEFT" BGCOLOR="#ffffff">'
                f'<FONT FACE="{BOLD}" POINT-SIZE="18">{escape(title)}</FONT></TD></TR>'
                f'<TR>{cells}</TR>{body}</TABLE>>', **BOX)


def legend(items, title="범례"):
    """items: (색, 선 모양 문자, 설명)."""
    rows = "".join(f'<TR><TD ALIGN="LEFT"><FONT COLOR="{c}" POINT-SIZE="18"><B>{escape(mark)}</B></FONT></TD>'
                   f'<TD ALIGN="LEFT"><FONT POINT-SIZE="16">{escape(text)}</FONT></TD></TR>'
                   for c, mark, text in items)
    return Node(f'<<TABLE STYLE="rounded" BORDER="1" CELLBORDER="0" COLOR="#adb5bd" BGCOLOR="#ffffff" CELLSPACING="0" '
                f'CELLPADDING="5"><TR><TD COLSPAN="2" ALIGN="LEFT"><FONT FACE="{BOLD}" POINT-SIZE="18">'
                f'{escape(title)}</FONT></TD></TR>{rows}</TABLE>>', **BOX)


def edge(**attrs):
    """diagrams Edge 기본 글꼴(Sans-Serif 13pt)을 덮어씀. 직각 선은 label을 지원하지 않아 xlabel로 표시."""
    if "label" in attrs:
        attrs["xlabel"] = attrs.pop("label")
    return Edge(**{"fontname": FONT, "fontsize": "19", **attrs})


def pad(label):
    """선 라벨 좌우 여백."""
    return f" {label} "


def _edge(color, label, style, **attrs):
    if label:
        attrs["label"] = pad(label)
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
        llm = card("LLM API", "Claude · ai-service만 호출")
        toss = card("토스페이먼츠", "테스트 환경 · core-service")
        google = card("Google OAuth", "로그인 · core-service")
    return cluster_id(label), llm, toss, google


def overview():
    with diagram("01-overview", "사고뭉치 전체 시스템 구성도"):
        users = comp([Users], "사용자", "학생 · 학부모 · 관리자\nReact Web")

        with group("AWS Cloud", AWS):
            with group("엣지", GRAY):
                cdn = comp([CloudFront], "CloudFront", "웹 · API 단일 도메인")
                web = comp([SimpleStorageServiceS3], "S3", "웹 정적 파일 · 미션 장면")
            alb = comp([ALB], "ALB", "Ingress")

            with group("Amazon EKS", K8S):
                with group("namespace: app", NS):
                    core = comp([Spring], "core-service", "유일한 공개 API · 인증 · SSE\n대화 · 리포트 작업 · 결제")
                    learning = comp([Spring], "learning-service", "미션 · 학습 기록 · 규칙 판정")
                    report = comp([Fastapi], "report-service", "주간 리포트 생성 · 조회")
                    ai = comp([Fastapi], "ai-service", "판정 근거 · 되묻기\n분석 에이전트 (LangGraph)")
                    scoring = comp([Fastapi], "scoring-service", "M2 · M1 모델 추론")
                with group("namespace: platform", PLATFORM):
                    mq = comp([Rabbitmq], "RabbitMQ", "명령 큐 · 이벤트")
                    comp([Redis], "Redis", "SSE 중계")

            with group("데이터 저장소", GRAY):
                rds = comp([RDSPostgresqlInstance], "RDS PostgreSQL", "core_db · learning_db · report_db")
                files = comp([SimpleStorageServiceS3], "S3", "리포트 파일 · 모델 가중치")
            rds >> invis() >> files

        ext_id, llm, _, _ = externals()
        legend([(HTTP, "━━━", "동기 HTTP"), (MSG, "- - -", "메시지 (RabbitMQ)"), (DATA, "· · ·", "저장소"),
                (EXT, "━━━", "외부 API"), ("#495057", "※", "서비스 간 상세 호출은 03 구성도")])

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
    with diagram("02-aws", "AWS 인프라 구성도", direction="TB", ranksep="0.9"):
        users = comp([Users], "사용자")
        gha = comp([GithubActions], "GitHub Actions", "OIDC로 AWS 인증")
        ext_id, llm, _, _ = externals()

        with group("AWS Region", AWS):
            cdn = comp([CloudFront], "CloudFront", "/api/* 캐시 비활성")
            web = comp([SimpleStorageServiceS3], "S3", "웹 정적 파일 · 미션 장면")
            files = comp([SimpleStorageServiceS3], "S3", "리포트 파일 · 모델 가중치\nIRSA로 접근")
            mgmt_label = "관리형 서비스 (이미지 · 시크릿 · 권한 → EKS)"
            with group(mgmt_label, GRAY):
                ecr = comp([ECR], "ECR", "서비스 이미지")
                comp([SecretsManager], "Secrets Manager", "External Secrets로 주입")
                comp([IAM], "IAM", "IRSA · GitHub OIDC")

            with group("VPC", ("#f4fbf4", "#2b8a3e")):
                igw = comp([InternetGateway], "Internet Gateway")
                with group("Public Subnet", ("#e9f7ec", "#40c057")):
                    alb = comp([ALB], "ALB", "idle 120초")
                    nat = comp([NATGateway], "NAT Gateway", "단일 AZ 1개")
                with group("Private Subnet", ("#edf2ff", "#4c6ef5")):
                    eks_label = "Amazon EKS (eksctl · 관리형 control plane)"
                    # 진입 선이 왼쪽 위에서 들어오므로 영역 이름은 오른쪽에 둠
                    with group(eks_label, NS, labeljust="r"):
                        app = comp([EC2], "노드그룹 application", "core · learning · ai\nscoring · report")
                        plat = comp([EC2SpotInstance], "노드그룹 platform-observability",
                                    "Spot · RabbitMQ · Redis\n관측 · Argo CD")
                    rds = comp([RDSPostgresqlInstance], "RDS PostgreSQL", "서비스별 DB\n일 1회 백업 · PITR 7일")
                    ebs = comp([ElasticBlockStoreEBSVolume], "EBS gp3", "RabbitMQ · Redis 볼륨")

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
        gha >> edge(label=pad("이미지 push"), style="dashed") >> ecr
        ecr >> edge(style="dashed", ltail=cluster_id(mgmt_label),
                    lhead=cluster_id(eks_label)) >> app
        ecr >> invis() >> plat


def services():
    with diagram("03-msa-eda-kubernetes", "서비스 · 메시징 · Kubernetes 구성도 (MSA + EDA + K8s)",
                 nodesep="0.7", ranksep="1.0"):
        web = comp([React], "React Web")
        legend([(HTTP, "━━━", "동기 HTTP (내부 토큰 + 사용자·학생 범위 헤더)"),
                (MSG, "- - -", "메시지 (RabbitMQ, 수동 ACK · 멱등 소비)"),
                (SSE, "━━━", "SSE (피드백 · 분석 대화 · 알림)"),
                ("#495057", "※", "외부 API 연동은 01 · 02 구성도")])

        with group("Amazon EKS", K8S):
            ingress = comp([Ing], "Ingress", "ALB")
            with group("namespace: app", NS):
                core = comp([Spring, Postgresql], "core-service",
                            "공개 API · SSE · Outbox\nDB: core_db · HPA min 2")
                learning = comp([Spring, Postgresql], "learning-service",
                                "규칙 판정 · 기록 조회\nDB: learning_db · HPA min 2")
                stateless = "상태 없는 서비스 (DB 없음)"
                with group(stateless, GRAY):
                    ai = comp([Fastapi], "ai-service", "판정 근거 · 되묻기 · 분석 에이전트\nLLM API 호출 · HPA min 2")
                    scoring = comp([Fastapi], "scoring-service", "M2 · M1 추론\nHPA min 1")
                with group("report-service (같은 이미지 · Deployment 2개)", GRAY):
                    report_api = comp([Fastapi, Postgresql], "report-api", "리포트 조회\nDB: report_db · HPA min 1")
                    worker = comp([Fastapi], "report-worker",
                                  "learning 기록 조회 → 리포트 생성\nOutbox · KEDA 큐 길이 기반 0~N")
                common = comp([Netpol, Secret, Job], "공통 리소스 (app-service chart)",
                              "NetworkPolicy 기본 거부 · ExternalSecret\nmigration-job (Argo CD PreSync)", size=60)

            with group("namespace: platform", PLATFORM):
                mq = comp([Rabbitmq], "RabbitMQ", "cmd.direct · events.topic · dlx")
                comp([Redis], "Redis", "core 레플리카 간 SSE 중계")
                messages = table(
                    "메시지 (실패 시 1·5·15분 재시도 3회 → DLQ)",
                    ["메시지", "생산", "소비"],
                    [["report.generate (명령)", "core", "report-worker"],
                     ["report.started · completed · failed", "report-worker", "core"],
                     ["llm.usage.recorded", "ai · scoring", "core"],
                     ["student.deleted", "core", "learning · report-worker"],
                     ["model.version.activated", "core", "ai · scoring (Pod별 큐)"]],
                    line="#e8590c", head_fill="#fff4e6")

        # 진입과 SSE
        web >> http("HTTPS") >> ingress >> http() >> core
        core >> _edge(SSE, "SSE", "bold", constraint="false") >> web
        ingress >> invis() >> common

        # 동기 HTTP (api-spec 4장 호출 관계, report-worker → learning은 노드 설명으로 표기)
        core >> http("미션 · 피드백") >> learning
        core >> http("리포트 조회") >> report_api
        core >> http("분석 대화") >> ai
        learning >> http("판정 · 되묻기", reverse=True) >> ai
        ai >> http("M2 · M1") >> scoring
        worker >> http("서술 생성") >> ai

        # 메시지: app 영역 전체와 RabbitMQ를 한 선으로 묶고 생산·소비는 표로 표기
        core >> msg("명령 · 이벤트", reverse=True, ltail=cluster_id("namespace: app")) >> mq
        mq >> invis() >> messages


def _layer(name, color, fill, rows, **attrs):
    body = "".join(f'<TR><TD ALIGN="LEFT"><FONT FACE="{BOLD}" POINT-SIZE="16" COLOR="{color}">{escape(k)}</FONT>'
                   f'</TD><TD ALIGN="LEFT"><FONT POINT-SIZE="16">{escape(v)}</FONT></TD></TR>' for k, v in rows)
    return Node(f'<<TABLE STYLE="rounded" BORDER="2" CELLBORDER="0" COLOR="{color}" BGCOLOR="{fill}" CELLSPACING="0" '
                f'CELLPADDING="6"><TR><TD COLSPAN="2" ALIGN="LEFT"><FONT FACE="{BOLD}" POINT-SIZE="20" '
                f'COLOR="{color}">{escape(name)}</FONT></TD></TR>{body}</TABLE>>', **BOX, **attrs)


def layered():
    blue, green, orange, purple = "#1c7ed6", "#2f9e44", "#e8590c", "#7048e8"
    with diagram("04-layered", "레이어드 아키텍처 (기능 단위 패키지 + 기능 내부 4계층)", direction="TB",
                 nodesep="0.9", ranksep="0.9"):
        with group("백엔드: <service>/<기능>/  (예: learning-service/answer/)", NS):
            pres = _layer("Presentation", blue, "#e7f5ff",
                          [("Spring", "controller · consumer · scheduler"), ("Python", "router.py · consumer.py"),
                           ("책임", "HTTP · 메시지 수신, DTO 검증, ACK")], group="layers")
            app = _layer("Application", green, "#ebfbee",
                         [("Spring", "service · facade"), ("Python", "service.py · graph.py · nodes/"),
                          ("책임", "업무 흐름, 트랜잭션 경계, Outbox 기록")], group="layers")
            infra = _layer("Infrastructure", orange, "#fff4e6",
                           [("Spring", "repository · client · messaging"),
                            ("Python", "repository.py · clients/ · messaging/ · llm/"),
                            ("책임", "DB · 외부 API · 브로커 · LLM · S3 연동")], group="layers")
            domain = _layer("Domain", purple, "#f3f0ff",
                            [("Spring", "domain"), ("Python", "models.py · state.py"),
                             ("책임", "엔티티 · 상태 전이 규칙, 프레임워크 의존 없음")])
        down = {"color": "#495057", "penwidth": "2.4"}
        pres >> edge(**down) >> app >> edge(**down) >> infra
        ref = {"color": purple, "style": "dashed"}
        pres >> edge(label=pad("참조"), fontcolor=purple, **ref) >> domain
        app >> edge(constraint="false", **ref) >> domain
        infra >> edge(constraint="false", **ref) >> domain

        with group("예시: learning 답변 제출 · 피드백", GRAY):
            ctrl = card("AnswerController", "요청 검증 · Idempotency-Key", "#e7f5ff", blue)
            svc = card("AnswerService", "@Transactional 답변 버전 저장", "#ebfbee", green)
            facade = card("FeedbackFacade", "판정 상태 전이, AI 호출은 트랜잭션 밖", "#ebfbee", green)
            repo = card("AnswerRepository", "MyBatis → PostgreSQL", "#fff4e6", orange)
            ai_client = card("AiClient", "→ ai-service", "#fff4e6", orange)
            answer = card("Answer", "버전 증가 · 덮어쓰기 금지", "#f3f0ff", purple)
        ctrl >> svc >> repo
        svc >> edge(style="dashed", color=purple) >> answer
        ctrl >> facade >> ai_client

        with group("frontend/web", ("#f3fbfc", "#1098ad")):
            f_pres = card("presentation", "페이지 · 컴포넌트", "#ffffff", "#1098ad")
            f_data = card("data", "API 클라이언트 · SSE · TanStack Query", "#ffffff", "#1098ad")
            f_domain = card("domain", "타입 · 화면 규칙", "#ffffff", "#1098ad")
        f_pres >> f_data
        [f_pres, f_data] >> edge(style="dashed", color="#1098ad") >> f_domain

        rules = table("의존 규칙", ["규칙", "내용"],
                      [["방향", "Presentation → Application → Infrastructure 단방향, 계층 건너뛰기 금지"],
                       ["Domain", "모든 레이어가 참조, Domain은 다른 레이어 참조 금지"],
                       ["기능 간", "상대 기능 service로만 호출, 여러 기능 흐름은 facade로 조합"],
                       ["트랜잭션", "Application에서만 시작, 트랜잭션 안 외부 HTTP · AMQP 호출 금지"],
                       ["적용 범위", "core · learning · report 4계층 / ai · scoring Domain 제외 3계층"],
                       ["프론트", "presentation → data, core-service 공개 API만 호출"]])
        infra >> invis() >> rules


def cicd_observability():
    with diagram("05-cicd-observability", "CI/CD (GitOps) · 관측 구성도", ranksep="0.9"):
        with group("CI/CD (GitOps)", K8S):
            repo = comp([Github], "모노레포", "backend · frontend · contracts")
            actions = comp([GithubActions], "GitHub Actions", "경로 필터 → 변경 서비스만\n테스트 · 빌드 · 계약 검사")
            ghcr = card("GHCR", "local 이미지 push")
            ecr = comp([ECR], "ECR", "prod 이미지 push (OIDC)")
            gitops = comp([Github], "gitops 태그 갱신 커밋", "environments/<env>/")
            argo = comp([Argocd], "Argo CD", "자동 동기화 · ApplicationSet\nHelm chart")
            kind = card("kind (local)", "ingress-nginx · Calico\nstub (LLM · 토스)", "#e7f5ff", HTTP)
            eks = card("EKS (prod)", "AWS LB Controller\nCluster Autoscaler", "#fff4e6", "#ff9900")

        legend([("#7b8894", "━━━", "빌드 · 배포 흐름"), ("#7b8894", "- - -", "이미지 pull")])
        repo >> actions >> [ghcr, ecr]
        actions >> gitops >> argo >> [kind, eks]
        ghcr >> edge(style="dashed") >> kind
        ecr >> edge(style="dashed") >> eks

        with group("관측 (namespace: observability)", ("#f8f5ff", "#7048e8")):
            apps = card("app 서비스", "core · learning · ai\nscoring · report")
            otel = card("OpenTelemetry Collector", "traceparent: HTTP 헤더 + 이벤트 봉투")
            prom = comp([Prometheus], "Prometheus", "서비스 지표 · 큐 길이 · DLQ")
            grafana = comp([Grafana], "Grafana", "대시보드 · Alerting")
            langfuse = card("Langfuse", "ai · scoring LLM 호출\n토큰 · 비용 · trace")
        discord = comp([Discord], "팀 디스코드", "오류율 · 지연 · 적체\nLLM 비용 80% 경보")

        apps >> otel >> prom >> grafana >> discord
        apps >> langfuse


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    overview()
    aws()
    services()
    layered()
    cicd_observability()
