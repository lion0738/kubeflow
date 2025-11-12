"""POST request handlers."""

from flask import request
from kubeflow.kubeflow.crud_backend import api

from ..services import cloudshell, containers, networking
from . import bp


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
    pod = _get_notebook_pod(namespace, container_name)
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


@bp.route("/api/namespaces/<namespace>/containers", methods=["POST"])
def create_container(namespace):
    body = request.get_json()

    try:
        result = containers.create_custom_container(namespace, body)
        return api.success_response("container", result.to_dict())
    except Exception as exc:  # pylint: disable=broad-except
        return api.failed_response(f"Container creation failed: {exc}", 500)


def _get_notebook_pod(namespace: str, notebook_name: str):
    label_selector = "notebook-name=" + notebook_name
    pods = api.list_pods(namespace=namespace, label_selector=label_selector)
    if pods.items:
        return pods.items[0]
    return None
