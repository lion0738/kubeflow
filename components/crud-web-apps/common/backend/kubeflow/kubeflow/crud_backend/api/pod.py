from kubernetes import client
from kubernetes.stream import stream

from .. import authz
from . import v1_core


def list_pods(namespace, auth=True, label_selector=None):
    if auth:
        authz.ensure_authorized("list", "", "v1", "pods", namespace)

    return v1_core.list_namespaced_pod(
        namespace=namespace,
        label_selector=label_selector)


def get_pod_logs(namespace, pod, container, auth=True):
    if auth:
        authz.ensure_authorized("get", "", "v1", "pods", namespace, "log")

    return v1_core.read_namespaced_pod_log(
        namespace=namespace, name=pod, container=container
    )


def exec_pod_command(namespace, pod, container, command, auth=True):
    if auth:
        authz.ensure_authorized("create", "", "v1", "pods/exec", namespace)

    try:
        exec_response = stream(
            v1_core.connect_get_namespaced_pod_exec,
            name=pod,
            namespace=namespace,
            container=container,
            command=command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False
        )
        return exec_response.strip()
    except client.exceptions.ApiException as e:
        print(f"Error executing command in pod: {e}")
        return None
