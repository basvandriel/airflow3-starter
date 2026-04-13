FROM apache/airflow:3.2.0

# Install project dependencies on top of the official image.
# It is best practice to pin apache-airflow to the same version as the base image
# so pip does not attempt to downgrade or upgrade it.
COPY --chown=airflow:root pyproject.toml uv.lock /home/airflow/
WORKDIR /home/airflow

USER airflow

RUN pip install --user --no-cache-dir uv
RUN uv sync --locked --no-dev

# Copy DAGs into the image for production deployments.
# For local/dev, DAGs are mounted from a PVC instead (see helm/values.yaml).
COPY --chown=airflow:root dags/ /opt/airflow/dags/
