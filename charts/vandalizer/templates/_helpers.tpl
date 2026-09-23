{{/*
Expand the name of the chart.
*/}}
{{- define "vandalizer.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name (63 char limit).
*/}}
{{- define "vandalizer.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart name and version for the helm.sh/chart label.
*/}}
{{- define "vandalizer.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels. Usage: include "vandalizer.labels" (dict "ctx" $ "component" "api")
*/}}
{{- define "vandalizer.labels" -}}
helm.sh/chart: {{ include "vandalizer.chart" .ctx }}
{{ include "vandalizer.selectorLabels" . }}
{{- if .ctx.Chart.AppVersion }}
app.kubernetes.io/version: {{ .ctx.Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
app.kubernetes.io/part-of: vandalizer
{{- with .ctx.Values.commonLabels }}
{{ toYaml . }}
{{- end }}
{{- end }}

{{/*
Selector labels. Usage: include "vandalizer.selectorLabels" (dict "ctx" $ "component" "api")
*/}}
{{- define "vandalizer.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vandalizer.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/*
Service account name.
*/}}
{{- define "vandalizer.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "vandalizer.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Image references. Empty tags fall back to the chart appVersion.
*/}}
{{- define "vandalizer.backendImage" -}}
{{- printf "%s:%s" .Values.image.backend.repository (default .Chart.AppVersion .Values.image.backend.tag) }}
{{- end }}

{{- define "vandalizer.frontendImage" -}}
{{- printf "%s:%s" .Values.image.frontend.repository (default .Chart.AppVersion .Values.image.frontend.tag) }}
{{- end }}

{{/*
Datastore endpoints. In-cluster services win when enabled; otherwise the
external endpoint is required — a missing one fails the render loudly rather
than producing a half-configured deployment.
*/}}
{{- define "vandalizer.mongoUri" -}}
{{- if .Values.mongodb.enabled }}
{{- printf "mongodb://%s-mongodb:27017/" (include "vandalizer.fullname" .) }}
{{- else }}
{{- required "mongodb.external.uri is required when mongodb.enabled=false" .Values.mongodb.external.uri }}
{{- end }}
{{- end }}

{{- define "vandalizer.redisHost" -}}
{{- if .Values.redis.enabled }}
{{- printf "%s-redis" (include "vandalizer.fullname" .) }}
{{- else }}
{{- required "redis.external.host is required when redis.enabled=false (hostname only; the app hardcodes port 6379)" .Values.redis.external.host }}
{{- end }}
{{- end }}

{{- define "vandalizer.chromaHost" -}}
{{- if .Values.chromadb.enabled }}
{{- printf "%s-chromadb:8000" (include "vandalizer.fullname" .) }}
{{- else }}
{{- printf "%s:%v" (required "chromadb.external.host is required when chromadb.enabled=false" .Values.chromadb.external.host) .Values.chromadb.external.port }}
{{- end }}
{{- end }}

{{/*
Public URL of the app: explicit config.frontendUrl wins, else derived from
the top-level hostname. One of the two is required.
*/}}
{{- define "vandalizer.frontendUrl" -}}
{{- if .Values.config.frontendUrl }}
{{- .Values.config.frontendUrl }}
{{- else if .Values.hostname }}
{{- printf "https://%s" .Values.hostname }}
{{- else }}
{{- fail "set hostname (or config.frontendUrl) — the public URL users reach the app at" }}
{{- end }}
{{- end }}

{{/*
Hostnames for the HTTPRoute: explicit list wins, else the top-level hostname.
May legitimately be empty (attach to all of the Gateway's hostnames).
*/}}
{{- define "vandalizer.httpRouteHostnames" -}}
{{- if .Values.httpRoute.hostnames }}
{{- toYaml .Values.httpRoute.hostnames }}
{{- else if .Values.hostname }}
{{- toYaml (list .Values.hostname) }}
{{- end }}
{{- end }}

{{/*
Name of the Secret holding backend secrets (chart-managed or user-supplied).
*/}}
{{- define "vandalizer.secretName" -}}
{{- default (printf "%s-backend" (include "vandalizer.fullname" .)) .Values.secrets.existingSecret }}
{{- end }}

{{/*
Name of the uploads PVC (chart-managed or user-supplied).
*/}}
{{- define "vandalizer.uploadsClaimName" -}}
{{- default (printf "%s-uploads" (include "vandalizer.fullname" .)) .Values.uploads.existingClaim }}
{{- end }}

{{/*
storageClassName line for a persistence block (omitted when unset).
Usage: include "vandalizer.storageClass" .Values.uploads
Convention: "" uses the cluster default class, "-" renders storageClassName: ""
(no dynamic provisioning), anything else is used verbatim.
*/}}
{{- define "vandalizer.storageClass" -}}
{{- if .storageClass }}
{{- if eq .storageClass "-" }}
storageClassName: ""
{{- else }}
storageClassName: {{ .storageClass | quote }}
{{- end }}
{{- end }}
{{- end }}

{{/*
envFrom block shared by the api, celery workers, beat, and bootstrap job.
*/}}
{{- define "vandalizer.backendEnvFrom" -}}
envFrom:
  - configMapRef:
      name: {{ include "vandalizer.fullname" . }}-env
  - secretRef:
      name: {{ include "vandalizer.secretName" . }}
{{- end }}

{{/*
Checksum annotations that roll backend pods when config or secrets change.
Skipped for the secret when the user manages it out-of-band.
*/}}
{{- define "vandalizer.backendChecksums" -}}
checksum/config: {{ include (print .Template.BasePath "/configmap-env.yaml") . | sha256sum }}
{{- if not .Values.secrets.existingSecret }}
checksum/secret: {{ include (print .Template.BasePath "/secret.yaml") . | sha256sum }}
{{- end }}
{{- end }}
