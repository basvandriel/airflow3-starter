import yaml


def test_pod_template_has_kueue_queue_label() -> None:
    """The pod template must carry kueue.x-k8s.io/queue-name as a *label*.

    Kueue's mutating webhook only injects a scheduling gate when this key is a
    label on the pod.
    """

    with open("helm/pod_template.yaml") as f:
        tmpl = yaml.safe_load(f)
    labels = tmpl.get("metadata", {}).get("labels", {})
    assert "kueue.x-k8s.io/queue-name" in labels


def test_pod_template_has_no_kueue_managed_label() -> None:
    """Kueue sets kueue.x-k8s.io/managed itself; pre-setting it breaks admission."""

    with open("helm/pod_template.yaml") as f:
        tmpl = yaml.safe_load(f)
    labels = tmpl.get("metadata", {}).get("labels", {})
    assert "kueue.x-k8s.io/managed" not in labels


def test_kueue_resources_yaml_has_required_kinds() -> None:
    """kueue-resources.yaml must include ResourceFlavor, ClusterQueue and LocalQueue."""

    with open("helm/kueue-resources.yaml") as f:
        docs = list(yaml.safe_load_all(f))
    kinds = {d["kind"] for d in docs if d}
    assert "ResourceFlavor" in kinds
    assert "ClusterQueue" in kinds
    assert "LocalQueue" in kinds


def test_kueue_values_uses_pod_framework() -> None:
    """helm/kueue-values.yaml must enable the 'pod' integration framework."""

    with open("helm/kueue-values.yaml") as f:
        vals = yaml.safe_load(f)
    cfg_yaml = vals["managerConfig"]["controllerManagerConfigYaml"]
    cfg = yaml.safe_load(cfg_yaml)
    frameworks = cfg.get("integrations", {}).get("frameworks", [])
    assert "pod" in frameworks


def test_kueue_memory_test_dag_has_queue_name_label() -> None:
    """The DAG file must reference the queue-name label key (for docs correctness)."""

    with open("dags/kueue_memory_test.py") as f:
        src = f.read()
    assert "kueue.x-k8s.io/queue-name" in src
