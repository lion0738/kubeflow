"""Helpers for provisioning standalone containers."""

import shlex
from typing import Dict, List, Optional, Tuple

from kubeflow.kubeflow.crud_backend import api, authn, logging
from kubernetes import client

from .. import form, utils, volumes

log = logging.getLogger(__name__)


def create_custom_container(namespace: str, body: Dict):
    """Create a Deployment that represents a single custom container."""
    name = body.get("name")
    image = body.get("image")
    command = body.get("command", "")
    ports = body.get("ports", [])
    resources_dict = body.get("resources", {})
    envs = body.get("envs", [])

    resources = client.V1ResourceRequirements(
        requests=resources_dict,
        limits=resources_dict
    )

    defaults = utils.load_spawner_ui_config()
    api_volumes = form.get_form_value(body, defaults, "datavols",
                                      "dataVolumes") or []

    _dry_run_volumes(api_volumes, namespace)

    new_volumes, new_volume_mounts = _create_volumes(api_volumes, namespace)

    command_list = shlex.split(command) if command.strip() else None
    env_vars = _build_env_vars(envs)

    container = client.V1Container(
        name=name,
        image=image,
        command=command_list,
        ports=[client.V1ContainerPort(container_port=p) for p in ports],
        resources=resources,
        env=env_vars or None,
        volume_mounts=new_volume_mounts or None
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(
            labels={
                "app": name,
                "container-type": "custom-container",
                "notebook-name": name
            }
        ),
        spec=client.V1PodSpec(
            scheduler_name="reservation-scheduler",
            containers=[container],
            restart_policy="Always",
            volumes=new_volumes or None
        )
    )

    spec = client.V1DeploymentSpec(
        replicas=1,
        selector=client.V1LabelSelector(match_labels={"app": name}),
        template=template
    )

    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(
            name=name,
            labels={"container-type": "custom-container", "app": name},
            annotations={"notebooks.kubeflow.org/creator": authn.get_username()}
        ),
        spec=spec
    )

    log.info("Creating custom container deployment %s", name)
    return api.create_deployment(namespace=namespace, body=deployment)


def _dry_run_volumes(api_volumes: List[Dict], namespace: str) -> None:
    for api_volume in api_volumes:
        pvc = volumes.get_new_pvc(api_volume)
        if pvc is None:
            continue
        api.create_pvc(pvc, namespace, dry_run=True)


def _create_volumes(api_volumes: List[Dict], namespace: str) -> Tuple[List,
                                                                      List]:
    new_volumes = []
    new_volume_mounts = []
    for api_volume in api_volumes:
        pvc = volumes.get_new_pvc(api_volume)
        if pvc is not None:
            log.info("Creating PVC for custom container: %s", pvc)
            pvc = api.create_pvc(pvc, namespace)

        v1_volume = volumes.get_pod_volume(api_volume, pvc)
        mount = volumes.get_container_mount(api_volume, v1_volume["name"])

        new_volumes.append(v1_volume)
        new_volume_mounts.append(mount)

    return new_volumes, new_volume_mounts


def _build_env_vars(envs: List[Dict]) -> Optional[List[client.V1EnvVar]]:
    env_vars: List[client.V1EnvVar] = []
    for env in envs:
        env_name = env.get("name")
        env_value = env.get("value")
        if env_name:
            env_vars.append(client.V1EnvVar(name=env_name, value=env_value))

    return env_vars or None
