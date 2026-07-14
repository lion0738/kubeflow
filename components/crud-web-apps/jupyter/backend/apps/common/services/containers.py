"""Helpers for provisioning standalone containers."""

import hashlib
import shlex
from typing import Dict, List, Optional, Tuple

from kubeflow.kubeflow.crud_backend import api, authn, logging
from kubernetes import client

from .. import form, utils, volumes
from . import workloads

log = logging.getLogger(__name__)
RDMA_RESOURCE_KEY = "rdma/rdma_shared_device_a"
RDMA_DEFAULT_LIMIT = "1"
LAST_REPLICAS_ANNOTATION = "containers.kubeflow.org/last-replicas"
DNS_LABEL_MAX_LENGTH = 63


def create_custom_container(namespace: str, body: Dict):
    """Create a StatefulSet that represents a custom container workload."""
    name = body.get("name")
    image = body.get("image")
    image_pull_policy = body.get("imagePullPolicy", "IfNotPresent")
    command = body.get("command", "")
    replicas = body.get("replicas", 1)
    ports = body.get("ports", [])
    resources_dict = body.get("resources", {})
    envs = body.get("envs", [])

    if workloads.get_container_workload(namespace, name) is not None:
        raise ValueError(f"Container '{name}' already exists.")

    try:
        replicas = max(1, int(replicas))
    except (TypeError, ValueError):
        replicas = 1

    # Add RDMA shared device to limits unless user provided it
    limits_dict = dict(resources_dict)
    limits_dict.setdefault(RDMA_RESOURCE_KEY, RDMA_DEFAULT_LIMIT)

    resources = client.V1ResourceRequirements(
        requests=resources_dict,
        limits=limits_dict
    )

    defaults = utils.load_spawner_ui_config()
    api_volumes = form.get_form_value(body, defaults, "datavols",
                                      "dataVolumes") or []

    _validate_per_replica_volumes(api_volumes, replicas)
    _dry_run_volumes(api_volumes, namespace)

    new_volumes, new_volume_mounts, claim_templates = _create_volumes(
        api_volumes, namespace
    )

    command_list = shlex.split(command) if command.strip() else None
    env_vars = _build_env_vars(envs)

    security_ctx = client.V1SecurityContext(
        capabilities=client.V1Capabilities(add=["IPC_LOCK"])
    )

    container = client.V1Container(
        name=name,
        image=image,
        image_pull_policy=image_pull_policy,
        command=command_list,
        ports=[client.V1ContainerPort(container_port=p) for p in ports],
        resources=resources,
        env=env_vars or None,
        volume_mounts=new_volume_mounts or None,
        security_context=security_ctx
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(
            labels={
                "app": name,
                "container-type": "custom-container",
                "notebook-name": name
            },
            annotations={
                "k8s.v1.cni.cncf.io/networks": "nvidia-network-operator/ipoibnetwork",
                "sidecar.istio.io/inject": "false",
            }
        ),
        spec=client.V1PodSpec(
            scheduler_name="reservation-scheduler",
            containers=[container],
            restart_policy="Always",
            volumes=new_volumes or None,
            termination_grace_period_seconds=15,
        )
    )

    headless_service_name = _dns_label_name(f"{name}-headless")
    spec = client.V1StatefulSetSpec(
        replicas=replicas,
        selector=client.V1LabelSelector(match_labels={"app": name}),
        template=template,
        service_name=headless_service_name,
        pod_management_policy="Parallel",
        update_strategy=client.V1StatefulSetUpdateStrategy(
            type="RollingUpdate"
        ),
        volume_claim_templates=claim_templates or None,
    )

    statefulset = client.V1StatefulSet(
        metadata=client.V1ObjectMeta(
            name=name,
            labels={"container-type": "custom-container", "app": name},
            annotations={
                "notebooks.kubeflow.org/creator": authn.get_username(),
                LAST_REPLICAS_ANNOTATION: str(replicas),
            }
        ),
        spec=spec
    )

    log.info("Creating custom container StatefulSet %s", name)
    result = api.create_statefulset(namespace=namespace, body=statefulset)
    try:
        _create_headless_service(namespace, result, headless_service_name, name)
    except Exception:
        api.delete_statefulset(name=name, namespace=namespace)
        raise
    return result


def _create_headless_service(namespace: str,
                             statefulset,
                             service_name: str,
                             workload_name: str) -> None:
    owner_reference = client.V1OwnerReference(
        api_version=statefulset.api_version or "apps/v1",
        kind=statefulset.kind or "StatefulSet",
        name=statefulset.metadata.name,
        uid=statefulset.metadata.uid,
    )
    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=service_name,
            owner_references=[owner_reference],
            labels={
                "app": workload_name,
                "container-type": "custom-container",
            },
        ),
        spec=client.V1ServiceSpec(
            cluster_ip="None",
            publish_not_ready_addresses=True,
            selector={"app": workload_name},
            ports=[client.V1ServicePort(
                name="identity",
                port=1,
                target_port=1,
                protocol="TCP",
            )],
        ),
    )
    api.create_service(namespace=namespace, body=service)


def _dry_run_volumes(api_volumes: List[Dict], namespace: str) -> None:
    for api_volume in api_volumes:
        if api_volume.get("perReplica"):
            continue
        pvc = volumes.get_new_pvc(api_volume)
        if pvc is None:
            continue
        api.create_pvc(pvc, namespace, dry_run=True)


def _create_volumes(api_volumes: List[Dict], namespace: str) -> Tuple[List,
                                                                      List,
                                                                      List]:
    new_volumes = []
    new_volume_mounts = []
    claim_templates = []
    for api_volume in api_volumes:
        pvc = volumes.get_new_pvc(api_volume)
        if api_volume.get("perReplica"):
            claim_templates.append(pvc)
            new_volume_mounts.append(
                volumes.get_container_mount(api_volume, pvc.metadata.name)
            )
            continue

        if pvc is not None:
            log.info("Creating PVC for custom container: %s", pvc)
            pvc = api.create_pvc(pvc, namespace)

        v1_volume = volumes.get_pod_volume(api_volume, pvc)
        mount = volumes.get_container_mount(api_volume, v1_volume["name"])

        new_volumes.append(v1_volume)
        new_volume_mounts.append(mount)

    return new_volumes, new_volume_mounts, claim_templates


def _validate_per_replica_volumes(api_volumes: List[Dict], replicas: int) -> None:
    template_names = set()
    shared_volume_names = set()
    for api_volume in api_volumes:
        if api_volume.get("perReplica") is True:
            continue
        pvc = volumes.get_new_pvc(api_volume)
        if pvc is not None and pvc.metadata and pvc.metadata.name:
            shared_volume_names.add(pvc.metadata.name)
            continue
        source = api_volume.get("existingSource", {})
        claim = source.get("persistentVolumeClaim", {})
        if claim.get("claimName"):
            shared_volume_names.add(claim["claimName"])

    for api_volume in api_volumes:
        per_replica = api_volume.get("perReplica", False)
        if not isinstance(per_replica, bool):
            raise ValueError("Volume perReplica must be a boolean.")
        if not per_replica:
            continue
        if replicas < 2:
            raise ValueError(
                "Per-replica volumes require at least two replicas."
            )
        pvc = volumes.get_new_pvc(api_volume)
        if pvc is None:
            raise ValueError(
                "Per-replica storage is only supported for new volumes."
            )
        if not pvc.metadata or not pvc.metadata.name:
            raise ValueError(
                "Per-replica volume claims must have a metadata.name."
            )
        if pvc.metadata.name in template_names:
            raise ValueError(
                f"Duplicate per-replica volume name: {pvc.metadata.name}"
            )
        if pvc.metadata.name in shared_volume_names:
            raise ValueError(
                "Per-replica and shared volumes must use different names: "
                f"{pvc.metadata.name}"
            )
        template_names.add(pvc.metadata.name)


def _dns_label_name(value: str) -> str:
    value = value.lower()
    if len(value) <= DNS_LABEL_MAX_LENGTH:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    prefix = value[:DNS_LABEL_MAX_LENGTH - len(digest) - 1].rstrip("-")
    return f"{prefix}-{digest}"


def _build_env_vars(envs: List[Dict]) -> Optional[List[client.V1EnvVar]]:
    env_vars: List[client.V1EnvVar] = []
    for env in envs:
        env_name = env.get("name")
        env_value = env.get("value")
        if env_name:
            env_vars.append(client.V1EnvVar(name=env_name, value=env_value))

    return env_vars or None
