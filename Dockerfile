FROM apache/airflow:3.1.7

# Install project dependencies on top of the official image.
# It is best practice to pin apache-airflow to the same version as the base image
# so pip does not attempt to downgrade or upgrade it.
ARG AIRFLOW_VERSION=3.1.7
ADD requirements.txt .
RUN pip install apache-airflow==${AIRFLOW_VERSION} -r requirements.txt
