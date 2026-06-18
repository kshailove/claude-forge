# Kubernetes Production Deployment

Deploy engg-intelligence to Kubernetes using the bundled Helm chart.

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| `kubectl` | 1.27+ | https://kubernetes.io/docs/tasks/tools/ |
| `helm` | 3.12+ | https://helm.sh/docs/intro/install/ |
| PostgreSQL 16 | managed (RDS / Cloud SQL) or self-hosted with TimescaleDB | — |
| Redis 7 | managed (ElastiCache) or self-hosted | — |

> The Helm chart does **not** deploy PostgreSQL or Redis. Provision them
> separately and supply connection strings in `custom-values.yaml`.

---

## Step 1 — Create namespace and secrets

```bash
# Create a dedicated namespace
kubectl create namespace engg-intelligence

# Create the application secret
# Replace every REPLACE_ME value before running this.
kubectl create secret generic engg-intelligence-env \
  --namespace engg-intelligence \
  --from-literal=DATABASE_URL="postgresql+asyncpg://engg:YOUR_PASSWORD@your-db-host:5432/engg_intelligence" \
  --from-literal=USE_TIMESCALEDB="false" \
  --from-literal=REDIS_URL="redis://your-redis-host:6379/0" \
  --from-literal=CELERY_BROKER_URL="redis://your-redis-host:6379/0" \
  --from-literal=CELERY_RESULT_BACKEND="redis://your-redis-host:6379/1" \
  --from-literal=JWT_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=DB_ENCRYPTION_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  --from-literal=APP_URL="https://engg-intelligence.yourcompany.com" \
  --from-literal=ENV="production" \
  --from-literal=LOG_LEVEL="INFO" \
  --from-literal=SENDGRID_API_KEY="SG.your-key" \
  --from-literal=SMTP_FROM_ADDRESS="noreply@yourcompany.com"
```

> Alternatively, manage secrets with External Secrets Operator or Vault and
> remove the `secret.yaml` template from the Helm chart.

---

## Step 2 — Prepare custom values

Create `custom-values.yaml` to override image and resource settings:

```yaml
image:
  repository: your-registry/engg-intelligence
  tag: "1.0.0"
  pullPolicy: Always

ingress:
  enabled: true
  className: "nginx"
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
  host: engg-intelligence.yourcompany.com
  tls:
    enabled: true
    secretName: engg-intelligence-tls

# The Helm chart manages the Secret; if you created it manually above,
# set env to empty so the chart does not duplicate it.
env: {}
```

---

## Step 3 — Install the Helm chart

```bash
helm install engg-intelligence ./helm/engg-intelligence \
  --namespace engg-intelligence \
  --values custom-values.yaml \
  --wait \
  --timeout 5m
```

The `--wait` flag blocks until all pods are in the `Running` state or the
timeout is reached.

---

## Step 4 — Verify all pods are running

```bash
kubectl get pods -n engg-intelligence
```

Expected output (all pods in `Running` state):

```
NAME                                              READY   STATUS    RESTARTS   AGE
engg-intelligence-api-xxxx-yyyy                   1/1     Running   0          2m
engg-intelligence-api-xxxx-zzzz                   1/1     Running   0          2m
engg-intelligence-worker-github-xxxx-yyyy         1/1     Running   0          2m
engg-intelligence-worker-github-xxxx-zzzz         1/1     Running   0          2m
engg-intelligence-worker-pm-xxxx-yyyy             1/1     Running   0          2m
engg-intelligence-worker-pm-xxxx-zzzz             1/1     Running   0          2m
engg-intelligence-worker-incidents-xxxx-yyyy      1/1     Running   0          2m
engg-intelligence-worker-slack-xxxx-yyyy          1/1     Running   0          2m
engg-intelligence-worker-keka-xxxx-yyyy           1/1     Running   0          2m
engg-intelligence-worker-digest-xxxx-yyyy         1/1     Running   0          2m
engg-intelligence-beat-xxxx-yyyy                  1/1     Running   0          2m
```

Check logs for the API pod:

```bash
kubectl logs -n engg-intelligence -l app.kubernetes.io/component=api --tail=50
```

---

## Step 5 — Run database migrations

Run Alembic migrations via a one-off Kubernetes Job:

```bash
kubectl run --rm -it engg-migrations \
  --image=your-registry/engg-intelligence:1.0.0 \
  --namespace=engg-intelligence \
  --env-from=secret/engg-intelligence-env \
  --restart=Never \
  --command -- alembic upgrade head
```

Or apply a Job manifest:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: engg-migrations
  namespace: engg-intelligence
spec:
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: migrations
          image: your-registry/engg-intelligence:1.0.0
          command: ["alembic", "upgrade", "head"]
          envFrom:
            - secretRef:
                name: engg-intelligence-env
```

```bash
kubectl apply -f migrations-job.yaml -n engg-intelligence
kubectl wait --for=condition=complete job/engg-migrations -n engg-intelligence --timeout=120s
kubectl delete job/engg-migrations -n engg-intelligence
```

---

## Step 6 — Create admin user

```bash
kubectl exec -n engg-intelligence \
  $(kubectl get pod -n engg-intelligence -l app.kubernetes.io/component=api -o name | head -1) \
  -- python -m app.cli create-admin
```

---

## Step 7 — Configure ingress and TLS

If using cert-manager for automatic TLS:

```bash
# Install cert-manager (if not already installed)
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --set installCRDs=true

# Create a ClusterIssuer for Let's Encrypt
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: platform@yourcompany.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
EOF
```

The Ingress resource created by the Helm chart will automatically request
a certificate once the ClusterIssuer is available.

---

## Upgrading

```bash
# Pull new image and upgrade
helm upgrade engg-intelligence ./helm/engg-intelligence \
  --namespace engg-intelligence \
  --values custom-values.yaml \
  --set image.tag=1.1.0 \
  --wait
```

Always run migrations after upgrading:

```bash
kubectl run --rm -it engg-migrations-v110 \
  --image=your-registry/engg-intelligence:1.1.0 \
  --namespace=engg-intelligence \
  --env-from=secret/engg-intelligence-env \
  --restart=Never \
  --command -- alembic upgrade head
```

---

## Scaling

```bash
# Scale the API horizontally
kubectl scale deployment engg-intelligence-api \
  --replicas=4 -n engg-intelligence

# Or update values.yaml and re-apply:
helm upgrade engg-intelligence ./helm/engg-intelligence \
  --namespace engg-intelligence \
  --values custom-values.yaml \
  --set api.replicaCount=4
```

The HPA will take over once CPU utilisation exceeds the configured threshold.

> **Never scale the Beat deployment beyond 1 replica.** The template
> hardcodes `replicas: 1` to prevent duplicate scheduled task execution.
