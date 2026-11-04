"""Helm compatibility checks, then run actual rendered provisioning in Docker."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import yaml  # Verification only; not a production dependency.


def run(*args, expect_success=True):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if (result.returncode == 0) != expect_success:
        raise AssertionError("Unexpected result from " + str(args[0]) + ": " + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--helm", required=True)
    parser.add_argument("--baseline", default="de8e225c30d1e156347379b59cb9c34b73dafe37",
                        help="Fetched base commit whose rendered resources must remain unchanged")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    chart_path = "infrastructure/gitops/charts/observability"
    chart = repo / chart_path
    base = run("git", "-C", str(repo), "rev-parse", "--verify", args.baseline + "^{commit}").strip()
    run("git", "-C", str(repo), "merge-base", "--is-ancestor", base, "HEAD")
    environments = repo / "infrastructure/gitops/environments"
    prod = environments / "prod/observability.json"
    load = lambda text: [doc for doc in yaml.safe_load_all(text) if doc]
    identify = lambda docs: {(d["kind"], d["metadata"]["name"]): d for d in docs}
    with tempfile.TemporaryDirectory(prefix="issue187-chart-") as directory:
        root = Path(directory)
        baseline = root / "baseline"
        for path in run("git", "-C", str(repo), "ls-tree", "-r", "--name-only", base, chart_path).splitlines():
            target = baseline / Path(path).relative_to(chart_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(run("git", "-C", str(repo), "show", base + ":" + path), encoding="utf-8")
        # prod values gained #187 rules, so compare the chart change with the baseline's own prod values.
        base_prod = root / "base-prod.json"
        base_prod.write_text(run("git", "-C", str(repo), "show", base + ":" + prod.relative_to(repo).as_posix()), encoding="utf-8")
        for extra in ([], ["-f", str(environments / "local/observability.yaml")], ["-f", str(base_prod)]):
            before = load(run(args.helm, "template", "observability", str(baseline), "--namespace", "observability", *extra))
            after = load(run(args.helm, "template", "observability", str(chart), "--namespace", "observability", *extra))
            # Source filenames can reorder resources, so compare by Kubernetes identity.
            assert identify(before) == identify(after), "Existing default/local/prod resources changed"
            run(args.helm, "lint", "--strict", str(chart), *extra)
        print("PASS Helm default/local/baseline-prod resources identical to baseline " + base, flush=True)
        run(args.helm, "lint", "--strict", str(chart), "-f", str(prod))
        prod_rendered = identify(load(run(args.helm, "template", "observability", str(chart), "--namespace", "observability", "-f", str(prod))))
        assert "rabbitmq-dlq" in prod_rendered["ConfigMap", "prometheus-config"]["data"]["prometheus.yml"]
        print("PASS current prod values lint and enable the DLQ scrape", flush=True)
        # Tempo: Collector pipeline, datasource, policies, and Pod rolls for config that is read only at start.
        collector = yaml.safe_load(prod_rendered["ConfigMap", "otel-collector-config"]["data"]["config.yaml"])
        assert collector["service"]["pipelines"]["traces"]["exporters"] == ["otlp/tempo"]
        sources = yaml.safe_load(prod_rendered["ConfigMap", "grafana-datasources"]["data"]["prometheus.yaml"])["datasources"]
        assert [(d["name"], d["uid"]) for d in sources] == [("Prometheus", "prometheus"), ("Tempo", "tempo")]
        assert ("NetworkPolicy", "tempo") in prod_rendered and ("PersistentVolumeClaim", "tempo-data") in prod_rendered
        egress = lambda name: [p["podSelector"]["matchLabels"].get("app.kubernetes.io/name") for rule in
                               prod_rendered["NetworkPolicy", name]["spec"]["egress"] for p in rule["to"] if "podSelector" in p]
        assert "tempo" in egress("otel-collector") and "tempo" in egress("grafana")
        for name, key in (("otel-collector", "ops187/tempo-traces"), ("grafana", "ops187/tempo-datasource")):
            assert prod_rendered["Deployment", name]["spec"]["template"]["metadata"]["annotations"][key] == "enabled"
        app_chart = repo / "infrastructure/gitops/charts/app-service"
        for service, java in (("core-service", True), ("learning-service", True), ("report-worker", False)):
            pod = identify(load(run(args.helm, "template", service, str(app_chart), "-f",
                                    str(environments / "prod" / (service + ".json")))))["Deployment", service]
            env = {e["name"]: e.get("value") for e in pod["spec"]["template"]["spec"]["containers"][0]["env"]}
            assert env["OTEL_TRACES_EXPORTER"] == "otlp" and env["OTEL_SERVICE_NAME"] == service
            assert env["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://otel-collector.observability.svc.cluster.local:4318"
            # A JAVA_TOOL_OPTIONS from values must not replace the agent flag.
            assert ("-javaagent:/otel/javaagent.jar" in env.get("JAVA_TOOL_OPTIONS", "")) is java
        print("PASS prod values enable Tempo and OTLP trace export for core, learning and report-worker", flush=True)

        # Accelerated copy of the prod rules; not operating thresholds.
        alerting = json.loads(prod.read_text(encoding="utf-8"))["grafana"]["alerting"]
        rules = [dict(rule, **{"for": "10s"}) for rule in alerting["rules"]]
        backlog = next(rule for rule in rules if "rabbitmq_queue_messages_ready" in rule["expr"])
        backlog["threshold"] = 10
        values = {"prometheus": {"rabbitmqDlqMetrics": {"enabled": True}},
                  "grafana": {"alerting": {"enabled": True, "discordSecretName": "issue187-test",
                                           "interval": "10s", "groupWait": "1s", "groupInterval": "10s",
                                           "repeatInterval": "300s", "rules": rules}}}
        values_file = root / "values.json"
        values_file.write_text(json.dumps(values), encoding="utf-8")
        run(args.helm, "lint", "--strict", str(chart), "-f", str(values_file))
        rendered = load(run(args.helm, "template", "observability", str(chart), "--namespace", "observability", "-f", str(values_file)))
        by_name = identify(rendered)
        provisioning = yaml.safe_load(by_name["ConfigMap", "grafana-alerting"]["data"]["alerting.yaml"])
        assert [r["uid"] for r in provisioning["groups"][0]["rules"]] == [r["uid"] for r in rules]
        no_data = {r["uid"]: r["noDataState"] for r in provisioning["groups"][0]["rules"]}
        assert {u for u, state in no_data.items() if state == "OK"} == {r["uid"] for r in rules if r.get("noDataState") == "OK"}
        assert all(state in ("OK", "NoData") for state in no_data.values())
        assert provisioning["groups"][0]["interval"] == "10s"
        datasource = by_name["ConfigMap", "grafana-datasources"]["data"]["prometheus.yaml"]
        pod = by_name["Deployment", "grafana"]["spec"]["template"]["spec"]
        container = next(c for c in pod["containers"] if c["name"] == "grafana")
        secret = next(e for e in container["env"] if e["name"] == "DISCORD_WEBHOOK_URL")["valueFrom"]["secretKeyRef"]
        assert secret["name"] == "issue187-test" and secret.get("optional") is not True
        assert any(v.get("configMap", {}).get("name") == "grafana-alerting" for v in pod["volumes"])
        print("PASS enabled values render alerting provisioning, mount and required webhook Secret", flush=True)
        scrape = yaml.safe_load(by_name["ConfigMap", "prometheus-config"]["data"]["prometheus.yml"])
        dlq_job = next(j for j in scrape["scrape_configs"] if j["job_name"] == "rabbitmq-dlq")
        assert dlq_job["metrics_path"] == "/metrics/detailed"
        assert dlq_job["params"] == {"family": ["queue_coarse_metrics"]}
        assert [j["job_name"] for j in scrape["scrape_configs"]] == ["otel-collector", "rabbitmq", "rabbitmq-dlq"]
        # Without a Pod template change an upgrade leaves Prometheus on the old scrape config.
        prometheus_pod = by_name["Deployment", "prometheus"]["spec"]["template"]["metadata"]
        assert prometheus_pod.get("annotations", {}).get("ops187/rabbitmq-dlq-scrape") == "enabled"
        keep = dlq_job["metric_relabel_configs"][0]
        definitions = json.loads((repo / "infrastructure/gitops/charts/platform-data/files/rabbitmq/definitions.json")
                                 .read_text(encoding="utf-8"))
        queues = [q["name"] for q in definitions["queues"]]
        # Prometheus anchors relabel regexes; separator ';' joins source label values.
        kept = [q for q in queues if re.fullmatch(keep["regex"], "rabbitmq_detailed_queue_messages;" + q)]
        expected = [q for q in queues if q.endswith(".dlq")]
        assert expected and kept == expected, "DLQ relabel must keep exactly the defined <queue>.dlq queues"
        assert not re.fullmatch(keep["regex"], "rabbitmq_detailed_queue_messages_ready;" + expected[0])
        print("PASS DLQ scrape keeps only total messages of " + str(len(expected)) + " defined <queue>.dlq queues", flush=True)
        invalid = json.loads(json.dumps(values))
        invalid["prometheus"]["rabbitmqDlqMetrics"]["enabled"] = False
        invalid_file = root / "invalid.json"
        invalid_file.write_text(json.dumps(invalid), encoding="utf-8")
        run(args.helm, "template", "observability", str(chart), "-f", str(invalid_file), expect_success=False)
        print("PASS Helm rejects a DLQ rule without its scrape job", flush=True)
        bundle = root / "bundle.json"
        bundle.write_text(json.dumps({
            "alerting": provisioning, "datasource_text": datasource, "dlq_job": dlq_job,
            "titles": {"target": next(r["title"] for r in rules if "up{" in r["expr"]), "backlog": backlog["title"],
                       **{key: next(r["title"] for r in rules if r["uid"] == uid) for key, uid in (
                           ("dlq", "rabbitmq-dlq-depth"), ("budget", "llm-budget-80"), ("unpriced", "llm-unpriced-calls"),
                           ("missing", "app-metrics-missing"), ("auth_errors", "http-auth-errors"),
                           ("auth_latency", "http-auth-latency"))}}}), encoding="utf-8")
        subprocess.run([sys.executable, str(Path(__file__).with_name("verify.py")), "--chart-bundle", str(bundle)], check=True)


if __name__ == "__main__":
    main()
