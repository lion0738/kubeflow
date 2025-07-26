"""POST request handlers."""

import shlex
import string
import subprocess
import threading

from . import bp
from flask import request
from kubeflow.kubeflow.crud_backend import api, authn
from kubernetes import client


def create_nodeport_service(pod, namespace, port):
    # NodePort 서비스 정의 (nodePort를 명시하지 않음, Kubernetes가 자동 할당)
    service_name = f"nodeport-service-{pod.metadata.name}-{port}"
    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=service_name,
            owner_references=pod.metadata.owner_references
        ),
        spec=client.V1ServiceSpec(
            selector=pod.metadata.labels,
            ports=[client.V1ServicePort(
                protocol="TCP",
                port=port,
                target_port=port,
            )],
            type="NodePort",
        ),
    )

    # 서비스 생성 요청
    try:
        api.create_service(namespace=namespace, body=service)
    except client.rest.ApiException as e:
        print(f"NodePort Service already exists: {e}")

    # AuthorizationPolicy 생성
    policy_name = f"allow-nodeport-{pod.metadata.name}-{port}"
    labels_selector = pod.metadata.labels

    auth_policy = {
        "apiVersion": "security.istio.io/v1beta1",
        "kind": "AuthorizationPolicy",
        "metadata": {
            "name": policy_name,
            "namespace": namespace,
            "ownerReferences": pod.metadata.owner_references
        },
        "spec": {
            "selector": {
                "matchLabels": labels_selector
            },
            "action": "ALLOW",
            "rules": [
                {
                    "to": [
                        {
                            "operation": {
                                "ports": [str(port)]
                            }
                        }
                    ]
                }
            ]
        }
    }

    # AuthorizationPolicy 생성 요청
    try:
        client.CustomObjectsApi().create_namespaced_custom_object(
            "security.istio.io",
            "v1beta1",
            namespace,
            "authorizationpolicies",
            auth_policy
        )
        print(f"AuthorizationPolicy '{policy_name}' created.")
    except Exception as e:
        print(f"Error creating AuthorizationPolicy: {e}")

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
    private_key = api.exec_pod_command(namespace=namespace, pod=pod.metadata.name, container=notebook_name, command=["cat", "/home/jovyan/.ssh/id_rsa"])
    if private_key is None or "No such file" in private_key:
        return api.failed_response("Failed to get password for SSH. Please use an SSH-ready pod.", 500)

    port = create_nodeport_service(pod, namespace, 22)
    if port is None:
        return api.failed_response("SSH service creation failed.", 500)

    return api.success_response("sshinfo", [address, port, username, private_key])


@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/portforward", methods=["POST"])
def port_forward_notebook(notebook_name, namespace):
    port = request.args.get("port", type=int)
    label_selector = "notebook-name=" + notebook_name
    # There should be only one Pod for each Notebook,
    # so we expect items to have length = 1
    pods = api.list_pods(namespace=namespace, label_selector=label_selector)
    if pods.items:
        pod = pods.items[0]

    address = get_node_address(pod.spec.node_name)
    nodeport = create_nodeport_service(pod, namespace, port)
    if nodeport is None:
        return api.failed_response("Service creation failed.", 500)

    return api.success_response("portinfo", [address, port, nodeport])

@bp.route("/api/namespaces/<namespace>/containers", methods=["POST"])
def create_container(namespace):
    body = request.get_json()
    name = body.get("name")
    image = body.get("image")
    command = body.get("command", "")
    ports = body.get("ports", [])
    resources_dict = body.get("resources", {})
    volumes_input = body.get("volumes", [])

    # resources
    gpu = resources_dict.get("nvidia.com/gpu")
    resources = client.V1ResourceRequirements(
        requests=resources_dict,
        limits={"nvidia.com/gpu": gpu} if gpu else None
    )

    # volumes
    volume_mounts = []
    volumes = []

    for v in volumes_input:
        volume_mounts.append(client.V1VolumeMount(
            name=v["name"],
            mount_path=v["mountPath"]
        ))
        volumes.append(client.V1Volume(
            name=v["name"],
            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                claim_name=v["claimName"]
            )
        ))

    command_list = shlex.split(command)

    container = client.V1Container(
        name=name,
        image=image,
        command=command_list,
        ports=[client.V1ContainerPort(container_port=p) for p in ports],
        resources=resources,
        volume_mounts=volume_mounts or None
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"app": name, "container-type": "custom-container", "notebook-name": name}),
        spec=client.V1PodSpec(
            schedulerName="reservation-scheduler",
            containers=[container],
            restart_policy="Always",
            volumes=volumes or None
        )
    )

    spec = client.V1DeploymentSpec(
        replicas=1,
        selector=client.V1LabelSelector(match_labels={"app": name}),
        template=template
    )

    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(
            name=name,
            labels={"container-type": "custom-container", "app": name},
            annotations={"notebooks.kubeflow.org/creator": authn.get_username()}),
        spec=spec
    )

    try:
        result = api.create_deployment(namespace=namespace, body=deployment)
        return api.success_response("container", result.to_dict())
    except Exception as e:
        return api.failed_response(f"Container creation failed: {e}", 500)
