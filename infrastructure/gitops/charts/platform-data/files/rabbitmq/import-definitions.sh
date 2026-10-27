#!/bin/sh
set -eu

: "${RABBITMQ_USER:?RABBITMQ_USER is required}"
: "${RABBITMQ_PASSWORD:?RABBITMQ_PASSWORD is required}"
endpoint="${RABBITMQ_MANAGEMENT_URL:-http://rabbitmq:15672}"
definitions="${DEFINITIONS_FILE:-/definitions/definitions.json}"
wait_seconds="${WAIT_TIMEOUT_SECONDS:-120}"
case "$wait_seconds" in ''|*[!0-9]*) echo 'Invalid wait timeout' >&2; exit 1 ;; esac
[ "$wait_seconds" -gt 0 ] || exit 1
[ -r "$definitions" ] || { echo 'Definitions file is not readable' >&2; exit 1; }

# Send credentials through stdin rather than curl's command line or logs.
authorization=$(printf '%s:%s' "$RABBITMQ_USER" "$RABBITMQ_PASSWORD" | base64 | tr -d '\n')
request() {
  printf 'header = "Authorization: Basic %s"\n' "$authorization" |
    curl --config - --silent --show-error --connect-timeout 3 --max-time 10 "$@"
}

deadline=$(( $(date +%s) + wait_seconds ))
while :; do
  if status=$(request --output /tmp/rabbitmq-readiness.json --write-out '%{http_code}' "$endpoint/api/overview"); then
    case "$status" in
      200) break ;;
      401|403) echo 'RabbitMQ initialization authentication failed' >&2; exit 1 ;;
    esac
  fi
  [ "$(date +%s)" -lt "$deadline" ] || { echo 'RabbitMQ readiness timed out' >&2; exit 1; }
  sleep 2
done

request --fail --output /tmp/rabbitmq-import.json --request POST \
  --header 'Content-Type: application/json' --data-binary "@$definitions" \
  "$endpoint/api/definitions"
echo 'RabbitMQ definitions imported'
