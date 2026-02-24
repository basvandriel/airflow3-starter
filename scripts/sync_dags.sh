#!/usr/bin/env bash
# copy the local dags directory into the PVC mounted by the dag-processor
# and then restart the dag-processor pod so Airflow immediately rescans.
# Usage: ./scripts/sync_dags.sh [<namespace>]

set -euo pipefail

NAMESPACE=${1:-airflow-dev}

# find a dag-processor pod
POD=$(kubectl get pod -n "$NAMESPACE" -l component=dag-processor -o jsonpath='{.items[0].metadata.name}')
if [[ -z "$POD" ]]; then
    echo "error: no dag-processor pod found in namespace $NAMESPACE" >&2
    exit 1
fi

echo "copying dags to pod $POD (namespace $NAMESPACE)"
# use kubectl cp for simplicity; be aware that it may not copy hidden files
# if you use shell patterns, so we specify the directory explicitly
kubectl cp dags/. "$NAMESPACE/$POD:/opt/airflow/dags"

echo "deleting pod $POD to force reload"
kubectl delete pod "$POD" -n "$NAMESPACE"

echo "done"
