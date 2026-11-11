#!/bin/sh
set -eu

: "${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
: "${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
endpoint="${MINIO_ENDPOINT:-http://minio:9000}"
wait_seconds="${WAIT_TIMEOUT_SECONDS:-120}"
case "$wait_seconds" in ''|*[!0-9]*) echo 'Invalid wait timeout' >&2; exit 1 ;; esac
[ "$wait_seconds" -gt 0 ] || exit 1
[ "$#" -gt 0 ] || { echo 'At least one bucket is required' >&2; exit 1; }

deadline=$(( $(date +%s) + wait_seconds ))
until curl --fail --silent --show-error --connect-timeout 3 --max-time 5 \
  --output /dev/null "$endpoint/minio/health/ready"; do
  [ "$(date +%s)" -lt "$deadline" ] || { echo 'MinIO readiness timed out' >&2; exit 1; }
  sleep 2
done

# Quote curl config values; .env preparation rejects embedded newlines.
credentials=$(printf '%s:%s' "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" | sed 's/\\/\\\\/g; s/"/\\"/g')
for bucket in "$@"; do
  case "$bucket" in ''|*[!a-z0-9-]*) echo 'Invalid bucket name' >&2; exit 1 ;; esac
  status=$(printf 'user = "%s"\n' "$credentials" |
    curl --config - --aws-sigv4 'aws:amz:us-east-1:s3' --silent --show-error \
      --connect-timeout 3 --max-time 15 --request PUT --data '' \
      --output /tmp/minio-bucket.xml --write-out '%{http_code}' "$endpoint/$bucket")
  case "$status" in
    200|204) ;;
    409)
      grep -q '<Code>BucketAlreadyOwnedByYou</Code>' /tmp/minio-bucket.xml || {
        echo 'MinIO bucket conflict' >&2; exit 1;
      }
      ;;
    *) echo "MinIO bucket creation failed: HTTP $status" >&2; exit 1 ;;
  esac
  echo "MinIO bucket ready: $bucket"
done

# Optional placeholder objects for local stand-ins (#509), as space-separated "bucket/key".
# An existing object is never overwritten.
set -f
for object in ${MINIO_PLACEHOLDER_OBJECTS:-}; do
  bucket=${object%%/*}
  key=${object#*/}
  case "$bucket" in ''|*[!a-z0-9-]*) echo 'Invalid placeholder bucket' >&2; exit 1 ;; esac
  case "$key" in
    "$object"|''|/*|*/|*//*|*..*|*[!A-Za-z0-9._/-]*) echo 'Invalid placeholder key' >&2; exit 1 ;;
  esac
  status=$(printf 'user = "%s"\n' "$credentials" |
    curl --config - --aws-sigv4 'aws:amz:us-east-1:s3' --silent --show-error \
      --connect-timeout 3 --max-time 15 --head \
      --output /dev/null --write-out '%{http_code}' "$endpoint/$bucket/$key")
  case "$status" in
    200) echo "MinIO placeholder exists: $object"; continue ;;
    404) ;;
    *) echo "MinIO placeholder check failed: HTTP $status" >&2; exit 1 ;;
  esac
  status=$(printf 'user = "%s"\n' "$credentials" |
    curl --config - --aws-sigv4 'aws:amz:us-east-1:s3' --silent --show-error \
      --connect-timeout 3 --max-time 15 --request PUT \
      --data-binary 'sagomungchi local placeholder object (#509)' \
      --output /tmp/minio-object.xml --write-out '%{http_code}' "$endpoint/$bucket/$key")
  case "$status" in
    200) echo "MinIO placeholder created: $object" ;;
    *) echo "MinIO placeholder creation failed: HTTP $status" >&2; exit 1 ;;
  esac
done
