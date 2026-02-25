#!/usr/bin/env bash
# Reproduces the GitHub Actions CI pipeline locally using kind.
# Usage:
#   ./scripts/ci-local.sh          # full run
#   ./scripts/ci-local.sh clean    # destroy the cluster and exit

set -euo pipefail

CLUSTER=airflow-ci-local
NAMESPACE=airflow-ci
CHART_NAME=ci-airflow
IMAGE=airflow3-starter:ci

# ── Helpers ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[ci-local]${NC} $*"; }
warn()  { echo -e "${YELLOW}[ci-local]${NC} $*"; }
die()   { echo -e "${RED}[ci-local] ERROR${NC} $*" >&2; exit 1; }

# ── Clean-up ──────────────────────────────────────────────────────────────────
cleanup() {
  warn "Destroying kind cluster '$CLUSTER'..."
  kind delete cluster --name "$CLUSTER" 2>/dev/null || true
}

if [[ "${1:-}" == "clean" ]]; then
  cleanup
  exit 0
fi

trap 'echo ""; warn "Caught signal – cleaning up..."; cleanup' INT TERM

# ── 1. Build image ─────────────────────────────────────────────────────────────
info "Building Docker image $IMAGE..."
docker build --tag "$IMAGE" .

# ── 2. Create kind cluster ─────────────────────────────────────────────────────
if kind get clusters 2>/dev/null | grep -q "^${CLUSTER}$"; then
  warn "Cluster '$CLUSTER' already exists – reusing it."
else
  info "Creating kind cluster '$CLUSTER'..."
  kind create cluster --name "$CLUSTER"
fi

# Point kubectl at the new cluster
kubectl config use-context "kind-${CLUSTER}"

# ── 3. Load custom image into kind ────────────────────────────────────────────
info "Loading $IMAGE into kind..."
kind load docker-image "$IMAGE" --name "$CLUSTER"

# ── 4. Helm deploy ────────────────────────────────────────────────────────────
info "Adding Airflow Helm repo..."
helm repo add apache-airflow https://airflow.apache.org 2>/dev/null || true
helm repo update

info "Deploying Airflow via Helm (this takes a few minutes)..."
# NOTE: --wait is intentionally omitted.  Helm's --wait blocks until all pods
# are Ready *before* running post-install hooks.  The migration job is a
# post-install hook, so --wait creates a deadlock: pods need migrations to
# become Ready, but migrations only run after pods are Ready.  Instead we
# let helm finish immediately, then poll for readiness ourselves.
helm upgrade --install "$CHART_NAME" apache-airflow/airflow \
  --namespace "$NAMESPACE" --create-namespace \
  --values helm/values.prod.yaml \
  --values helm/values.ci.yaml \
  --set defaultAirflowRepository=airflow3-starter \
  --set defaultAirflowTag=ci \
  --timeout 10m

info "Waiting for migration job to complete..."
kubectl wait job/"${CHART_NAME}-run-airflow-migrations" \
  -n "$NAMESPACE" --for=condition=complete --timeout=5m 2>/dev/null || \
kubectl wait job/"${CHART_NAME}-run-airflow-migrations" \
  -n "$NAMESPACE" --for=condition=failed --timeout=5m 2>/dev/null || true

info "Waiting for all Airflow pods to become ready (up to 5m)..."
kubectl wait pods -n "$NAMESPACE" \
  -l "release=${CHART_NAME}" \
  --for=condition=Ready --timeout=5m || true

# ── 5. Quick sanity check ─────────────────────────────────────────────────────
info "Pod status:"
kubectl get pods -n "$NAMESPACE" -o wide

info "Done! Cluster is still running. To explore:"
echo "  kubectl get pods -n $NAMESPACE"
echo "  kubectl logs -n $NAMESPACE -l component=api-server --all-containers"
echo "  kubectl describe pod -n $NAMESPACE -l component=api-server"
echo ""
echo "  To tear down: ./scripts/ci-local.sh clean"
