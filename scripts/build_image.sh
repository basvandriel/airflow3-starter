#!/usr/bin/env bash
# Build and optionally push the custom Airflow image that includes project requirements.
# Usage: ./scripts/build_image.sh [registry/repo[:tag]]

set -euo pipefail

TAG=${1:-"airflow3-starter:latest"}

# you can customize BASE_IMAGE if you want to override
BASE_IMAGE="apache/airflow:3.1.7"

# build locally

docker build --build-arg AIRFLOW_VERSION=3.1.7 -t "$TAG" .

echo "Built image $TAG"

echo "To push, run: docker push $TAG"
