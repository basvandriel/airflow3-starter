# Makefile for common project tasks

.PHONY: build-image push-image helm-deploy helm-uninstall

IMAGE?=airflow3-starter:latest
CHART_NAME?=dev-airflow
NAMESPACE?=airflow-dev

build-image:
	./scripts/build_image.sh $(IMAGE)

push-image:
	docker push $(IMAGE)

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
