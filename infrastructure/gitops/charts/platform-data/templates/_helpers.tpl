{{/* Every active workload must receive explicit environment resource requests and limits. */}}
{{- define "platform-data.resources" -}}
{{- $requests := required "resources.requests must be set in environment values" .requests -}}
{{- $limits := required "resources.limits must be set in environment values" .limits -}}
{{- $_ := required "resources.requests.cpu must be set" $requests.cpu -}}
{{- $_ := required "resources.requests.memory must be set" $requests.memory -}}
{{- $_ := required "resources.limits.cpu must be set" $limits.cpu -}}
{{- $_ := required "resources.limits.memory must be set" $limits.memory -}}
{{- toYaml . -}}
{{- end -}}
