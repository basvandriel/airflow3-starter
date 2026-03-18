#!/usr/bin/env bash
# Install the Kueue Helm chart into the KUEUE_NAMESPACE (default: kueue-system).
# This script only installs Kueue; ClusterQueue/LocalQueue resources are applied
# separately (for example via scripts/apply_kueue_resources.sh).
#
# Usage:
#   ./scripts/install_kueue.sh
#
# Example (override namespace):
#   KUEUE_NAMESPACE=airflow-dev ./scripts/install_kueue.sh

set -euo pipefail

# Kueue is installed in its own namespace (kueue-system) so that its pod
# webhook is not excluded from the Airflow workload namespace.  If Kueue
# were installed in the same namespace as Airflow it would auto-exclude that
# namespace, meaning Airflow task pods would bypass Kueue admission.
KUEUE_NAMESPACE=${KUEUE_NAMESPACE:-kueue-system}
RELEASE_NAME=${RELEASE_NAME:-kueue}
KUEUE_VERSION=${KUEUE_VERSION:-0.16.2}

info()  { echo "[install_kueue] $*"; }
warn()  { echo "[install_kueue] WARNING: $*" >&2; }
error() { echo "[install_kueue] ERROR: $*" >&2; exit 1; }

# Require tooling.
for cmd in kubectl helm; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    error "'$cmd' is required but was not found on PATH."
  fi
done


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
KUEUE_VALUES="${KUEUE_VALUES:-$REPO_DIR/helm/kueue-values.yaml}"

info "Installing Kueue into namespace '$KUEUE_NAMESPACE' (release: $RELEASE_NAME, version: $KUEUE_VERSION)"
info "Using values file: $KUEUE_VALUES"
helm upgrade --install "$RELEASE_NAME" oci://registry.k8s.io/kueue/charts/kueue \
  --version "$KUEUE_VERSION" \
  --namespace "$KUEUE_NAMESPACE" --create-namespace \
  --values "$KUEUE_VALUES"

kubectl rollout status deployment/kueue-controller-manager -n "$KUEUE_NAMESPACE" --timeout=300s

info "Kueue install complete."
info "Pods labeled with kueue.x-k8s.io/queue-name=<queue> will be queued by Kueue."
info "The Airflow pod template in helm/pod_template.yaml already adds this label (if you are using it)."
