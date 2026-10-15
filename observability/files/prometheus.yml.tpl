# Шаблон Helm (tpl) — рендерится в templates/prometheus.yaml; проверяется promtool после helm template.
global:
  scrape_interval: 15s
  scrape_timeout: 4s
  evaluation_interval: {{ .Values.prometheus.evaluationInterval }}
  external_labels:
    stand: {{ .Values.standName }}

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager.{{ .Release.Namespace }}.svc:9093"]

scrape_configs:
  - job_name: prometheus
    static_configs:
      - targets: ["localhost:9090"]

  # Pod приложения обоих слотов; метки slot/version берутся из меток pod.
  - job_name: mts-api
    scrape_interval: {{ .Values.prometheus.appScrapeInterval }}
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names: [{{ .Values.appNamespace }}]
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app_kubernetes_io_name]
        regex: mts-api
        action: keep
      - source_labels: [__meta_kubernetes_pod_container_port_name]
        regex: http
        action: keep
      - source_labels: [__meta_kubernetes_pod_phase]
        regex: Running
        action: keep
      - source_labels: [__meta_kubernetes_pod_label_slot]
        target_label: slot
      - source_labels: [__meta_kubernetes_pod_label_app_kubernetes_io_version]
        target_label: version
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod
      - source_labels: [__meta_kubernetes_namespace]
        target_label: namespace

  # CPU/RAM контейнеров (cAdvisor kubelet) — напрямую с kubelet, права nodes/metrics.
  - job_name: kubelet-cadvisor
    scheme: https
    metrics_path: /metrics/cadvisor
    tls_config:
      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    authorization:
      credentials_file: /var/run/secrets/kubernetes.io/serviceaccount/token
    kubernetes_sd_configs:
      - role: node
    relabel_configs:
      - source_labels: [__meta_kubernetes_node_name]
        target_label: node
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: container_cpu_usage_seconds_total|container_memory_working_set_bytes
        action: keep
      - source_labels: [namespace]
        regex: {{ .Values.appNamespace }}|{{ .Release.Namespace }}|kube-system
        action: keep
      - source_labels: [container]
        regex: ""
        action: drop

  # Синтетическая проба бизнес-метода через ingress-контроллер (пользовательский путь).
  - job_name: blackbox-api
    scrape_interval: 5s
    metrics_path: /probe
    params:
      module: [http_business]
    static_configs:
      - targets: ["{{ .Values.blackbox.target }}"]
        labels:
          probe: tariffs-via-ingress
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox.{{ .Release.Namespace }}.svc:9115

  - job_name: traefik
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names: [kube-system]
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_label_app_kubernetes_io_name]
        regex: traefik
        action: keep
      - source_labels: [__meta_kubernetes_pod_container_port_name]
        regex: metrics
        action: keep
      - source_labels: [__meta_kubernetes_pod_name]
        target_label: pod

  - job_name: alertmanager
    static_configs:
      - targets: ["alertmanager.{{ .Release.Namespace }}.svc:9093"]

  - job_name: grafana
    static_configs:
      - targets: ["grafana.{{ .Release.Namespace }}.svc:3000"]
