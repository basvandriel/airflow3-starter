#!/usr/bin/env bash
# Apply Kueue queue resources (ClusterQueue + LocalQueue) into an Airflow namespace.
#
# Usage:
#   ./scripts/apply_kueue_resources.sh <airflow-namespace>
#
# This script applies the kube resources from helm/kueue-resources.yaml and
# substitutes the namespace for the LocalQueue entry.

set -euo pipefail

AIRFLOW_NAMESPACE=${1:-airflow-dev}
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Kueue's webhook can reject requests briefly after rollout even if the pod is
# Ready. Retry until the apply succeeds (idempotent).

deadline=$((SECONDS + 120))
while true; do
  if sed "s|namespace: \"airflow-dev\"|namespace: \"$AIRFLOW_NAMESPACE\"|g" \
      "$REPO_DIR/helm/kueue-resources.yaml" | kubectl apply -f -; then
    break
  fi

  if [ $SECONDS -ge $deadline ]; then
    echo "Timed out waiting for Kueue webhook to accept requests" >&2
    exit 1
  fi

  echo "Kueue webhook not ready yet; retrying in 5s..."
  sleep 5
done

echo "Kueue resources applied for namespace '$AIRFLOW_NAMESPACE'"
