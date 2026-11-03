"""Render opt-in Grafana file provisioning; no deployment or secret access."""
import argparse
import json
from pathlib import Path
import re

# Must match the opt-in scrape job in the observability chart's prometheus-config.
DLQ_JOB = "rabbitmq-dlq"


def build(config):
    required = {"environment", "datasource_uid", "backlog_messages", "dlq_messages", "pending_seconds",
                "interval_seconds", "group_wait_seconds", "group_interval_seconds",
                "repeat_interval_seconds", "secret_name", "secret_key"}
    if set(config) != required:
        raise ValueError("configuration must contain exactly: " + ", ".join(sorted(required)))
    for key in required - {"environment", "datasource_uid", "secret_name", "secret_key", "dlq_messages"}:
        if type(config[key]) is not int or config[key] <= 0:
            raise ValueError(key + " must be a positive integer")
    # 0 is a valid explicit choice: any dead-lettered message fires.
    if type(config["dlq_messages"]) is not int or config["dlq_messages"] < 0:
        raise ValueError("dlq_messages must be a non-negative integer")
    for key in ("environment", "datasource_uid", "secret_name", "secret_key"):
        if not isinstance(config[key], str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+", config[key]):
            raise ValueError(key + " must be a nonempty identifier (never a secret value)")
    if len(config["datasource_uid"]) > 40:
        raise ValueError("datasource_uid exceeds 40 characters")
    if config["repeat_interval_seconds"] % config["group_interval_seconds"]:
        raise ValueError("repeat interval must be a multiple of group interval")
    if config["interval_seconds"] % 10:
        raise ValueError("evaluation interval must be a multiple of Grafana's 10-second base interval")
    uid = config["datasource_uid"]
    rules = []
    scrape = "Infrastructure signal only; inspect scrape health before application diagnosis."
    specifications = [
        ("rabbitmq-down", "RabbitMQ scrape unavailable", "rabbitmq",
         '(1 - up{job="rabbitmq"}) or absent(up{job="rabbitmq"})', 0, scrape),
        ("collector-down", "Collector scrape unavailable", "observability",
         '(1 - up{job="otel-collector"}) or absent(up{job="otel-collector"})', 0, scrape),
        ("rabbitmq-backlog", "RabbitMQ aggregate ready backlog", "rabbitmq",
         'sum(rabbitmq_queue_messages_ready{job="rabbitmq"})', config["backlog_messages"], scrape),
        # One alert instance per <queue>.dlq; max avoids double counting if a queue is reported twice.
        ("rabbitmq-dlq", "RabbitMQ dead letter queue depth", "rabbitmq",
         'max by (vhost, queue) (rabbitmq_detailed_queue_messages{job="' + DLQ_JOB + '"})',
         config["dlq_messages"],
         "Dead-lettered messages wait for manual inspection or reprocessing; check the queue label."),
    ]
    for suffix, title, service, query, threshold, description in specifications:
        rules.append({
            "uid": "ops187-" + suffix, "title": title, "condition": "C",
            "for": f'{config["pending_seconds"]}s',
            "noDataState": "NoData", "execErrState": "Error",
            "labels": {"service": service, "environment": config["environment"],
                       "severity": "warning", "scope": "infra", "issue": "187"},
            "annotations": {"summary": title, "description": description},
            "notification_settings": {
                "receiver": "ops187-discord",
                "group_by": ["grafana_folder", "alertname", "service", "environment"],
                "group_wait": f'{config["group_wait_seconds"]}s',
                "group_interval": f'{config["group_interval_seconds"]}s',
                "repeat_interval": f'{config["repeat_interval_seconds"]}s'},
            "data": [
                {"refId": "A", "datasourceUid": uid, "relativeTimeRange": {"from": 300, "to": 0},
                 "model": {"refId": "A", "expr": query, "instant": True, "range": False,
                           "datasource": {"type": "prometheus", "uid": uid},
                           "intervalMs": 15000, "maxDataPoints": 43200}},
                {"refId": "C", "datasourceUid": "__expr__", "relativeTimeRange": {"from": 0, "to": 0},
                 "model": {"refId": "C", "type": "threshold", "expression": "A",
                           "conditions": [{"type": "query", "query": {"params": ["C"]},
                                           "reducer": {"type": "last", "params": []},
                                           "evaluator": {"type": "gt", "params": [threshold]},
                                           "operator": {"type": "and"}}]}}
            ]})
    provisioning = {
        "apiVersion": 1,
        "groups": [{"orgId": 1, "name": "ops187-infrastructure", "folder": "Operational alerts",
                    "interval": f'{config["interval_seconds"]}s', "rules": rules}],
        "contactPoints": [{"orgId": 1, "name": "ops187-discord", "receivers": [{
            "uid": "ops187-discord", "type": "discord", "disableResolveMessage": False,
            "settings": {"url": "$OPS_DISCORD_WEBHOOK_URL", "use_discord_username": True}}]}]}
    patch = {"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {
        "name": "grafana", "namespace": "observability"}, "spec": {"template": {"spec": {
            "containers": [{"name": "grafana", "env": [{"name": "OPS_DISCORD_WEBHOOK_URL",
                "valueFrom": {"secretKeyRef": {"name": config["secret_name"],
                    "key": config["secret_key"], "optional": False}}}],
                "command": ["/bin/sh", "-ec"],
                "args": ['test -n "$OPS_DISCORD_WEBHOOK_URL" || { echo "OPS Discord Secret value is required" >&2; exit 1; }; exec /run.sh'],
                "volumeMounts": [{"name": "ops187-alerting", "mountPath": "/etc/grafana/provisioning/alerting",
                                  "readOnly": True}]}],
            "volumes": [{"name": "ops187-alerting", "configMap": {"name": "ops187-alerting"}}]}}}}
    return provisioning, patch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        provisioning, patch = build(config)
    except (ValueError, OSError):
        parser.exit(2, "Invalid configuration: check required identifiers and positive integer settings.\n")
    args.output.mkdir(parents=True, exist_ok=False)
    for name, value in (("alerting.json", provisioning), ("deployment-patch.json", patch),
                        ("helm-values.json", {"prometheus": {"rabbitmqDlqMetrics": {"enabled": True}},
                                              "grafana": {"datasourceUid": config["datasource_uid"],
                            "alerting": {"enabled": True,
                                "secretName": config["secret_name"],
                                "secretKey": config["secret_key"],
                                "provisioning": provisioning}}}),
                        ("configmap.json", {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {
                            "name": "ops187-alerting", "namespace": "observability"},
                            "data": {"alerting.json": json.dumps(provisioning)}})):
        (args.output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
