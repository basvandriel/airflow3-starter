"""
Pytest configuration and shared fixtures for deployment tests.

Pass deployment parameters via the CLI:
    pytest tests/ --namespace airflow-prod --chart-name prod-airflow --expect-custom-image
    pytest tests/ --e2e
"""

import pytest
from kubernetes import client, config
from kubernetes.client import CoreV1Api


# -- CLI options --


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--namespace", default="airflow-dev", help="Kubernetes namespace")
    parser.addoption("--chart-name", default="dev-airflow", help="Helm release name")
    parser.addoption(
        "--expect-custom-image",
        action="store_true",
        default=False,
        help="Assert the dag-processor uses a non-upstream image",
    )
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run end-to-end DAG trigger test",
    )


# -- Kubernetes client --


@pytest.fixture(scope="session")
def k8s() -> CoreV1Api:
    """Session-scoped Kubernetes CoreV1Api client loaded from the active kubeconfig."""
    config.load_kube_config()
    return client.CoreV1Api()


# -- Parametrised fixtures --


@pytest.fixture(scope="session")
def namespace(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--namespace")


@pytest.fixture(scope="session")
def chart_name(request: pytest.FixtureRequest) -> str:
    return request.config.getoption("--chart-name")


@pytest.fixture(scope="session")
def expect_custom_image(request: pytest.FixtureRequest) -> bool:
    return request.config.getoption("--expect-custom-image")


@pytest.fixture(scope="session")
def e2e(request: pytest.FixtureRequest) -> bool:
    return request.config.getoption("--e2e")
