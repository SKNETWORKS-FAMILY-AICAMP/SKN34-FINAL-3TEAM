"""Isolated Docker integration test. Never connects to a team webhook or Kubernetes."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from render import build


def serve():
    state = {"ready": 0, "empty": False, "received": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path == "/metrics":
                body = "" if state["empty"] else (
                    "# TYPE rabbitmq_queue_messages_ready gauge\n"
                    f'rabbitmq_queue_messages_ready {state["ready"]}\n')
            else:
                body = json.dumps(state)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4" if self.path == "/metrics" else "application/json")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            if self.path == "/control":
                state.update(data)
            else:
                # Local Discord protocol double: retain only status markers, no URLs or raw body.
                text = json.dumps(data)
                state["received"].append({"firing": "FIRING" in text.upper(),
                                          "resolved": "RESOLVED" in text.upper(),
                                          "nodata": "DatasourceNoData" in text,
                                          "error": "DatasourceError" in text})
            self.send_response(204)
            self.end_headers()

    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode:
        # Do not echo commands/output that might contain runtime-only credentials.
        raise RuntimeError("Docker operation failed: " + args[0])
    return result.stdout.strip()


def eventually(fn, description, seconds=100):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if fn():
                print("PASS " + description, flush=True)
                return
        except (OSError, ValueError, KeyError, RuntimeError):
            pass
        time.sleep(2)
    raise AssertionError(description + " timed out")


def integration(faults_only=False, scrape_only=False, chart_bundle=None):
    faults_only = faults_only or scrape_only
    prefix = "issue187-" + uuid.uuid4().hex[:10]
    names = []
    network_created = False
    with tempfile.TemporaryDirectory(prefix="issue187-") as directory:
        root = Path(directory)
        alert_dir = root / "alerting"
        ds_dir = root / "datasources"
        alert_dir.mkdir()
        ds_dir.mkdir()
        config = dict(environment="verification", datasource_uid="issue187-prometheus",
                      backlog_messages=10, pending_seconds=10, interval_seconds=10,
                      group_wait_seconds=1, group_interval_seconds=10, repeat_interval_seconds=300,
                      secret_name="issue187-test", secret_key="DISCORD_WEBHOOK_URL")
        provisioning, patch = build(config)
        chart = json.loads(chart_bundle.read_text(encoding="utf-8")) if chart_bundle else None
        if chart:
            provisioning = chart["alerting"]
            patch["spec"]["template"]["spec"]["containers"][0] = chart["grafana_container"]
        for invalid in ({}, dict(config, backlog_messages=0), dict(config, secret_name=""),
                        dict(config, repeat_interval_seconds=11)):
            try:
                build(invalid)
            except ValueError:
                continue
            raise AssertionError("invalid configuration accepted")
        assert patch["spec"]["template"]["spec"]["containers"][0]["env"][0]["valueFrom"]["secretKeyRef"]["optional"] is False
        print("PASS invalid/missing inputs rejected; Secret reference required", flush=True)
        alert_file = alert_dir / "alerts.json"
        alert_file.write_text(json.dumps(provisioning), encoding="utf-8")
        datasource_text = json.dumps({"apiVersion": 1, "datasources": [{
            "name": "Prometheus", "uid": config["datasource_uid"], "type": "prometheus",
            "url": "http://" + prefix + "-prom:9090", "access": "proxy", "isDefault": True}]})
        (ds_dir / "prometheus.yaml").write_text(chart["datasource_text"] if chart else datasource_text, encoding="utf-8")
        (root / "prometheus.yml").write_text(
            "global:\n  scrape_interval: 2s\nscrape_configs:\n"
            f"  - job_name: rabbitmq\n    static_configs:\n      - targets: ['{prefix}-fixture:8080']\n"
            f"  - job_name: otel-collector\n    static_configs:\n      - targets: ['{prefix}-fixture:8080']\n", encoding="utf-8")
        try:
            docker("network", "create", "--internal", prefix)
            network_created = True

            def run(suffix, image, *args, options=()):
                name = prefix + "-" + suffix
                names.append(name)
                docker("run", "-d", "--name", name, "--network", prefix, *options, image, *args)
                return name

            fixture = run("fixture", "python:3.12-slim", "python", "/test/verify.py", "--serve", options=(
                "--memory", "96m", "--cpus", "0.25", "-v",
                str(Path(__file__).resolve().parent) + ":/test:ro"))
            control = run("control", "python:3.12-slim", "python", "-c", "import time; time.sleep(3600)",
                          options=("--memory", "64m", "--cpus", "0.25"))

            def local_request(url, body=None, auth=False):
                code = ("import json,urllib.request,base64; "
                        "headers={'Content-Type':'application/json'}; "
                        + ("headers['Authorization']='Basic '+base64.b64encode(b'admin:issue187-test-only').decode(); " if auth else "")
                        + "req=urllib.request.Request(" + repr(url) + ",data="
                        + ("None" if body is None else repr(json.dumps(body).encode()))
                        + ",headers=headers); "
                        "data=urllib.request.urlopen(req,timeout=5).read(); "
                        "print(data.decode() if data else 'null')")
                return json.loads(docker("exec", control, "python", "-c", code))
            if not faults_only:
                (root / "enabled_plugins").write_text("[rabbitmq_prometheus].\n", encoding="utf-8")
                rabbit = run("rabbit", "rabbitmq:4.3.7-management-alpine", options=(
                    "--memory", "384m", "--cpus", "0.5", "-e", "RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS=+S 1:1",
                    "-v", str(root / "enabled_plugins") + ":/etc/rabbitmq/enabled_plugins:ro"))

                def rabbit_metrics():
                    try:
                        result = docker("exec", fixture, "python", "-c",
                            "import urllib.request; s=urllib.request.urlopen('http://" + rabbit +
                            ":15692/metrics').read().decode(); "
                            "assert '# TYPE rabbitmq_queue_messages_ready gauge' in s; "
                            "assert not any('queue=' in l for l in s.splitlines() if l.startswith('rabbitmq_queue_messages_ready')); "
                            "print('aggregate gauge confirmed')")
                        return result == "aggregate gauge confirmed"
                    except RuntimeError:
                        return False

                eventually(rabbit_metrics, "RabbitMQ 4.3.7 actual aggregate gauge without queue labels", 120)
                docker("stop", rabbit)
            run("prom", "prom/prometheus:v3.15.1", "--config.file=/etc/prometheus/prometheus.yml", "--query.lookback-delta=10s", options=(
                "--memory", "256m", "--cpus", "0.5", "--network-alias", "prometheus.observability.svc.cluster.local",
                "--tmpfs", "/prometheus:uid=65534,gid=65534", "-v", str(root / "prometheus.yml") + ":/etc/prometheus/prometheus.yml:ro"))
            # Only a local receiver on an internal network. No real webhook URL exists in this test.
            gf = run("grafana", "grafana/grafana:13.3.0", options=(
                "--memory", "512m", "--cpus", "1",
                "-e", "GF_SECURITY_ADMIN_PASSWORD=issue187-test-only",
                "-e", "GF_ANALYTICS_REPORTING_ENABLED=false", "-e", "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
                "-e", "GF_UNIFIED_ALERTING_EVALUATION_TIMEOUT=5s",
                "-e", "OPS_DISCORD_WEBHOOK_URL=http://" + fixture + ":8080/discord",
                "-v", str(alert_dir) + ":/etc/grafana/provisioning/alerting:ro",
                "-v", str(ds_dir) + ":/etc/grafana/provisioning/datasources:ro"))

            fixture_url = "http://" + fixture + ":8080"
            gf_url = "http://" + gf + ":3000"
            api = lambda path, body=None: local_request(gf_url + path, body, auth=True)

            def healthy():
                if docker("inspect", "--format", "{{.State.Status}}", gf) == "exited":
                    raise AssertionError("Grafana exited during startup; inspect its local provisioning/configuration")
                return api("/api/health")["database"] == "ok"

            eventually(healthy, "Grafana 13.3.0 startup/provisioning", 180)
            missing = run("missing-secret", "grafana/grafana:13.3.0", "-ec",
                          patch["spec"]["template"]["spec"]["containers"][0]["args"][0],
                          options=("--entrypoint", "/bin/sh", "--memory", "128m"))
            eventually(lambda: docker("inspect", "--format", "{{.State.Status}}:{{.State.ExitCode}}", missing) == "exited:1",
                       "missing webhook environment fails before Grafana starts")

            def rules():
                return [rule for group in api("/api/prometheus/grafana/api/v1/rules")["data"]["groups"] for rule in group["rules"]]

            def backlog():
                return next(r for r in rules() if r["name"] == "RabbitMQ aggregate ready backlog")

            eventually(lambda: len(rules()) == 3 and all(r["state"] == "inactive" and r["health"] == "ok"
                       and not r["lastEvaluation"].startswith("0001") for r in rules()), "three real engine rules evaluated normal")
            if not faults_only:
                local_request(fixture_url + "/control", {"ready": 20})
                eventually(lambda: backlog()["state"] == "pending", "normal to pending")
                eventually(lambda: backlog()["state"] == "firing", "pending to firing")
                eventually(lambda: any(x["firing"] for x in local_request(fixture_url)["received"]), "Discord integration delivered to local receiver")
                count = len(local_request(fixture_url)["received"])
                time.sleep(20)
                assert backlog()["state"] == "firing"
                assert len(local_request(fixture_url)["received"]) == count
                print("PASS sustained firing; repeat suppressed over 20 seconds", flush=True)
                local_request(fixture_url + "/control", {"ready": 0})
                eventually(lambda: backlog()["state"] == "inactive", "recovery")
                eventually(lambda: any(x["resolved"] for x in local_request(fixture_url)["received"]), "local resolved notification")
            if not scrape_only:
                local_request(fixture_url + "/control", {"empty": True})
                # Prometheus instant queries may use a last sample for up to the lookback window.
                # Use an explicit missing metric for a deterministic no-data engine test.
                rule = provisioning["groups"][0]["rules"][2]
                original = rule["data"][0]["model"]["expr"]

                def reload():
                    alert_file.write_text(json.dumps(provisioning), encoding="utf-8")
                    api("/api/admin/provisioning/alerting/reload", {})

                rule["data"][0]["model"]["expr"] = "issue187_missing_metric"
                reload()
                eventually(lambda: backlog()["health"] == "nodata" and any(a.get("state") == "NoData" for a in backlog().get("alerts", [])), "NoData remains a distinct engine state")
                eventually(lambda: any(x["nodata"] for x in local_request(fixture_url)["received"]), "NoData notification routed to local receiver")
                rule["data"][0]["model"]["expr"] = "invalid("
                reload()
                eventually(lambda: backlog()["health"] == "error", "invalid query reports engine error")
                eventually(lambda: any(x["error"] for x in local_request(fixture_url)["received"]), "query error notification routed to local receiver")
                last_evaluation = backlog()["lastEvaluation"]
                rule["data"][0]["model"]["expr"] = original
                rule["data"][0]["datasourceUid"] = "issue187-missing-datasource"
                reload()
                eventually(lambda: backlog()["health"] == "error" and backlog()["lastEvaluation"] != last_evaluation,
                           "missing datasource reports a fresh engine error")
                rule["data"][0]["datasourceUid"] = config["datasource_uid"]
                local_request(fixture_url + "/control", {"empty": False, "ready": 0})
                reload()
                reload()
                eventually(lambda: len(rules()) == 3 and all(r["health"] == "ok" for r in rules()), "reapply restores three unique rules")
                contacts = api("/api/v1/provisioning/contact-points")
                assert len([c for c in contacts if c["uid"] == "ops187-discord"]) == 1
                print("PASS stable contact UID after reapply", flush=True)
            # Stop only our fixture: real Prometheus target up changes to 0.
            docker("stop", fixture)
            eventually(lambda: all(r["state"] == "firing" for r in rules() if "scrape unavailable" in r["name"]), "both scrape failures fire")
            (root / "prometheus.yml").write_text("global:\n  scrape_interval: 2s\nscrape_configs: []\n", encoding="utf-8")
            docker("kill", "--signal", "HUP", prefix + "-prom")
            eventually(lambda: not local_request("http://" + prefix + "-prom:9090/api/v1/targets")["data"]["activeTargets"], "Prometheus accepted removal of both jobs")
            eventually(lambda: all(r["state"] == "firing" and any("instance" not in a.get("labels", {}) for a in r.get("alerts", []))
                                   for r in rules() if "scrape unavailable" in r["name"]), "removed scrape jobs fire via absent")
        finally:
            for name in reversed(names):
                subprocess.run(["docker", "rm", "-f", "-v", name], capture_output=True)
            if network_created:
                subprocess.run(["docker", "network", "rm", prefix], capture_output=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--faults-only", action="store_true", help="Resume fault checks without repeating passed lifecycle tests")
    parser.add_argument("--scrape-only", action="store_true", help="Resume only scrape failure/removal checks")
    parser.add_argument("--chart-bundle", type=Path, help="Use actual rendered Helm provisioning and Grafana command")
    args = parser.parse_args()
    serve() if args.serve else integration(args.faults_only, args.scrape_only, args.chart_bundle)
