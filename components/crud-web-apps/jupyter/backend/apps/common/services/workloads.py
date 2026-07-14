"""Compatibility helpers for custom-container workloads."""

from typing import List, Optional

from kubeflow.kubeflow.crud_backend import api
from kubernetes import client


def list_container_workloads(namespace: str) -> List:
    """List StatefulSets and legacy Deployments, preferring StatefulSets."""
    statefulsets = []
    for item in api.list_statefulsets(namespace=namespace).items:
        if not _is_custom_container(item):
            continue
        _set_workload_kind(item, "StatefulSet")
        statefulsets.append(item)
    statefulset_names = {item.metadata.name for item in statefulsets}
    deployments = []
    for item in api.list_deployments(namespace=namespace).items:
        if not _is_custom_container(item):
            continue
        if item.metadata.name in statefulset_names:
            continue
        _set_workload_kind(item, "Deployment")
        deployments.append(item)
    return statefulsets + deployments


def get_container_workload(namespace: str, name: str) -> Optional[object]:
    return next(
        (item for item in list_container_workloads(namespace)
         if item.metadata.name == name),
        None,
    )


def patch_container_workload(namespace: str, name: str, body, workload=None):
    workload = workload or get_container_workload(namespace, name)
    if workload is None:
        return None
    if workload_kind(workload) == "StatefulSet":
        return api.patch_statefulset(name=name, namespace=namespace, body=body)
    return api.patch_deployment(name=name, namespace=namespace, body=body)


def delete_container_workload(namespace: str, name: str, workload=None):
    workload = workload or get_container_workload(namespace, name)
    if workload is None:
        return None
    if workload_kind(workload) == "StatefulSet":
        return api.delete_statefulset(name=name, namespace=namespace)
    return api.delete_deployment(name=name, namespace=namespace)


def owner_reference(workload):
    kind = workload_kind(workload)
    return client.V1OwnerReference(
        api_version=workload.api_version or "apps/v1",
        kind=kind,
        name=workload.metadata.name,
        uid=workload.metadata.uid,
    )


def _is_custom_container(workload) -> bool:
    labels = workload.metadata.labels or {}
    return labels.get("container-type") == "custom-container"


def workload_kind(workload) -> str:
    """Return the concrete apps/v1 workload kind for a typed API object."""
    recorded_kind = getattr(workload, "_kubeflow_workload_kind", None)
    if recorded_kind in ("StatefulSet", "Deployment"):
        return recorded_kind
    kind = getattr(workload, "kind", None)
    if kind in ("StatefulSet", "Deployment"):
        return kind
    if isinstance(workload, client.V1StatefulSet):
        return "StatefulSet"
    if isinstance(workload, client.V1Deployment):
        return "Deployment"
    raise ValueError("Unsupported container workload type.")


def _set_workload_kind(workload, kind: str) -> None:
    if getattr(workload, "kind", None) is None:
        try:
            workload.kind = kind
        except (AttributeError, TypeError):
            pass
    try:
        setattr(workload, "_kubeflow_workload_kind", kind)
    except (AttributeError, TypeError):
        pass
