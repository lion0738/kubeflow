"""CloudShell helper utilities."""

import time
from typing import Optional

from kubeflow.kubeflow.crud_backend import logging
from kubernetes import client

log = logging.getLogger(__name__)


def delete_existing_cloudshell(namespace: str, pod_name: str) -> None:
    """Delete any previously created CloudShell for the pod."""
    cloudshell_name = f"cloudshell-{pod_name}"
    custom_api = client.CustomObjectsApi()

    try:
        custom_api.get_namespaced_custom_object(
            group="cloudshell.cloudtty.io",
            version="v1alpha1",
            namespace=namespace,
            plural="cloudshells",
            name=cloudshell_name,
        )
        custom_api.delete_namespaced_custom_object(
            group="cloudshell.cloudtty.io",
            version="v1alpha1",
            namespace=namespace,
            plural="cloudshells",
            name=cloudshell_name,
            body=client.V1DeleteOptions(),
        )
        time.sleep(2)
        log.info("Deleted existing CloudShell %s", cloudshell_name)
    except client.exceptions.ApiException as exc:
        if exc.status != 404:
            log.error("Failed deleting CloudShell %s: %s", cloudshell_name, exc)
            raise


def create_cloudshell(namespace, target_pod, command):
    """Create the CloudShell custom resource pointing at the pod."""
    container_name = target_pod.metadata.name
    body = {
        "apiVersion": "cloudshell.cloudtty.io/v1alpha1",
        "kind": "CloudShell",
        "metadata": {
            "name": f"cloudshell-{container_name}",
            "namespace": namespace,
            "ownerReferences": target_pod.metadata.owner_references
        },
        "spec": {
            "exposureMode": "ClusterIP",
            "commandAction": f"kubectl exec -n {namespace} -it "
                             f"{container_name} -- {command}"
        }
    }

    try:
        result = client.CustomObjectsApi().create_namespaced_custom_object(
            group="cloudshell.cloudtty.io",
            version="v1alpha1",
            namespace=namespace,
            plural="cloudshells",
            body=body
        )
        log.info("Created CloudShell for pod %s", container_name)
        return result
    except client.rest.ApiException as exc:
        if exc.status == 409:
            log.info("CloudShell for %s already exists.", container_name)
        else:
            log.error("Error creating CloudShell for %s: %s", container_name,
                      exc)
        return None


def wait_for_target_service(namespace: str,
                            cloudshell_name: str,
                            max_retries: int = 30,
                            sleep_seconds: int = 1) -> Optional[str]:
    """Poll the CloudShell CR until the backing service label is populated."""
    custom_api = client.CustomObjectsApi()
    for _ in range(max_retries):
        full_cloudshell = custom_api.get_namespaced_custom_object(
            group="cloudshell.cloudtty.io",
            version="v1alpha1",
            namespace=namespace,
            plural="cloudshells",
            name=cloudshell_name
        )
        labels = full_cloudshell.get("metadata", {}).get("labels", {})
        target_service_name = labels.get("cloudshell.cloudtty.io/pod-name")
        if target_service_name:
            return target_service_name
        time.sleep(sleep_seconds)

    log.error("Timed out waiting for CloudShell %s target service label",
              cloudshell_name)
    return None
