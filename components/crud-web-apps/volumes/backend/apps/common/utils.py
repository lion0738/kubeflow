from kubeflow.kubeflow.crud_backend import api

from . import status


def parse_pvc(pvc, notebooks, containers=None):
    """
    pvc: client.V1PersistentVolumeClaim

    Process the PVC and format it as the UI expects it.
    """
    try:
        capacity = pvc.status.capacity["storage"]
    except Exception:
        capacity = pvc.spec.resources.requests["storage"]

    notebooks = get_notebooks_using_pvc(pvc.metadata.name, notebooks)
    containers = get_containers_using_pvc(pvc.metadata.name, containers or [])
    parsed_pvc = {
        "name": pvc.metadata.name,
        "namespace": pvc.metadata.namespace,
        "status": status.pvc_status(pvc),
        "age": pvc.metadata.creation_timestamp,
        "capacity": capacity,
        "modes": pvc.spec.access_modes,
        "class": pvc.spec.storage_class_name,
        "notebooks": notebooks,
        "containers": containers,
    }

    return parsed_pvc


def get_notebooks_using_pvc(pvc, notebooks):
    """Return a list of Notebooks that are using the given PVC."""
    mounted_notebooks = []

    for nb in notebooks:
        pvcs = get_notebook_pvcs(nb)
        if pvc in pvcs:
            mounted_notebooks.append(nb["metadata"]["name"])

    return mounted_notebooks


def get_notebook_pvcs(nb):
    """
    Return a list of PVC names that the given notebook is using.

    If it doesn't use any, then an empty list will be returned.
    """
    pvcs = []
    if not nb["spec"]["template"]["spec"]["volumes"]:
        return []

    vols = nb["spec"]["template"]["spec"]["volumes"]
    for vol in vols:
        # Check if the volume is a pvc
        if not vol.get("persistentVolumeClaim"):
            continue
        pvcs.append(vol["persistentVolumeClaim"]["claimName"])

    return pvcs


def get_containers_using_pvc(pvc, containers):
    """Return a list of custom containers that are using the given PVC."""
    mounted_containers = []

    for container in containers:
        pvcs = get_container_pvcs(container)
        if pvc in pvcs:
            mounted_containers.append(container.metadata.name)

    return mounted_containers


def get_container_pvcs(container):
    """
    Return a list of PVC names that the given container Deployment is using.

    If it doesn't use any, then an empty list will be returned.
    """
    pod_spec = container.spec.template.spec
    if not pod_spec.volumes:
        return []

    pvcs = []
    for vol in pod_spec.volumes:
        if not vol.persistent_volume_claim:
            continue
        pvcs.append(vol.persistent_volume_claim.claim_name)

    return pvcs


def get_pods_using_pvc(pvc, namespace):
    """
    Return a list of Pods that are using the given PVC
    """
    pods = api.list_pods(namespace)
    mounted_pods = []

    for pod in pods.items:
        pvcs = get_pod_pvcs(pod)
        if pvc in pvcs:
            mounted_pods.append(pod)

    return mounted_pods


def get_pod_pvcs(pod):
    """
    Return a list of PVC name that the given Pod
    is using. If it doesn't use any, then an empty list will
    be returned.
    """
    pvcs = []
    if not pod.spec.volumes:
        return []

    vols = pod.spec.volumes
    for vol in vols:
        # Check if the volume is a pvc
        if not vol.persistent_volume_claim:
            continue

        pvcs.append(vol.persistent_volume_claim.claim_name)

    return pvcs
