#!/usr/bin/env bash
# Install Kueue into the same namespace as the Airflow deployment and create a
# minimal ClusterQueue + LocalQueue for Airflow's KubernetesExecutor pods.
#
# Usage:
#   ./scripts/install_kueue.sh [namespace]
#
# Example:
#   ./scripts/install_kueue.sh airflow-dev

set -euo pipefail

NAMESPACE=${1:-airflow-dev}
RELEASE_NAME=${RELEASE_NAME:-kueue}
KUEUE_VERSION=${KUEUE_VERSION:-0.16.2}
QUEUE_NAME=${QUEUE_NAME:-airflow}
CLUSTER_QUEUE_NAME=${CLUSTER_QUEUE_NAME:-airflow-cluster-queue}
FLAVOR_NAME=${FLAVOR_NAME:-default-flavor}

info()  { echo "[install_kueue] $*"; }
warn()  { echo "[install_kueue] WARNING: $*" >&2; }
error() { echo "[install_kueue] ERROR: $*" >&2; exit 1; }

# Require tooling.
for cmd in kubectl helm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "'$cmd' is required but was not found on PATH."
  fi
done

# Ensure namespace exists (helm --create-namespace is convenient, but it may
# be confusing if the user has a misconfigured kubeconfig / context).
if ! kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then
  info "Namespace '$NAMESPACE' does not exist; creating it."
  kubectl create namespace "$NAMESPACE"
fi

info "Installing Kueue into namespace '$NAMESPACE' (release: $RELEASE_NAME, version: $KUEUE_VERSION)"
helm upgrade --install "$RELEASE_NAME" oci://registry.k8s.io/kueue/charts/kueue \
  --version "$KUEUE_VERSION" \
  --namespace "$NAMESPACE" --create-namespace \
  --wait --timeout 300s

info "Applying Kueue resources (ClusterQueue + LocalQueue) from helm/kueue-resources.yaml"

kubectl apply -f "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/helm/kueue-resources.yaml"

info "Kueue install complete. Pods must be annotated with kueue.x-k8s.io/queue-name=$QUEUE_NAME to use this queue."
info "The Airflow pod template in helm/pod_template.yaml already adds this annotation (if you are using it)."
