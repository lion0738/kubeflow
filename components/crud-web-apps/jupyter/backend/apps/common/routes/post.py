"""POST request handlers."""

from flask import request
from kubeflow.kubeflow.crud_backend import api
from kubernetes import client

from ..services import cloudshell, containers, networking
from . import bp

NODE_PORT_MIN = 30000
NODE_PORT_MAX = 32767


@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/ssh",
          methods=["POST"])
def ssh_notebook(notebook_name, namespace):
    pod = _get_notebook_pod(namespace, notebook_name)
    if pod is None:
        return api.failed_response("No pod detected.", 404)

    address = networking.get_node_internal_ip(pod.spec.node_name)
    username = "jovyan"
    private_key = api.exec_pod_command(
        namespace=namespace,
        pod=pod.metadata.name,
        container=notebook_name,
        command=["cat", "/home/jovyan/.ssh/id_rsa"],
    )
    if private_key is None or "No such file" in private_key:
        return api.failed_response(
            "Failed to get password for SSH. Please use an SSH-ready pod.", 500
        )

    selector = {"notebook-name": notebook_name}
    service = networking.create_service(
        namespace=namespace,
        pod_name=pod.metadata.name,
        selector=selector,
        owner_references=pod.metadata.owner_references,
        port=22,
        service_type="NodePort",
    )
    if service is None or service.node_port is None:
        return api.failed_response("SSH service creation failed.", 500)

    return api.success_response(
        "sshinfo", [address, service.node_port, username, private_key]
    )


@bp.route("/api/namespaces/<namespace>/containers/<container_name>/shell",
          methods=["POST"])
def ssh_container(container_name, namespace):
    command = request.args.get("command", type=str)
    pod_name = request.args.get("podName", type=str)
    pod = _get_notebook_pod(namespace, container_name, pod_name)
    if pod is None:
        return api.failed_response("No pod detected.", 404)

    cloudshell.delete_existing_cloudshell(namespace, pod.metadata.name)
    shell = cloudshell.create_cloudshell(namespace, pod, command)
    if shell is None:
        return api.failed_response("Failed to create CloudShell.", 500)

    cloudshell_name = shell["metadata"]["name"]
    owner_references = [{
        "apiVersion": shell["apiVersion"],
        "kind": shell["kind"],
        "name": cloudshell_name,
        "uid": shell["metadata"]["uid"],
    }]

    target_service_name = cloudshell.wait_for_target_service(
        namespace, cloudshell_name)
    if target_service_name is None:
        return api.failed_response("Timed out waiting for CloudShell pod-name label", 500)

    if pod_name:
        address = f"/cloudtty/{namespace}/{container_name}/{pod.metadata.name}/"
    else:
        address = f"/cloudtty/{namespace}/{container_name}/"
    networking.create_virtual_service(namespace, target_service_name,
                                      owner_references, address, 7681)

    return api.success_response()


@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/portforward",
          methods=["POST"])
def port_forward_notebook(notebook_name, namespace):
    port = request.args.get("port", type=int)
    pod = _get_notebook_pod(namespace, notebook_name)
    if pod is None:
        return api.failed_response("No pod detected.", 404)

    address = networking.get_node_internal_ip(pod.spec.node_name)
    selector = {"notebook-name": notebook_name}
    service = networking.create_service(
        namespace=namespace,
        pod_name=pod.metadata.name,
        selector=selector,
        owner_references=pod.metadata.owner_references,
        port=port,
        service_type="NodePort",
    )
    if service is None or service.node_port is None:
        return api.failed_response("Service creation failed.", 500)

    return api.success_response("portinfo", [address, port, service.node_port])


@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/ports",
          methods=["POST"])
def create_notebook_port(notebook_name, namespace):
    body = request.get_json() or {}
    port, node_port = _get_port_request_values(body)
    if port is None:
        return api.failed_response("Port must be an integer from 1 to 65535.", 400)
    if node_port is False:
        return api.failed_response(
            "NodePort must be an integer from 30000 to 32767.",
            400,
        )

    pod = _get_notebook_pod(namespace, notebook_name)
    if pod is None:
        return api.failed_response("No pod detected.", 404)

    selector = {"notebook-name": notebook_name}
    service = networking.create_service(
        namespace=namespace,
        pod_name=pod.metadata.name,
        selector=selector,
        owner_references=pod.metadata.owner_references,
        port=port,
        service_type="NodePort",
        node_port=node_port,
    )
    if service is None or service.node_port is None:
        return api.failed_response("Service creation failed.", 500)

    ports = networking.list_node_port_services(namespace, selector)
    created_port = next(
        (item for item in ports if item["name"] == service.name),
        None,
    )
    return api.success_response("port", created_port)


@bp.route("/api/namespaces/<namespace>/containers/<name>/ports",
          methods=["POST"])
def create_container_port(namespace, name):
    body = request.get_json() or {}
    port, node_port = _get_port_request_values(body)
    if port is None:
        return api.failed_response("Port must be an integer from 1 to 65535.", 400)
    if node_port is False:
        return api.failed_response(
            "NodePort must be an integer from 30000 to 32767.",
            400,
        )

    deployment = _get_container_deployment(namespace, name)
    if deployment is None:
        return api.failed_response("No container detected.", 404)

    pod = _get_container_pod(namespace, name)
    if pod is None:
        return api.failed_response("No pod detected.", 404)

    selector = {"notebook-name": name}
    service = networking.create_service(
        namespace=namespace,
        pod_name=pod.metadata.name,
        selector=selector,
        owner_references=[_owner_reference_from_deployment(deployment)],
        port=port,
        service_type="NodePort",
        node_port=node_port,
    )
    if service is None or service.node_port is None:
        return api.failed_response("Service creation failed.", 500)

    ports = networking.list_node_port_services(namespace, selector)
    created_port = next(
        (item for item in ports if item["name"] == service.name),
        None,
    )
    return api.success_response("port", created_port)


@bp.route("/api/namespaces/<namespace>/containers", methods=["POST"])
def create_container(namespace):
    body = request.get_json()

    try:
        result = containers.create_custom_container(namespace, body)
        return api.success_response("container", result.to_dict())
    except Exception as exc:  # pylint: disable=broad-except
        return api.failed_response(f"Container creation failed: {exc}", 500)


def _get_notebook_pod(namespace: str, notebook_name: str, pod_name: str = None):
    label_selector = "notebook-name=" + notebook_name
    pods = api.list_pods(namespace=namespace, label_selector=label_selector)
    if pod_name:
        for pod in pods.items:
            if pod.metadata.name == pod_name:
                return pod
        return None
    if pods.items:
        return pods.items[0]
    return None


def _get_container_deployment(namespace: str, name: str):
    deployments = api.list_deployments(namespace=namespace).items
    return next((dep for dep in deployments if dep.metadata.name == name), None)


def _get_container_pod(namespace: str, name: str):
    pods = api.list_pods(namespace=namespace, label_selector=f"notebook-name={name}")
    return pods.items[0] if pods.items else None


def _owner_reference_from_deployment(deployment):
    return client.V1OwnerReference(
        api_version=deployment.api_version or "apps/v1",
        kind=deployment.kind or "Deployment",
        name=deployment.metadata.name,
        uid=deployment.metadata.uid,
    )


def _get_port_request_values(body):
    port = _valid_port(body.get("port"))
    if port is None:
        return None, None

    node_port_value = body.get("nodePort")
    node_port = None
    if node_port_value not in (None, ""):
        node_port = _valid_node_port(node_port_value)
        if node_port is None:
            return port, False

    return port, node_port


def _valid_port(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None

    if port < 1 or port > 65535:
        return None

    return port


def _valid_node_port(value):
    port = _valid_port(value)
    if port is None:
        return None

    if port < NODE_PORT_MIN or port > NODE_PORT_MAX:
        return None

    return port
