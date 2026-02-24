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

gen-configmap:
	# generate a ConfigMap manifest from the local dags directory
	kubectl create configmap airflow-dags --namespace=$(NAMESPACE) \
	  --from-file=dags/ --dry-run=client -o yaml > helm/airflow-dags.yaml

helm-uninstall:
	helm uninstall $(CHART_NAME) -n $(NAMESPACE)

get-default-values:
	# fetch the chart's default values for reference
	helm show values apache-airflow/airflow > helm/default-values.yaml
