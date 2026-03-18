#!/usr/bin/env bash
set -x

# ============================================================
# Step 1: Force Helm uninstall (skip hooks, ignore errors)
# ============================================================
helm uninstall dev-airflow -n airflow-dev --no-hooks 2>&1 || true
helm uninstall kueue -n kueue-system --no-hooks 2>&1 || true

# ============================================================
# Step 2: Nuke all Kueue CRD finalizers (patch via API)
# ============================================================
for CRD in $(kubectl get crd -o name 2>/dev/null | grep kueue); do
  kubectl patch "$CRD" -p '{"metadata":{"finalizers":[]}}' --type=merge 2>/dev/null || true
done

# ============================================================
# Step 3: Remove finalizers from all Kueue CRs in all namespaces
# ============================================================
for NS in airflow-dev kueue-system; do
  for RESOURCE in workloads localqueues clusterqueues resourceflavors; do
    for NAME in $(kubectl get "$RESOURCE" -n "$NS" -o name 2>/dev/null); do
      kubectl patch "$NAME" -n "$NS" -p '{"metadata":{"finalizers":[]}}' --type=merge 2>/dev/null || true
    done
  done
done
# clusterqueues and resourceflavors are cluster-scoped
for RESOURCE in clusterqueues.kueue.x-k8s.io resourceflavors.kueue.x-k8s.io; do
  for NAME in $(kubectl get "$RESOURCE" -o name 2>/dev/null); do
    kubectl patch "$NAME" -p '{"metadata":{"finalizers":[]}}' --type=merge 2>/dev/null || true
  done
done

# ============================================================
# Step 4: Force-delete all resources in airflow-dev
# ============================================================
kubectl delete all --all -n airflow-dev --force --grace-period=0 2>&1 || true
kubectl delete pvc --all -n airflow-dev --force --grace-period=0 2>&1 || true
kubectl delete configmap --all -n airflow-dev --force --grace-period=0 2>&1 || true
kubectl delete secret --all -n airflow-dev --force --grace-period=0 2>&1 || true
kubectl delete serviceaccount --all -n airflow-dev --force --grace-period=0 2>&1 || true
kubectl delete rolebinding --all -n airflow-dev --force --grace-period=0 2>&1 || true
kubectl delete role --all -n airflow-dev --force --grace-period=0 2>&1 || true

# ============================================================
# Step 5: Force-delete all resources in kueue-system
# ============================================================
kubectl delete all --all -n kueue-system --force --grace-period=0 2>&1 || true
kubectl delete validatingwebhookconfigurations kueue-validating-webhook-configuration --force --grace-period=0 2>&1 || true
kubectl delete mutatingwebhookconfigurations kueue-mutating-webhook-configuration --force --grace-period=0 2>&1 || true

# Delete visibility APIServices that caused namespace stuck last time
kubectl delete apiservice v1beta1.visibility.kueue.x-k8s.io v1beta2.visibility.kueue.x-k8s.io --force --grace-period=0 2>&1 || true

# ============================================================
# Step 6: Patch namespace finalizers to [] then delete
# ============================================================
for NS in airflow-dev kueue-system; do
  kubectl patch namespace "$NS" -p '{"metadata":{"finalizers":[]}}' --type=merge 2>/dev/null || true
  kubectl delete namespace "$NS" --force --grace-period=0 2>&1 || true
done

# ============================================================
# Step 7: Delete Kueue CRDs entirely
# ============================================================
kubectl delete crd $(kubectl get crd -o name | grep kueue | sed 's|customresourcedefinitions.apiextensions.k8s.io/||') --force --grace-period=0 2>&1 || true

echo ""
echo "=== NUKE COMPLETE ==="
kubectl get namespaces | grep -E "airflow-dev|kueue-system" || echo "Both namespaces gone"
helm list -A | grep -E "dev-airflow|kueue" || echo "Both Helm releases gone"
