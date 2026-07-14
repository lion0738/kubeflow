"""Compatibility helpers for custom-container workloads."""

from typing import List, Optional

from kubeflow.kubeflow.crud_backend import api
from kubernetes import client


def list_container_workloads(namespace: str) -> List:
    """List StatefulSets and legacy Deployments, preferring StatefulSets."""
    statefulsets = [
        item for item in api.list_statefulsets(namespace=namespace).items
        if _is_custom_container(item)
    ]
    statefulset_names = {item.metadata.name for item in statefulsets}
    deployments = [
        item for item in api.list_deployments(namespace=namespace).items
        if _is_custom_container(item)
        and item.metadata.name not in statefulset_names
    ]
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
    if workload.kind == "StatefulSet":
        return api.patch_statefulset(name=name, namespace=namespace, body=body)
    return api.patch_deployment(name=name, namespace=namespace, body=body)


def delete_container_workload(namespace: str, name: str, workload=None):
    workload = workload or get_container_workload(namespace, name)
    if workload is None:
        return None
    if workload.kind == "StatefulSet":
        return api.delete_statefulset(name=name, namespace=namespace)
    return api.delete_deployment(name=name, namespace=namespace)


def owner_reference(workload):
    return client.V1OwnerReference(
        api_version=workload.api_version or "apps/v1",
        kind=workload.kind or "Deployment",
        name=workload.metadata.name,
        uid=workload.metadata.uid,
    )


def _is_custom_container(workload) -> bool:
    labels = workload.metadata.labels or {}
    return labels.get("container-type") == "custom-container"

