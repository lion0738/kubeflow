import os
import random
import string

from cachetools.func import ttl_cache
from kubernetes import client
from werkzeug import exceptions

from kubeflow.kubeflow.crud_backend import helpers, logging

from . import status

log = logging.getLogger(__name__)

FILE_ABS_PATH = os.path.abspath(os.path.dirname(__file__))

NOTEBOOK_TEMPLATE_YAML = os.path.join(
    FILE_ABS_PATH, "yaml/notebook_template.yaml"
)
LAST_ACTIVITY_ANNOTATION = "notebooks.kubeflow.org/last-activity"

# The production configuration is mounted on the app's pod via a configmap
DEV_CONFIG = os.path.join(FILE_ABS_PATH, "yaml/spawner_ui_config.yaml")
CONFIGS = [
    "/etc/config/spawner_ui_config.yaml",
    DEV_CONFIG,
]


def random_string(size=9, chars=string.ascii_lowercase + string.digits):
    """Create a random string."""
    return "".join(random.choice(chars) for _ in range(size))


def load_notebook_template(**kwargs):
    """
    kwargs: the parameters to be replaced in the yaml

    Reads the yaml for the web app's custom resource, replaces the variables
    and returns it as a python dict.
    """
    return helpers.load_param_yaml(NOTEBOOK_TEMPLATE_YAML, **kwargs)


@ttl_cache(ttl=60)
def load_spawner_ui_config():
    for config in CONFIGS:
        config_dict = helpers.load_yaml(config)

        if config_dict is not None:
            log.info("Using config file: %s", config)
            return config_dict["spawnerFormDefaults"]

    log.error("Couldn't find any config file.")
    raise exceptions.NotFound("Couldn't find any config file.")


def process_gpus(container):
    """
    This function will expose two things, regarding GPUs:
    1. The total number of GPUs that the Notebook has requested
    2. A message describing how many GPUs from each venders it requested

    This function will check the vendors that the admin has defined in the
    app's config file.
    """
    # get the GPU vendors from the app's config
    config = load_spawner_ui_config()
    cfg_vendors = config.get("gpus", {}).get("value", {}).get("vendors", [])
    # create a dict mapping the limits key with the UI name.
    # For example: "nvidia.com/gpu": "NVIDIA"
    gpu_vendors = {v["limitsKey"]: v["uiName"] for v in cfg_vendors}

    count = 0
    gpus = []
    if hasattr(container, "resources") and container.resources and container.resources.limits:
        resource_limits = container.resources.limits
    elif isinstance(container, dict):
        resource_limits = container.get("resources", {}).get("limits", {})
    else:
        resource_limits = {}
    for vendor in gpu_vendors.keys():
        if vendor not in resource_limits:
            continue

        gpu_count = resource_limits[vendor]
        count += int(gpu_count)

        # final message will be like: 1 NVIDIA, 2 AMD
        gpus.append("%s %s" % (gpu_count, gpu_vendors[vendor]))

    return {"count": count, "message": ", ".join(gpus)}


def pvc_from_dict(vol, namespace):
    if vol is None:
        return None

    return client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=vol["name"],
            namespace=namespace,
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=[vol["mode"]],
            storage_class_name=get_storage_class(vol),
            resources=client.V1ResourceRequirements(
                requests={"storage": vol["size"]}
            ),
        ),
    )


def get_storage_class(vol):
    # handle the StorageClass
    if "class" not in vol:
        return None
    if vol["class"] == "{empty}":
        return ""
    if vol["class"] == "{none}":
        return None
    else:
        return vol["class"]


# Functions for transforming the data from k8s api
def get_notebook_last_activity(notebook):
    annotations = notebook["metadata"].get("annotations", {})
    return annotations.get(LAST_ACTIVITY_ANNOTATION, "")


def notebook_dict_from_k8s_obj(notebook, pods):
    cntr = notebook["spec"]["template"]["spec"]["containers"][0]
    server_type = None
    owner = None
    ip = None
    if notebook["metadata"].get("annotations"):
        annotations = notebook["metadata"]["annotations"]
        server_type = annotations.get("notebooks.kubeflow.org/server-type")
        owner = annotations.get("notebooks.kubeflow.org/creator")

    nb_name = notebook["metadata"]["name"]
    nb_namespace = notebook["metadata"]["namespace"]
    matching_pods = [
        pod for pod in pods.items
        if pod.metadata.name.startswith(nb_name) and pod.metadata.namespace == nb_namespace
    ]
    if matching_pods:
        ip = matching_pods[0].status.pod_ip

    return {
        "name": notebook["metadata"]["name"],
        "namespace": notebook["metadata"]["namespace"],
        "owner": owner,
        "ip": ip,
        "serverType": server_type,
        "age": notebook["metadata"]["creationTimestamp"],
        "last_activity": get_notebook_last_activity(notebook),
        "image": cntr["image"],
        "shortImage": cntr["image"].split("/")[-1],
        "cpu": cntr["resources"]["requests"]["cpu"],
        "gpus": process_gpus(cntr),
        "memory": cntr["resources"]["requests"]["memory"],
        "volumes": [v["name"] for v in cntr["volumeMounts"]],
        "status": status.process_status(notebook),
        "metadata": notebook["metadata"],
    }

def container_dict_from_k8s_obj(deployment, pod):
    container = deployment.spec.template.spec.containers[0]
    resources = container.resources.requests or {}

    annotations = deployment.metadata.annotations or {}
    owner = annotations.get("notebooks.kubeflow.org/creator")

    return {
        "name": deployment.metadata.name,
        "namespace": deployment.metadata.namespace,
        "owner": owner,
        "ip": pod.status.pod_ip if pod else None,
        "serverType": "container",
        "age": deployment.metadata.creation_timestamp,
        "last_activity": None,
        "image": container.image,
        "shortImage": container.image.split("/")[-1],
        "cpu": resources.get("cpu"),
        "gpus": process_gpus(container),
        "memory": resources.get("memory"),
        "volumes": [v.name for v in container.volume_mounts] if container.volume_mounts else [],
        "status": status.process_container_status(deployment, pod),
        "metadata": deployment.metadata.to_dict(),
    }

