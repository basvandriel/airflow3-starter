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

# Kueue is installed in its own namespace (kueue-system) so that its pod
# webhook is not excluded from the Airflow workload namespace.  If Kueue
# were installed in the same namespace as Airflow it would auto-exclude that
# namespace, meaning Airflow task pods would bypass Kueue admission.
AIRFLOW_NAMESPACE=${1:-airflow-dev}
KUEUE_NAMESPACE=${KUEUE_NAMESPACE:-kueue-system}
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

# Ensure Airflow namespace exists.
if ! kubectl get namespace "$AIRFLOW_NAMESPACE" >/dev/null 2>&1; then
  info "Namespace '$AIRFLOW_NAMESPACE' does not exist; creating it."
  kubectl create namespace "$AIRFLOW_NAMESPACE"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
KUEUE_VALUES="${KUEUE_VALUES:-$REPO_DIR/helm/kueue-values.yaml}"

info "Installing Kueue into namespace '$KUEUE_NAMESPACE' (release: $RELEASE_NAME, version: $KUEUE_VERSION)"
info "Kueue will watch the Airflow namespace '$AIRFLOW_NAMESPACE'."
info "Using values file: $KUEUE_VALUES"
helm upgrade --install "$RELEASE_NAME" oci://registry.k8s.io/kueue/charts/kueue \
  --version "$KUEUE_VERSION" \
  --namespace "$KUEUE_NAMESPACE" --create-namespace \
  --values "$KUEUE_VALUES"

kubectl rollout status deployment/kueue-controller-manager -n "$KUEUE_NAMESPACE" --timeout=300s

info "Applying Kueue resources (ClusterQueue + LocalQueue) from helm/kueue-resources.yaml"
info "LocalQueue will be created in namespace '$AIRFLOW_NAMESPACE'"

# Substitute the namespace placeholder (default: airflow-dev) with the actual
# target namespace so the LocalQueue lands in the right place.
sed "s|namespace: \"airflow-dev\"|namespace: \"$AIRFLOW_NAMESPACE\"|g" \
  "$REPO_DIR/helm/kueue-resources.yaml" | kubectl apply -f -

info "Kueue install complete."
info "Pods in '$AIRFLOW_NAMESPACE' annotated with kueue.x-k8s.io/queue-name=$QUEUE_NAME will be queued."
info "The Airflow pod template in helm/pod_template.yaml already adds this annotation (if you are using it)."
