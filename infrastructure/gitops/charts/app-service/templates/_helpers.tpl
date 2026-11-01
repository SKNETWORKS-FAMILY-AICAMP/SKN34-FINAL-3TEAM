{{- define "app-service.name" -}}
{{- default .Release.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "app-service.image" -}}
{{- $repository := required "image.repository is required" .repository -}}
{{- if .digest -}}
{{- printf "%s@%s" $repository .digest -}}
{{- else -}}
{{- printf "%s:%s" $repository (required "image.tag or image.digest is required" .tag) -}}
{{- end -}}
{{- end -}}

{{- define "app-service.labels" -}}
app.kubernetes.io/name: {{ include "app-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "app-service.selectorLabels" -}}
app.kubernetes.io/name: {{ include "app-service.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
