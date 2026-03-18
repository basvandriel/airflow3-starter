#!/usr/bin/env bash
# Port-forward the Airflow API service (or pod) to localhost:8080.
#
# This script finds the first pod that looks like an Airflow API server and
# forwards local port 8080 to the pod's port 8080.
#
# Usage:
#   ./scripts/port_forward_api.sh [namespace]
#
# If no namespace is provided, it defaults to "airflow-dev".

set -euo pipefail

NAMESPACE=${1:-airflow-dev}
LOCAL_PORT=8080
REMOTE_PORT=8080

info()  { echo "[port-forward-api] $*"; }
warn()  { echo "[port-forward-api] WARNING: $*" >&2; }
error() { echo "[port-forward-api] ERROR: $*" >&2; exit 1; }

# Prefer the API server label if present.
POD=$(kubectl get pods -n "$NAMESPACE" -l component=api-server -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [[ -z "$POD" ]]; then
  info "No pod found with label component=api-server in namespace '$NAMESPACE'."
  info "Trying to find a pod name containing 'api'..."
  POD=$(kubectl get pods -n "$NAMESPACE" -o name | grep -Ei 'api' | head -n 1 | cut -d'/' -f2 || true)
fi

if [[ -z "$POD" ]]; then
  error "Could not find an Airflow API pod in namespace '$NAMESPACE'."
fi

info "Port-forwarding pod '$POD' in namespace '$NAMESPACE' to localhost:$LOCAL_PORT (remote $REMOTE_PORT)"

kubectl port-forward -n "$NAMESPACE" "pod/$POD" "$LOCAL_PORT:$REMOTE_PORT"
