#!/bin/sh
set -eu

: "${RABBITMQ_USER:?RABBITMQ_USER is required}"
: "${RABBITMQ_PASSWORD:?RABBITMQ_PASSWORD is required}"
# Service accounts (architecture 4.5): fixed names, passwords from env only.
for name in CORE LEARNING AI SCORING REPORT; do
  eval "password=\${RABBITMQ_${name}_PASSWORD:-}"
  # Passwords go into AMQP URLs and JSON bodies, so only URL-safe literals are accepted.
  case "$password" in ''|*[!A-Za-z0-9_-]*) echo "RABBITMQ_${name}_PASSWORD is missing or not [A-Za-z0-9_-]" >&2; exit 1 ;; esac
done
case "$RABBITMQ_USER" in core|learning|ai|scoring|report) echo 'RABBITMQ_USER must differ from service account names' >&2; exit 1 ;; esac
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

# Least-privilege service accounts. Apps never declare topology except ai/scoring per-pod exclusive
# queues: aio_pika robust channels name them amq_<uuid hex> (amq.gen-* if the server names them).
# Retries go through each service's own retry exchange, so no account can write to the default
# exchange. Regexes use [.] for a literal dot so they need no JSON escaping.
put_json() {
  request --fail --output /dev/null --request PUT --header 'Content-Type: application/json' \
    --data-binary "$2" "$endpoint/api/$1"
}
service_user() {
  name=$1 password=$2 tags=$3
  umask 077
  printf '{"password":"%s","tags":"%s"}' "$password" "$tags" > /tmp/rabbitmq-user.json
  put_json "users/$name" @/tmp/rabbitmq-user.json
  rm -f /tmp/rabbitmq-user.json
  put_json "permissions/%2F/$name" "{\"configure\":\"$4\",\"write\":\"$5\",\"read\":\"$6\"}"
  # Routing keys this account may publish to events.topic; the broker refuses the rest.
  put_json "topic-permissions/%2F/$name" "{\"exchange\":\"events.topic\",\"write\":\"$7\",\"read\":\".*\"}"
}
none='^$'
service_user core "$RABBITMQ_CORE_PASSWORD" monitoring "$none" \
  '^(cmd[.]direct|events[.]topic|core[.]retry)$' \
  '^core[.](report[.]events|llm[.]usage[.]recorded|event[.]audit|model[.]loading[.]reported)$' \
  '^(student[.]deleted|model[.]version[.]activated)$'
service_user learning "$RABBITMQ_LEARNING_PASSWORD" '' "$none" \
  '^learning[.]retry$' '^learning[.]student[.]deleted$' "$none"
service_user ai "$RABBITMQ_AI_PASSWORD" '' '^amq(_[0-9a-f]{32}|[.]gen-.*)$' \
  '^(events[.]topic|amq_[0-9a-f]{32}|amq[.]gen-.*)$' '^(events[.]topic|amq_[0-9a-f]{32}|amq[.]gen-.*)$' '^llm[.]usage[.]recorded$'
service_user scoring "$RABBITMQ_SCORING_PASSWORD" '' '^amq(_[0-9a-f]{32}|[.]gen-.*)$' \
  '^(events[.]topic|amq_[0-9a-f]{32}|amq[.]gen-.*)$' '^(events[.]topic|amq_[0-9a-f]{32}|amq[.]gen-.*)$' \
  '^(llm[.]usage[.]recorded|model[.]loading[.]reported)$'
service_user report "$RABBITMQ_REPORT_PASSWORD" '' "$none" \
  '^(events[.]topic|report[.]retry)$' '^report[.](report[.]generate|student[.]deleted)$' \
  '^report[.](started|completed|failed)$'
echo 'RabbitMQ service accounts applied'
