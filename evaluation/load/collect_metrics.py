"""부하 시험 한 단계의 서버 지표 요약 (#361).

k6가 재지 못하는 서버 쪽 지표를 시험 시간대(시작~끝)로 모은다.
- Prometheus(관측 스택, Pod 안에서 조회): core·learning JVM CPU·스레드·힙, DB 연결 풀, core HTTP p95, RabbitMQ 적체
- CloudWatch: RDS CPU·연결, ALB 5xx·응답 시간, NAT 연결·포트 할당 오류
- Kubernetes: app 네임스페이스 Pod 재시작 횟수

사용: python evaluation/load/collect_metrics.py --kubeconfig <AWS kubeconfig> --start 2026-11-05T11:30:00+09:00 --end 2026-11-05T11:38:00+09:00
조회만 한다. 비밀 값은 다루지 않는다.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import urllib.parse
from datetime import datetime

PROFILE = "sagomungchi-provided"
REGION = "ap-northeast-2"
RDS_ID = "sagomungchi-demo-db"
ALB_DIM = "app/sagomungchi-demo-core/1eda1209ceafe116"
NAT_ID = "nat-0e2085c827c381d79"

# (이름, PromQL, 집계). 집계는 시간대 안의 max 또는 avg.
PROM = [
    ("JVM CPU 사용률 최대(1코어=1.0)", 'max by (exported_job) (jvm_cpu_recent_utilization_ratio{exported_job=~"core-service|learning-service"})', "max"),
    ("JVM CPU 사용률 평균", 'max by (exported_job) (jvm_cpu_recent_utilization_ratio{exported_job=~"core-service|learning-service"})', "avg"),
    ("JVM 스레드 수", 'max by (exported_job) (sum by (exported_job, exported_instance) (jvm_thread_count{exported_job=~"core-service|learning-service"}))', "max"),
    ("JVM 힙 사용(MiB)", 'max by (exported_job) (sum by (exported_job, exported_instance) (jvm_memory_used_bytes{exported_job=~"core-service|learning-service",jvm_memory_type="heap"})) / 1048576', "max"),
    ("DB 풀 최대 크기", 'max by (exported_job) (db_client_connections_max{exported_job=~"core-service|learning-service"})', "max"),
    ("DB 풀 사용 중 연결", 'max by (exported_job) (sum by (exported_job, exported_instance) (db_client_connections_usage{exported_job=~"core-service|learning-service",state="used"}))', "max"),
    ("DB 풀 대기 요청", 'max by (exported_job) (sum by (exported_job, exported_instance) (db_client_connections_pending_requests{exported_job=~"core-service|learning-service"}))', "max"),
    ("DB 풀 평균 대기(ms, 1분)", 'sum by (exported_job) (rate(db_client_connections_wait_time_milliseconds_sum{exported_job=~"core-service|learning-service"}[1m])) / clamp_min(sum by (exported_job) (rate(db_client_connections_wait_time_milliseconds_count{exported_job=~"core-service|learning-service"}[1m])), 1e-9)', "max"),
    ("core HTTP p95(ms, 1분, SSE 포함)", 'histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{exported_job="core-service"}[1m]))) * 1000', "max"),
    ("core HTTP 처리량(req/s)", 'sum(rate(http_server_request_duration_seconds_count{exported_job="core-service"}[1m]))', "max"),
    ("core HTTP 5xx(req/s)", 'sum(rate(http_server_request_duration_seconds_count{exported_job="core-service",http_response_status_code=~"5.."}[1m]))', "max"),
    ("RabbitMQ ready 합", "sum(rabbitmq_queue_messages_ready)", "max"),
    ("RabbitMQ unacked 합", "sum(rabbitmq_queue_messages_unacked)", "max"),
]

CW = [
    ("RDS CPU(%)", "AWS/RDS", "CPUUtilization", [("DBInstanceIdentifier", RDS_ID)], "Maximum"),
    ("RDS 연결 수", "AWS/RDS", "DatabaseConnections", [("DBInstanceIdentifier", RDS_ID)], "Maximum"),
    ("ALB 대상 응답 시간 p95(s)", "AWS/ApplicationELB", "TargetResponseTime", [("LoadBalancer", ALB_DIM)], "p95"),
    ("ALB 요청 수(분당 최대)", "AWS/ApplicationELB", "RequestCount", [("LoadBalancer", ALB_DIM)], "Sum"),
    ("ALB 5xx(ELB)", "AWS/ApplicationELB", "HTTPCode_ELB_5XX_Count", [("LoadBalancer", ALB_DIM)], "Sum"),
    ("ALB 5xx(대상)", "AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", [("LoadBalancer", ALB_DIM)], "Sum"),
    ("NAT 활성 연결", "AWS/NATGateway", "ActiveConnectionCount", [("NatGatewayId", NAT_ID)], "Maximum"),
    ("NAT 포트 할당 오류", "AWS/NATGateway", "ErrorPortAllocation", [("NatGatewayId", NAT_ID)], "Sum"),
    ("NAT 대상 송신(바이트, 분당 최대)", "AWS/NATGateway", "BytesOutToDestination", [("NatGatewayId", NAT_ID)], "Sum"),
]


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8", timeout=90).stdout


def prom(kubeconfig: str, query: str, start: datetime, end: datetime) -> list[dict]:
    qs = urllib.parse.urlencode({"query": query, "start": start.timestamp(), "end": end.timestamp(), "step": "15"})
    out = run(["kubectl", "--kubeconfig", kubeconfig, "exec", "-n", "observability", "deploy/prometheus", "--",
               "wget", "-qO-", f"http://127.0.0.1:9090/api/v1/query_range?{qs}"])
    return json.loads(out)["data"]["result"]


def cloudwatch(namespace: str, metric: str, dims: list[tuple[str, str]], stat: str, start: datetime, end: datetime) -> list[float]:
    cmd = ["aws", "--profile", PROFILE, "--region", REGION, "cloudwatch", "get-metric-statistics",
           "--namespace", namespace, "--metric-name", metric, "--start-time", start.isoformat(), "--end-time", end.isoformat(),
           "--period", "60", "--output", "json", "--dimensions", *[f"Name={k},Value={v}" for k, v in dims]]
    cmd += ["--extended-statistics", stat] if stat.startswith("p") else ["--statistics", stat]
    points = json.loads(run(cmd))["Datapoints"]
    return [p["ExtendedStatistics"][stat] if stat.startswith("p") else p[stat] for p in points]


def restarts(kubeconfig: str) -> dict[str, int]:
    pods = json.loads(run(["kubectl", "--kubeconfig", kubeconfig, "get", "pods", "-n", "app", "-o", "json"]))["items"]
    return {p["metadata"]["name"]: sum(c.get("restartCount", 0) for c in p["status"].get("containerStatuses", []))
            for p in pods if p["status"].get("phase") == "Running"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kubeconfig", required=True)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--json", help="요약을 JSON으로도 저장할 경로")
    args = parser.parse_args()

    summary: dict[str, object] = {"start": args.start.isoformat(), "end": args.end.isoformat()}
    print(f"== 서버 지표 {args.start:%H:%M:%S} ~ {args.end:%H:%M:%S} ==")
    for name, query, agg in PROM:
        try:
            series = prom(args.kubeconfig, query, args.start, args.end)
        except Exception as error:  # 조회 실패는 표시만 하고 다음 지표로 간다
            print(f"{name}: 조회 실패 {type(error).__name__}")
            continue
        for s in series:
            values = [float(v) for _, v in s["values"] if v not in ("NaN", "+Inf", "-Inf")]
            if not values:
                continue
            value = max(values) if agg == "max" else sum(values) / len(values)
            label = s["metric"].get("exported_job", "")
            key = f"{name}{' [' + label + ']' if label else ''}"
            summary[key] = round(value, 3)
            print(f"{key}: {value:.3f}")
    for name, namespace, metric, dims, stat in CW:
        try:
            values = cloudwatch(namespace, metric, dims, stat, args.start, args.end)
        except Exception as error:
            print(f"{name}: 조회 실패 {type(error).__name__}")
            continue
        value = max(values) if values else None
        summary[name] = value
        print(f"{name}: {value if value is not None else '데이터 없음'}")
    summary["Pod 재시작"] = restarts(args.kubeconfig)
    print("Pod 재시작:", summary["Pod 재시작"])
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
