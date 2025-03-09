"""POST request handlers."""

import string
import subprocess
import threading

from . import bp
from kubeflow.kubeflow.crud_backend import api
from kubernetes import client


def create_ssh_nodeport_service(pod, namespace):
    # NodePort 서비스 정의 (nodePort를 명시하지 않음, Kubernetes가 자동 할당)
    service_name = f"ssh-service-{pod.metadata.name}"
    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=service_name,
            owner_references=pod.metadata.owner_references
        ),
        spec=client.V1ServiceSpec(
            selector=pod.metadata.labels,
            ports=[client.V1ServicePort(
                protocol="TCP",
                port=22,
                target_port=22,
            )],
            type="NodePort",
        ),
    )

    # 서비스 생성 요청
    try:
        api.create_service(namespace=namespace, body=service)
    except client.rest.ApiException as e:
        print(f"SSH Service already exists: {e}")

    # 서비스 생성 후, NodePort를 확인
    created_service = api.get_service(namespace=namespace, service_name=service_name)
    node_port = None

    # 생성된 서비스의 포트들 중에서 NodePort를 찾음
    for port in created_service.spec.ports:
        if port.node_port:
            node_port = port.node_port
            break

    if node_port:
        print(f"NodePort service created for {pod.metadata.name} on port {node_port}")
        return node_port
    else:
        print("Error: NodePort not assigned.")
        return None

def get_node_address(node_name):
    node = api.get_node(node_name)
    for address in node.status.addresses:
        if address.type == "InternalIP":
            return address.address

    return None

@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/ssh", methods=["POST"])
def ssh_notebook(notebook_name, namespace):
    label_selector = "notebook-name=" + notebook_name
    # There should be only one Pod for each Notebook,
    # so we expect items to have length = 1
    pods = api.list_pods(namespace=namespace, label_selector=label_selector)
    if pods.items:
        pod = pods.items[0]

    address = get_node_address(pod.spec.node_name)

    username = "jovyan"
    password = api.exec_pod_command(namespace=namespace, pod=pod.metadata.name, container=notebook_name, command=["cat", "/etc/ssh/ssh_password"])
    if password is None or "No such file" in password:
        return api.failed_response("Failed to get password for SSH. Please use an SSH-ready pod.", 500)

    port = create_ssh_nodeport_service(pod, namespace)
    if port is None:
        return api.failed_response("SSH service creation failed.", 500)


    return api.success_response("sshinfo", [address, port, username, password])