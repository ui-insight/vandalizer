# Vandalizer Helm chart

Deploys the Vandalizer document-intelligence platform on Kubernetes: the
FastAPI backend (`api`), Celery workers (one Deployment per queue) plus a
beat scheduler, the React frontend behind nginx, and — by default —
single-replica MongoDB, Redis, and ChromaDB, each replaceable with an
external endpoint.

The chart targets vanilla Kubernetes ≥1.25 and is written to stay viable on
OpenShift (values-driven securityContexts, no numeric UIDs in templates, a
non-root frontend image by default).

## Requirements

- **A ReadWriteMany-capable storage class** for the uploads volume on
  multi-node clusters (Ceph NFS, CephFS, EFS, Azure Files, …). The api and
  celery pods share one filesystem for uploaded documents; that is a hard
  application requirement today (its S3 backend is not yet complete). On a
  single-node cluster `ReadWriteOnce` works. Set `uploads.storageClass` /
  `uploads.accessModes`, or bring your own claim via `uploads.existingClaim`.
- Secrets: a JWT signing key and a Fernet `CONFIG_ENCRYPTION_KEY` (generate
  with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).
  **Back up the encryption key** — it encrypts LLM/OAuth credentials stored
  in MongoDB, and losing it makes them permanently undecryptable.
- An edge: either an Ingress controller (`ingress.enabled=true`) or a Gateway
  API implementation (`httpRoute.enabled=true`). With neither, use a
  port-forward (printed in the install notes).

## Quickstart

The chart's default image tag is its `appVersion`. Until that release is
published (the unprivileged frontend image first ships with it), pin
`image.backend.tag` / `image.frontend.tag` to a published release.

```bash
helm install vandalizer charts/vandalizer \
  --namespace vandalizer --create-namespace \
  --set hostname=vandalizer.example.edu \
  --set secrets.jwtSecretKey="$(openssl rand -hex 32)" \
  --set secrets.configEncryptionKey="$FERNET_KEY" \
  --set bootstrap.adminEmail=admin@example.edu \
  --set bootstrap.adminPassword="$ADMIN_PASSWORD" \
  --set httpRoute.enabled=true \
  --set httpRoute.parentRefs[0].name=my-gateway \
  --set httpRoute.parentRefs[0].namespace=gateways
```

`hostname` is stated once and derives `config.frontendUrl`
(`https://<hostname>`), `httpRoute.hostnames`, and `ingress.host`; set any of
those explicitly to override (e.g. a plain-http `frontendUrl` on an intranet).

For real installs prefer a values file, and prefer `secrets.existingSecret`
(a Secret whose keys are the environment-variable names: `JWT_SECRET_KEY`,
`CONFIG_ENCRYPTION_KEY`, optionally `SMTP_PASSWORD`, `SENTRY_DSN`,
`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`,
`GRAPH_TOKEN_KEY`, `GRAPH_CLIENT_STATE_SECRET`, `RESEND_API_KEY`) over
plaintext values.

## Routing

Default topology: **all traffic goes to the frontend Service**, whose nginx
proxies `/api/` to the api Service. That nginx config carries behaviors the
app depends on — SSE streaming (`proxy_buffering off`, generous read
timeout), a 200M upload body limit, the legacy `/login/azure/authorized`
OAuth callback, and the SPA fallback — so routing through it means those work
identically on every Ingress controller and Gateway implementation.

- `ingress.enabled` renders a `networking.k8s.io/v1` Ingress
  (`className`, `host`, `tls`, `annotations`).
- `httpRoute.enabled` renders a `gateway.networking.k8s.io/v1` HTTPRoute;
  set `parentRefs` to your Gateway and `hostnames`. The route's request
  timeout defaults to `0s` (disabled) because SSE streams outlive most
  Gateway defaults; set `httpRoute.timeouts.request` to a duration if your
  implementation rejects `0s`.

To route `/api` at the edge instead (bypassing the frontend nginx for API
traffic), see `values-split-routing.yaml` — you then own timeouts and
request-body limits at the Gateway.

## Datastores

`mongodb`, `redis`, and `chromadb` each render a minimal, pinned,
single-replica Deployment with optional persistence. For managed or shared
servers, disable the in-cluster one and point at yours:

```yaml
mongodb:
  enabled: false
  external:
    uri: mongodb://user:pass@mongo.example.edu:27017/
redis:
  enabled: false
  external:
    host: redis.example.edu     # hostname only — the app hardcodes port 6379, no auth/TLS
chromadb:
  enabled: false
  external:
    host: chroma.example.edu    # CHROMADB_HOST is host:port, not a URL
    port: 8000
```

Caveats that come from the application, not the chart:

- Redis must answer **unauthenticated on port 6379** (broker URLs and clients
  are hardcoded). The chart's NetworkPolicy compensates in-cluster.
- ChromaDB has **no authentication**; keep the ChromaDB server pinned to a
  v1-API release (0.x) — the backend's client is chromadb 0.5.x and Chroma
  ≥1.0 servers are v2-only.
- Keep `helm.sh/resource-policy: keep` on the Mongo/Chroma/uploads PVCs
  (the default) unless you want `helm uninstall` to be able to take your data
  with it.

## Storage classes

Every persistence block (`uploads`, `mongodb.persistence`,
`redis.persistence`, `chromadb.persistence`) has the same four knobs:
`existingClaim`, `storageClass` (`""` = cluster default, `"-"` = none),
`accessModes`, `size`. Nothing in the chart assumes a particular provisioner.

## OpenShift

The application pods comply with the restricted Pod Security Standard on
vanilla Kubernetes. The bundled ChromaDB runs as root, so a namespace that
*enforces* `restricted` rejects it — use an external ChromaDB there. On OpenShift, drop the fsGroup/runAsUser pinning and let the SCC
assign UIDs:

```yaml
api:
  podSecurityContext:
    runAsUser: null
    runAsGroup: null
    fsGroup: null
celery:
  podSecurityContext:
    runAsUser: null
    runAsGroup: null
    fsGroup: null
mongodb:
  podSecurityContext:
    runAsUser: null
    runAsGroup: null
    fsGroup: null
redis:
  podSecurityContext:
    runAsUser: null
    runAsGroup: null
    fsGroup: null
chromadb:
  podSecurityContext:
    runAsUser: null
    runAsGroup: null
    fsGroup: null
```

Note: some NFS-backed storage classes ignore `fsGroup` entirely; if uploads
land unwritable, fix ownership on the export (or via the provisioner's
options) rather than in the chart.

## Frontend image variants

The chart defaults to `vandalizer-frontend-unprivileged` (non-root nginx,
port 8080). The root-nginx port-80 image compose users run is also published;
`values-frontend-root.yaml` shows the three values that must change together
to use it.

## Bootstrap

`bootstrap.enabled` (default true) runs `bootstrap_install.py` as a
**post-install** hook Job: creates the admin user, optional default team and
org name, and seeds the workflow catalog. It never runs on upgrades because
re-running it resets the admin password. Credentials come from
`bootstrap.adminEmail`/`adminPassword` or `bootstrap.existingSecret` (keys
`ADMIN_EMAIL`, `ADMIN_PASSWORD`, optionally `ADMIN_NAME`,
`DEFAULT_TEAM_NAME`, `ORG_NAME`). The Secret the chart creates from
`adminPassword` is a hook resource Helm never deletes, not even on
uninstall — delete it after the first install, or prefer `existingSecret`.

## Scaling notes

- `api.replicaCount` / `api.hpa` scale the API; streaming (SSE) responses are
  served in-process per request, which is replica-safe, but multi-replica
  API has had less soak time than single-replica.
- Scale workers per queue: `celery.queues.<name>.replicas`. Queue-depth-based
  autoscaling (KEDA) is future work.
- Never scale `beat` — it is pinned to 1 replica by the chart.
- Celery pods get `terminationGracePeriodSeconds: 3720` so in-flight tasks
  (up to the app's 3660s task time limit) survive rollouts.

## Uninstall behavior

Two things `helm uninstall` does on purpose that can surprise:

- **Celery worker pods take up to 62 minutes to terminate.** They carry
  `terminationGracePeriodSeconds: 3720` so in-flight tasks survive normal
  rollouts; on uninstall the broker is deleted in the same breath, the
  workers' warm shutdown hangs on the vanished broker, and the kubelet only
  SIGKILLs them at the deadline. Safe to skip the wait:
  `kubectl delete pod --all -n <ns> --grace-period=0 --force`.
- **The uploads, MongoDB, and ChromaDB PVCs are kept** (they carry
  `helm.sh/resource-policy: keep`) so an uninstall can never take your data
  with it. Reinstalling under the same release name re-adopts them.
  `kubectl delete pvc ...` explicitly when you truly want the data gone —
  and note that with a `Retain`-policy storage class the released PV still
  survives that, for a cluster admin to clean up.

## Known limitations (upstream application work, not chart work)

- Uploads require a shared filesystem (RWX) — the S3 storage backend exists
  behind `STORAGE_BACKEND=s3` but is incomplete and its dependency isn't in
  the shipped image; do not enable it.
- Redis/ChromaDB/Mongo connections support no auth/TLS beyond what a Mongo
  URI carries; the NetworkPolicy is the compensating control. **Your CNI must
  enforce NetworkPolicy** (Calico, Cilium, most managed CNIs — not plain
  flannel): where it is ignored, any pod in the cluster can read the in-cluster
  MongoDB, including users and the encrypted LLM credentials. Otherwise point
  the chart at external datastores with credentials in the Mongo URI.
- `/api/metrics` (Prometheus) is unauthenticated. The chart's frontend nginx
  answers it with a 404, so it is not reachable through the default edge; with
  split routing (ingress straight to the api Service) block it at the ingress
  yourself. Anything in-cluster that can reach the api Service can scrape it.
