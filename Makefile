# Makefile for common project tasks

.PHONY: build-image push-image helm-deploy helm-deploy-prod helm-uninstall sync-dags create-pvcs create-logs-pvc test test-prod test-e2e test-prod-e2e

# ── Image settings ────────────────────────────────────────────────────────────
# Override IMAGE_REPO and IMAGE_TAG to use your own registry, e.g.:
#   make build-image IMAGE_REPO=registry.example.com/myteam/airflow3-starter IMAGE_TAG=1.0.0
IMAGE_REPO?=airflow3-starter
IMAGE_TAG?=latest
IMAGE?=$(IMAGE_REPO):$(IMAGE_TAG)

# ── Dev deployment settings ───────────────────────────────────────────────────
CHART_NAME?=dev-airflow
NAMESPACE?=airflow-dev

# ── Prod deployment settings ──────────────────────────────────────────────────
PROD_CHART_NAME?=prod-airflow
PROD_NAMESPACE?=airflow-prod

# ── Image targets ─────────────────────────────────────────────────────────────

build-image:
	docker build --tag $(IMAGE) .

push-image: build-image
	docker push $(IMAGE)

setup-helm-repos:
	helm repo add apache-airflow https://airflow.apache.org || true
	helm repo update
# ── Dev deployment ────────────────────────────────────────────────────────────

helm-deploy: create-pvcs
	# --set-file loads pod_template.yaml into the top-level `podTemplate` value
	# which the chart uses to write pod_template_file.yaml into the config
	# ConfigMap. No Helm-values wrapping needed in the file.
	helm upgrade --install $(CHART_NAME) apache-airflow/airflow \
	  --namespace $(NAMESPACE) --create-namespace \
	  --values helm/values.yaml \
	  --set-file podTemplate=helm/pod_template.yaml

# ── Prod deployment ───────────────────────────────────────────────────────────
# Builds and pushes the image, then deploys using the baked-in DAGs image.
# Override IMAGE_REPO and IMAGE_TAG to control the registry/tag, e.g.:
#   make helm-deploy-prod IMAGE_REPO=registry.example.com/myteam/airflow3-starter IMAGE_TAG=1.2.3

helm-deploy-prod: push-image
	kubectl apply -f helm/logs-pvc.yaml -n $(PROD_NAMESPACE)
	
	helm upgrade --install $(PROD_CHART_NAME) apache-airflow/airflow \
	  --namespace $(PROD_NAMESPACE) --create-namespace \
	  --values helm/values.prod.yaml \
	  --set defaultAirflowRepository=$(IMAGE_REPO) \
	  --set defaultAirflowTag=$(IMAGE_TAG)

helm-uninstall:
	helm uninstall $(CHART_NAME) -n $(NAMESPACE)

# ── Helpers ───────────────────────────────────────────────────────────────────

# install Kueue in the same namespace as the Airflow deployment
install-kueue:
	./scripts/install_kueue.sh $(NAMESPACE)

# copy local dags into the PVC and restart the dag processor pod
# this reuses the helper shell script for the actual work
sync-dags:
	./scripts/sync_dags.sh $(NAMESPACE)

# create persistent volume claims for dags and logs in the target namespace
create-pvcs: create-logs-pvc
	kubectl apply -f helm/dags-pvc.yaml -n $(NAMESPACE)

create-logs-pvc:
	kubectl apply -f helm/logs-pvc.yaml -n $(NAMESPACE)

# ── Tests ─────────────────────────────────────────────────────────────────────

# Smoke-test the dev deployment.
test:
	uv run pytest tests/ \
	  --namespace $(NAMESPACE) \
	  --chart-name $(CHART_NAME)

# Smoke-test the prod deployment (asserts custom image is used).
test-prod:
	uv run pytest tests/ \
	  --namespace $(PROD_NAMESPACE) \
	  --chart-name $(PROD_CHART_NAME) \
	  --expect-custom-image

# Smoke + end-to-end: triggers hello_world and waits for completion.
test-e2e:
	uv run pytest tests/ \
	  --namespace $(NAMESPACE) \
	  --chart-name $(CHART_NAME) \
	  --e2e

test-prod-e2e:
	uv run pytest tests/ \
	  --namespace $(PROD_NAMESPACE) \
	  --chart-name $(PROD_CHART_NAME) \
	  --expect-custom-image \
	  --e2e

docker-compose-shell:
	docker compose run --rm --entrypoint /bin/bash airflow-cli

docker-compose-reset-db:
	docker compose exec airflow-worker airflow db reset --yes