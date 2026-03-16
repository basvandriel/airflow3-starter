# Airflow 3 Starter Project

This is a starter project for Apache Airflow 3 using UV for dependency management.

## Setup

1. Ensure you have UV installed: `pip install uv`
2. Clone or navigate to this project
3. Install dependencies: `uv sync`

## Running Locally

To start Airflow in standalone mode (includes webserver and scheduler):

```bash
AIRFLOW_HOME=. AIRFLOW__CORE__LOAD_EXAMPLES=False uv run airflow standalone
```

This will:
- Set AIRFLOW_HOME to the current directory
- Disable loading of example DAGs
- Initialize the SQLite database (if not already done)
- Start the webserver on http://localhost:8080
- Start the scheduler

## Alternative: System-wide AIRFLOW_HOME with Project DAGs

If you prefer a system-wide AIRFLOW_HOME (like `~/airflow`) while keeping DAGs in this repo (similar to Dagster's approach):

Use the provided `run.sh` script:

```bash
./run.sh
```

This script:
- Sets `AIRFLOW_HOME=~/airflow` (or uses existing `AIRFLOW_HOME` env var)
- Points `AIRFLOW__CORE__DAGS_FOLDER` to `./dags`
- Disables example DAGs (`AIRFLOW__CORE__LOAD_EXAMPLES=False`)
- Initializes the database if needed
- Runs `airflow standalone`

Or manually:
```bash
AIRFLOW_HOME=~/airflow AIRFLOW__CORE__DAGS_FOLDER=$(pwd)/dags AIRFLOW__CORE__LOAD_EXAMPLES=False uv run airflow standalone
```

This keeps the database, logs, and config in `~/airflow`, but loads DAGs from your project's `dags/` directory.

## Accessing the UI

Open http://localhost:8080 in your browser.

Default credentials:
- Username: admin
- Password: admin

## DAGs

Place your DAG files in the `dags/` directory.

A sample `hello_world.py` DAG is included.

### Advanced Example: download_files.py

A more complex DAG that demonstrates best practices:

- **Modular design**: Business logic separated into `dags/utils/download_utils.py`
- **Python operators**: Uses `PythonOperator` for custom logic
- **XCom communication**: Tasks pass data between each other
- **Error handling**: Proper exception handling and verification
- **Large file support**: Streaming downloads, progress monitoring, timeouts
- **Resource management**: Automatic cleanup of old files

The DAG includes multiple tasks:
1. **setup_workdir**: Creates working directory
2. **download_files_task**: Downloads small sample files
3. **download_large_file**: Downloads large files (3GB+) with progress monitoring
4. **verify_downloads**: Confirms files exist and shows sizes
5. **cleanup_old_files**: Removes files older than 24 hours

**Large File Considerations:**
- Uses streaming downloads to avoid memory issues
- Configurable chunk sizes (1MB for large files)
- Progress callbacks for monitoring
- Extended timeouts (2 hours per task)
- Automatic cleanup to manage disk space

Run it manually from the UI or trigger it to see the modular approach in action.

## Best Practices

- Use virtual environments (handled by UV)
- Keep DAGs simple and testable
- Use Airflow's built-in testing tools
- For production, use proper databases and configurations

## Stopping

Press Ctrl+C to stop the standalone server.

## Deploying to Kubernetes with Helm

A remote k8s cluster is ideal for testing heavy DAGs that need terabytes of data. This project includes a `helm/values.yaml` with
custom overrides for the [official Apache Airflow Helm chart](https://airflow.apache.org/docs/helm-chart/stable/index.html).

### 1. Install the chart

Add the Apache Airflow repo and deploy using your kubeconfig:

```bash
helm repo add apache-airflow https://airflow.apache.org
helm repo update

helm upgrade --install dev-airflow apache-airflow/airflow \
  --namespace airflow-dev --create-namespace \
  --values helm/values.yaml
```

The supplied `values.yaml` is currently set up to mount a **Persistent
Volume Claim** called `my-dags-pvc` into each pod.  This is the method we
recommend for development because it preserves the full directory structure,
so helper modules like `dags/utils` are available without any special tweaks.

To use the PVC approach (or just to prepare the namespace) you can run
helper make targets that bundle the kubectl commands:

```bash
# create both the DAGs and logs PVCs
make create-pvcs

# populate the dags volume with your DAGs
kubectl -n airflow-dev cp -r dags/. pvc/my-dags-pvc:/workdir
```

Alternatively the `helm-deploy` target depends on `create-pvcs` so you
can simply run `make helm-deploy` and it will create the PVCs for you.

We also recommend mounting a separate PVC for logs (`my-logs-pvc`).
Without shared storage the webserver will attempt to contact the worker pod
by its DNS name to retrieve task output.  That works while the pod is
running, but you just saw the error above: the hostname may not be known in
cluster DNS once the pod has finished or if you're retaining pods for
debugging.  A common workaround is to enable remote logging; the quickest
fix in this demo is a shared volume so the UI reads logs directly.

```bash
# create the logs claim
kubectl apply -f helm/logs-pvc.yaml -n airflow-dev
```

The `helm/values.yaml` file already mounts both PVCs under `/opt/airflow` and
sets `AIRFLOW__CORE__BASE_LOG_FOLDER` accordingly.  After the logs claim is
in place the scheduler/webserver will see every task log as soon as it's
written to disk and the UI will no longer reach out to worker pods.

The `helm/values.yaml` volume/volumeMount entries will mount the claim at
`/opt/airflow/dags` in every component.  After populating the PVC, install or
upgrade the chart as shown above; the pods will restart with the new DAGs
present.

> **Quick note:** you can still use a ConfigMap or git-sync if desired, but
> those methods either flatten directories or require a repository.  PVCs are
> simple and work well for local development and testing with helper modules.

Other options include:
* **git-sync** – the chart can clone a Git repository into the DAGs folder,
  automatically keeping everything up to date.
* **Bake into the image** – copy the `dags/` tree into the container at build
  time and install it as a package; this is ideal for production but requires
  rebuilding for DAG changes.
> See the values examples earlier in `helm/values.yaml` for snippets.

### Using KubernetesExecutor

We configure the release to use the KubernetesExecutor.  Each task runs in a
separate Kubernetes pod; the scheduler merely creates pods and watches their
status.  The chart takes care of RBAC and service account setup (`rbac.create:
true` and `allowPodLaunching: true` in values).

To switch, set the following in `helm/values.yaml` (already done in this
repository):

```yaml
executor: "KubernetesExecutor"
allowPodLaunching: true
rbac:
  create: true
```

You can customise the *pod template* that KubernetesExecutor uses for
task pods, but you **don't have to**.  By default the chart writes its own
`pod-template-file.kubernetes-helm-yaml` (see
[upstream source](https://github.com/apache/airflow/blob/main/chart/files/pod-template-file.kubernetes-helm-yaml))
and uses that when `kubernetes_executor.podTemplate` is left unset.

This repository keeps `helm/pod_template.yaml` as a convenient copy of
the upstream default so that you can start editing in-place.


### 3. Access the UI

Forward the webserver port or create a service:

```bash
kubectl -n airflow-dev port-forward svc/dev-airflow-api-server 8080:8080
```

Open <http://localhost:8080> and login with the credentials shown in the chart's output (typically `admin/admin`).

### 4. Iteration

- Modify DAGs locally and synchronise them to the cluster.  You can do it
  manually:
  ```bash
  kubectl cp dags/. airflow-dev/dev-airflow-dag-processor-<pod>:/opt/airflow/dags -n airflow-dev
  kubectl delete pod -n airflow-dev dev-airflow-dag-processor-<pod>
  ```
  or use the helper Makefile target or script:
  ```bash
  make sync-dags            # finds the pod & performs copy+restart
  ./scripts/sync_dags.sh    # equivalent shell script
  ```
  (any pod that mounts the `my-dags-pvc` volume will work—I usually pick
  the dag-processor or scheduler.)
- Run `helm upgrade` if you change chart values.
- Scale worker replicas via `--set worker.replicas=<n>` to handle large loads.
- Tear down when finished: `helm uninstall dev-airflow -n airflow-dev`.

The PVC method means `/opt/airflow/dags` in every container is your DAG tree,
so imports and subpackages behave exactly as they do locally.  No
`.airflowignore` workarounds needed.

> **Port-forward reminder:** whenever you need to access the UI/API run:
> ```bash
> kubectl -n airflow-dev port-forward svc/dev-airflow-api-server 8080:8080
> ```
> Or use the helper script that finds the API pod automatically:
> ```bash
> ./scripts/port_forward_api.sh airflow-dev
> ```
> open http://localhost:8080 and use the credentials shown by Helm (`admin/admin`).

This setup gives you a development environment running in your remote
cluster so you can execute realistic, large-scale workflows while still
working on your laptop. Adjust `values.yaml` as needed for connections,
secrets, and resources.



### Debugging with `dag.test()` with local development

1. (If port is busy) Kill port 5683:
```bash
docker compose exec -T airflow-worker pkill -f debugpy || true
```

2. Start debugpy in the worker (blocks until VS Code attaches):
```bash
docker compose exec -T airflow-worker python -Xfrozen_modules=off -m debugpy --log-to-stderr --log-to /tmp/debugpy-logs --listen 0.0.0.0:5683 --wait-for-client /opt/airflow/scripts/debug_runner.py /opt/airflow/dags/download_files.py
```

3. Set breakpoints in the DAG file, then press **F5** with `Airflow: Debug Tasks (active file)`.