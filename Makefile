# Makefile for common project tasks

.PHONY: build-image push-image helm-deploy helm-uninstall sync-dags create-pvcs

IMAGE?=airflow3-starter:latest
CHART_NAME?=dev-airflow
NAMESPACE?=airflow-dev

helm-deploy:
	helm repo add apache-airflow https://airflow.apache.org || true
	helm repo update
	helm upgrade --install $(CHART_NAME) apache-airflow/airflow \
	  --namespace $(NAMESPACE) --create-namespace \
	  --values helm/values.yaml

helm-uninstall:
	helm uninstall $(CHART_NAME) -n $(NAMESPACE)

# copy local dags into the PVC and restart the dag processor pod
# this reuses the helper shell script for the actual work
sync-dags:
	./scripts/sync_dags.sh $(NAMESPACE)

# create persistent volume claims for dags and logs in the target namespace
create-pvcs:
	kubectl apply -f helm/dags-pvc.yaml -n $(NAMESPACE)
	kubectl apply -f helm/logs-pvc.yaml -n $(NAMESPACE)
