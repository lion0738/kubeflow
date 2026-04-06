"""CloudShell helper utilities."""

import time
from typing import Optional

from kubeflow.kubeflow.crud_backend import logging
from kubernetes import client

log = logging.getLogger(__name__)


def get_cloudshell_name(pod_name: str) -> str:
    return f"cloudshell-{pod_name}"


def delete_existing_cloudshell(namespace: str, pod_name: str) -> None:
    """Delete any previously created CloudShell for the pod."""
    cloudshell_name = get_cloudshell_name(pod_name)
    custom_api = client.CustomObjectsApi()

    try:
        custom_api.delete_namespaced_custom_object(
            group="cloudshell.cloudtty.io",
            version="v1alpha1",
            namespace=namespace,
            plural="cloudshells",
            name=cloudshell_name,
            body=client.V1DeleteOptions(),
        )

        for _ in range(20):
            try:
                custom_api.get_namespaced_custom_object(
                    group="cloudshell.cloudtty.io",
                    version="v1alpha1",
                    namespace=namespace,
                    plural="cloudshells",
                    name=cloudshell_name,
                )
                time.sleep(0.5)
            except client.exceptions.ApiException as exc:
                if exc.status == 404:
                    log.info("Deleted existing CloudShell %s", cloudshell_name)
                    return
                raise

        log.warning("Timed out waiting for CloudShell deletion: %s", cloudshell_name)

    except client.exceptions.ApiException as exc:
        if exc.status != 404:
            log.error("Failed deleting CloudShell %s: %s", cloudshell_name, exc)
            raise


def create_cloudshell(namespace, target_pod, command):
    """Create the CloudShell custom resource pointing at the pod."""
    pod_name = target_pod.metadata.name
    cloudshell_name = get_cloudshell_name(pod_name)
    body = {
        "apiVersion": "cloudshell.cloudtty.io/v1alpha1",
        "kind": "CloudShell",
        "metadata": {
            "name": cloudshell_name,
            "namespace": namespace,
            "ownerReferences": [
                {
                "apiVersion": "v1",
                "kind": "Pod",
                "name": pod_name,
                "uid": target_pod.metadata.uid,
                "controller": False,
                "blockOwnerDeletion": False
                }
            ],
        },
        "spec": {
            "exposureMode": "ClusterIP",
            "commandAction": f"kubectl exec -n {namespace} -it "
                             f"{pod_name} -- {command}"
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
        log.info("Created CloudShell %s for pod %s", cloudshell_name, pod_name)
        return result
    except client.rest.ApiException as exc:
        if exc.status == 409:
            log.info("CloudShell %s already exists.", cloudshell_name)
        else:
            log.error("Error creating CloudShell %s for pod %s: %s", cloudshell_name, pod_name,
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
