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
    parser.add_argument("--baseline", default="b35e381aa37cf22b5816d2750b46d18f2c11fa5c",
                        help="Fetched base commit whose disabled resources must remain unchanged")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[3]
    chart_path = "infrastructure/gitops/charts/observability"
    chart = repo / chart_path
    base = run("git", "-C", str(repo), "rev-parse", "--verify", args.baseline + "^{commit}").strip()
    run("git", "-C", str(repo), "merge-base", "--is-ancestor", base, "HEAD")
    local = repo / "infrastructure/gitops/environments/local/observability.yaml"
    load = lambda text: [doc for doc in yaml.safe_load_all(text) if doc]
    with tempfile.TemporaryDirectory(prefix="issue187-chart-") as directory:
        root = Path(directory)
        baseline = root / "baseline"
        for path in run("git", "-C", str(repo), "ls-tree", "-r", "--name-only", base, chart_path).splitlines():
            target = baseline / Path(path).relative_to(chart_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(run("git", "-C", str(repo), "show", base + ":" + path), encoding="utf-8")
        for extra in ([], ["-f", str(local)]):
            before = load(run(args.helm, "template", "observability", str(baseline), "--namespace", "observability", *extra))
            after = load(run(args.helm, "template", "observability", str(chart), "--namespace", "observability", *extra))
            # Source filenames can reorder resources, so compare by Kubernetes identity.
            identify = lambda docs: {(d["kind"], d["metadata"]["name"]): d for d in docs}
            assert identify(before) == identify(after), "Disabled mode changed existing resources"
        run(args.helm, "lint", str(chart))
        print("PASS Helm default/local disabled resources identical to baseline " + base, flush=True)
        config = dict(environment="verification", datasource_uid="issue187-prometheus", backlog_messages=10, dlq_messages=0,
                      pending_seconds=10, interval_seconds=10, group_wait_seconds=1, group_interval_seconds=10,
                      repeat_interval_seconds=300, secret_name="issue187-test", secret_key="DISCORD_WEBHOOK_URL")
        config_file = root / "config.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")
        output = root / "rendered"
        run(sys.executable, str(Path(__file__).with_name("render.py")), str(config_file), str(output))
        values_file = output / "helm-values.json"
        run(args.helm, "lint", str(chart), "-f", str(values_file))
        rendered = load(run(args.helm, "template", "observability", str(chart), "--namespace", "observability", "-f", str(values_file)))
        by_name = {(d["kind"], d["metadata"]["name"]): d for d in rendered}
        alerting = json.loads(by_name["ConfigMap", "ops187-alerting"]["data"]["alerting.json"])
        datasource = by_name["ConfigMap", "grafana-datasources"]["data"]["prometheus.yaml"]
        assert yaml.safe_load(datasource)["datasources"][0]["uid"] == config["datasource_uid"]
        pod = by_name["Deployment", "grafana"]["spec"]["template"]["spec"]
        container = next(c for c in pod["containers"] if c["name"] == "grafana")
        secret = next(e for e in container["env"] if e["name"] == "OPS_DISCORD_WEBHOOK_URL")["valueFrom"]["secretKeyRef"]
        assert secret == {"name": config["secret_name"], "key": config["secret_key"], "optional": False}
        assert any(v.get("configMap", {}).get("name") == "ops187-alerting" for v in pod["volumes"])
        assert any(v["mountPath"] == "/etc/grafana/provisioning/alerting" for v in container["volumeMounts"])
        print("PASS generated CLI values connect datasource, provisioning mount and required Secret", flush=True)
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
        values = json.loads(values_file.read_text(encoding="utf-8"))
        for key in ("secretName", "secretKey", "provisioning"):
            invalid = json.loads(json.dumps(values))
            invalid["grafana"]["alerting"][key] = {} if key == "provisioning" else ""
            invalid_file = root / "invalid.json"
            invalid_file.write_text(json.dumps(invalid), encoding="utf-8")
            run(args.helm, "template", "observability", str(chart), "-f", str(invalid_file), expect_success=False)
        invalid = json.loads(json.dumps(values))
        invalid["grafana"]["datasourceUid"] = "different-uid"
        invalid_file.write_text(json.dumps(invalid), encoding="utf-8")
        run(args.helm, "template", "observability", str(chart), "-f", str(invalid_file), expect_success=False)
        invalid = json.loads(json.dumps(values))
        invalid["prometheus"]["rabbitmqDlqMetrics"]["enabled"] = False
        invalid_file.write_text(json.dumps(invalid), encoding="utf-8")
        run(args.helm, "template", "observability", str(chart), "-f", str(invalid_file), expect_success=False)
        print("PASS Helm rejects missing Secret/provisioning, mismatched datasource UID and DLQ rule without its scrape", flush=True)
        bundle = root / "bundle.json"
        bundle.write_text(json.dumps({"alerting": alerting, "datasource_text": datasource,
                                      "grafana_container": container, "dlq_job": dlq_job}), encoding="utf-8")
        subprocess.run([sys.executable, str(Path(__file__).with_name("verify.py")), "--chart-bundle", str(bundle)], check=True)


if __name__ == "__main__":
    main()
