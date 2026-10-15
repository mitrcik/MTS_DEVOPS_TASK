{{- define "obs.podSecurity" -}}
runAsNonRoot: true
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "obs.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
privileged: false
capabilities:
  drop: ["ALL"]
{{- end -}}

{{- define "obs.labels" -}}
app.kubernetes.io/name: {{ .name }}
app.kubernetes.io/part-of: mts-devops
app.kubernetes.io/component: observability
{{- end -}}

{{- define "obs.ingress" -}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ .name }}
  labels:
    {{- include "obs.labels" . | nindent 4 }}
spec:
  ingressClassName: traefik
  rules:
    - host: {{ .host }}
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ .name }}
                port:
                  number: {{ .port }}
{{- end -}}
