"""POST request handlers."""

import re

from flask import request
from kubeflow.kubeflow.crud_backend import api
from kubernetes import client

from .. import utils
from ..services import cloudshell, containers, networking
from . import bp

NODE_PORT_MIN = 30000
NODE_PORT_MAX = 32767
DOMAIN_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


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


@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/ports",
          methods=["POST"])
def create_notebook_port(notebook_name, namespace):
    body = request.get_json() or {}
    access_type, domain, per_replica, error = _get_access_values(body, False)
    if error:
        return api.failed_response(error, 400)
    port, node_port, protocol = _get_port_request_values(body)
    if port is None:
        return api.failed_response("Port must be an integer from 1 to 65535.", 400)
    if node_port is False:
        return api.failed_response(
            "NodePort must be an integer from 30000 to 32767.",
            400,
        )
    if protocol is None:
        return api.failed_response("Protocol must be TCP or UDP.", 400)

    pod = _get_notebook_pod(namespace, notebook_name)
    if pod is None:
        return api.failed_response("No pod detected.", 404)

    selector = {"notebook-name": notebook_name}
    if access_type == "Gateway":
        try:
            created_port = networking.create_gateway_exposure(
                namespace=namespace,
                workload_name=notebook_name,
                selector=selector,
                owner_references=pod.metadata.owner_references,
                port=port,
                domain=domain,
                per_replica=per_replica,
                replicas=1,
                **_gateway_config(),
            )
            return api.success_response("port", created_port)
        except networking.DomainConflictError as exc:
            return api.failed_response(str(exc), 409)
        except Exception as exc:  # pylint: disable=broad-except
            return api.failed_response(f"Gateway creation failed: {exc}", 500)

    service = networking.create_service(
        namespace=namespace,
        pod_name=pod.metadata.name,
        selector=selector,
        owner_references=pod.metadata.owner_references,
        port=port,
        service_type="NodePort",
        node_port=node_port,
        protocol=protocol,
    )
    if service is None or service.node_port is None:
        return api.failed_response("Service creation failed.", 500)

    ports = networking.list_port_exposures(namespace, selector)
    created_port = next(
        (item for item in ports if item["name"] == service.name),
        None,
    )
    return api.success_response("port", created_port)


@bp.route("/api/namespaces/<namespace>/containers/<name>/ports",
          methods=["POST"])
def create_container_port(namespace, name):
    body = request.get_json() or {}
    access_type, domain, per_replica, error = _get_access_values(body, True)
    if error:
        return api.failed_response(error, 400)
    port, node_port, protocol = _get_port_request_values(body)
    if port is None:
        return api.failed_response("Port must be an integer from 1 to 65535.", 400)
    if node_port is False:
        return api.failed_response(
            "NodePort must be an integer from 30000 to 32767.",
            400,
        )
    if protocol is None:
        return api.failed_response("Protocol must be TCP or UDP.", 400)

    deployment = _get_container_deployment(namespace, name)
    if deployment is None:
        return api.failed_response("No container detected.", 404)

    selector = {"notebook-name": name}
    if access_type == "Gateway":
        try:
            created_port = networking.create_gateway_exposure(
                namespace=namespace,
                workload_name=name,
                selector=selector,
                owner_references=[_owner_reference_from_deployment(deployment)],
                port=port,
                domain=domain,
                per_replica=per_replica,
                replicas=_desired_replicas(deployment),
                **_gateway_config(),
            )
            return api.success_response("port", created_port)
        except networking.DomainConflictError as exc:
            return api.failed_response(str(exc), 409)
        except Exception as exc:  # pylint: disable=broad-except
            return api.failed_response(f"Gateway creation failed: {exc}", 500)

    pod = _get_container_pod(namespace, name)
    if pod is None:
        return api.failed_response("No pod detected.", 404)
    service = networking.create_service(
        namespace=namespace,
        pod_name=pod.metadata.name,
        selector=selector,
        owner_references=[_owner_reference_from_deployment(deployment)],
        port=port,
        service_type="NodePort",
        node_port=node_port,
        protocol=protocol,
    )
    if service is None or service.node_port is None:
        return api.failed_response("Service creation failed.", 500)

    ports = networking.list_port_exposures(namespace, selector)
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
        return None, None, None

    node_port_value = body.get("nodePort")
    node_port = None
    if node_port_value not in (None, ""):
        node_port = _valid_node_port(node_port_value)
        if node_port is None:
            return port, False, None

    protocol = _valid_protocol(body.get("protocol", "TCP"))
    return port, node_port, protocol


def _get_access_values(body, allow_per_replica):
    access_type = body.get("accessType", "NodePort")
    if access_type not in ("NodePort", "Gateway"):
        return None, None, False, "Access type must be NodePort or Gateway."

    if access_type == "NodePort":
        return access_type, None, False, None

    if body.get("nodePort") not in (None, ""):
        return None, None, False, "Gateway access does not accept a NodePort."
    if str(body.get("protocol", "TCP")).upper() != "TCP":
        return None, None, False, "Gateway access only supports TCP/HTTP services."
    domain = str(body.get("domain", "")).strip()
    if not DOMAIN_PATTERN.fullmatch(domain):
        return None, None, False, "Domain must be a lowercase DNS label."
    per_replica_value = body.get("perReplica", False)
    if not isinstance(per_replica_value, bool):
        return None, None, False, "perReplica must be a boolean."
    per_replica = per_replica_value if allow_per_replica else False
    return access_type, domain, per_replica, None


def _gateway_config():
    config = utils.load_spawner_ui_config().get("externalAccess", {})
    return {
        "domain_suffix": config.get(
            "domainSuffix", "knu-kubeflow.duckdns.org"
        ),
        "gateway": config.get("gateway", "kubeflow/custom-gateway"),
    }


def _desired_replicas(workload):
    annotations = workload.metadata.annotations or {}
    value = annotations.get("containers.kubeflow.org/last-replicas")
    try:
        return max(1, int(value if value is not None else workload.spec.replicas))
    except (TypeError, ValueError):
        return 1


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


def _valid_protocol(value):
    protocol = str(value).upper()
    if protocol not in ("TCP", "UDP"):
        return None

    return protocol
