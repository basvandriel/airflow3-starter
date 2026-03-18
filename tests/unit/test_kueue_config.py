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


def test_kueue_values_uses_pod_framework() -> None:
    """helm/kueue-values.yaml must enable the 'pod' integration framework."""

    with open("helm/kueue-values.yaml") as f:
        vals = yaml.safe_load(f)
    cfg_yaml = vals["managerConfig"]["controllerManagerConfigYaml"]
    cfg = yaml.safe_load(cfg_yaml)
    frameworks = cfg.get("integrations", {}).get("frameworks", [])
    assert "pod" in frameworks
