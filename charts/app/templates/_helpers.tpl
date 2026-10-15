{{- define "slot.name" -}}mts-api-{{ .Values.slot }}{{- end -}}

{{- define "slot.selectorLabels" -}}
app.kubernetes.io/name: mts-api
slot: {{ .Values.slot }}
{{- end -}}

{{- define "slot.labels" -}}
{{ include "slot.selectorLabels" . }}
app.kubernetes.io/instance: {{ include "slot.name" . }}
app.kubernetes.io/version: {{ .Values.release.version | quote }}
app.kubernetes.io/part-of: mts-devops
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
