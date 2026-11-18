{{/* Tempo config; the Deployment checksums it so a config change rolls the Pod. */}}
{{- define "observability.tempoConfig" -}}
server:
  http_listen_port: 3200
distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
# #784: smaller, shorter head blocks keep "completing block" memory under the limit.
ingester:
  max_block_bytes: {{ int .Values.tempo.ingester.maxBlockBytes }}
  max_block_duration: {{ .Values.tempo.ingester.maxBlockDuration }}
  trace_idle_period: {{ .Values.tempo.ingester.traceIdlePeriod }}
storage:
  trace:
    backend: local
    wal:
      path: /var/tempo/wal
    local:
      path: /var/tempo/blocks
compactor:
  compaction:
    block_retention: {{ .Values.tempo.retention }}
# Bounded intake: over the rate Tempo refuses spans, and the Collector drops them after its capped retry.
overrides:
  defaults:
    ingestion:
      rate_limit_bytes: {{ int .Values.tempo.limits.rateLimitBytes }}
      burst_size_bytes: {{ int .Values.tempo.limits.burstSizeBytes }}
      max_traces_per_user: {{ int .Values.tempo.limits.maxLiveTraces }}
    global:
      max_bytes_per_trace: {{ int .Values.tempo.limits.maxBytesPerTrace }}
usage_report:
  reporting_enabled: false
{{- end }}
