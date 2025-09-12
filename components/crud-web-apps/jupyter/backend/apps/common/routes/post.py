"""POST request handlers."""

import shlex
import string
import subprocess
import time
import threading

from . import bp
from .. import form, utils, volumes
from flask import request
from kubeflow.kubeflow.crud_backend import api, authn
from kubernetes import client

def create_service(namespace, pod_name, selector, owner_references, port, service_type):
    # 서비스 정의
    service_name = f"{service_type}-service-{pod_name}-{port}".lower()
    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=service_name,
            owner_references=owner_references
        ),
        spec=client.V1ServiceSpec(
            selector=selector,
            ports=[client.V1ServicePort(
                protocol="TCP",
                port=port,
                target_port=port,
            )],
            type=service_type,
        ),
    )

    # 서비스 생성 요청
    try:
        api.create_service(namespace=namespace, body=service)
    except client.rest.ApiException as e:
        print(f"{service_type} Service already exists: {e}")

    # AuthorizationPolicy 생성
    policy_name = f"allow-{service_type}-{pod_name}-{port}".lower()

    auth_policy = {
        "apiVersion": "security.istio.io/v1beta1",
        "kind": "AuthorizationPolicy",
        "metadata": {
            "name": policy_name,
            "namespace": namespace,
            "ownerReferences": owner_references
        },
        "spec": {
            "selector": {
                "matchLabels": selector
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

    if service_type == "NodePort":
        # 서비스 생성 후, NodePort를 확인
        created_service = api.get_service(namespace=namespace, service_name=service_name)
        node_port = None

        # 생성된 서비스의 포트들 중에서 NodePort를 찾음
        for port in created_service.spec.ports:
            if port.node_port:
                node_port = port.node_port
                break

        if node_port:
            print(f"NodePort service created for {pod_name} on port {node_port}")
            return node_port
        else:
            print("Error: NodePort not assigned.")

    return None

def create_virtual_service(namespace, service_name, owner_references, address, port):
    vs_name = f"cloudshell-virtualservice-{service_name}".lower()
    service_host = f"{service_name}.{namespace}.svc.cluster.local"

    body = {
        "apiVersion": "networking.istio.io/v1beta1",
        "kind": "VirtualService",
        "metadata": {
            "name": vs_name,
            "namespace": namespace,
            "ownerReferences": owner_references
        },
        "spec": {
            "hosts": ["*"],
            "gateways": ["kubeflow/kubeflow-gateway"],
            "http": [{
                "match": [{
                    "uri": {
                        "prefix": address
                    }
                }],
                "rewrite": {
                    "uri": "/"
                },
                "route": [{
                    "destination": {
                        "host": service_host,
                        "port": {
                            "number": port
                        }
                    }
                }]
            }]
        }
    }

    try:
        client.CustomObjectsApi().create_namespaced_custom_object(
            group="networking.istio.io",
            version="v1beta1",
            namespace=namespace,
            plural="virtualservices",
            body=body
        )
        print(f"VirtualService '{vs_name}' created.")
    except client.rest.ApiException as e:
        if e.status == 409:
            print(f"VirtualService '{vs_name}' already exists.")
        else:
            print(f"Error creating VirtualService: {e}")

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

    pod_name = pod.metadata.name
    selector = {"notebook-name": notebook_name}
    owner_references = pod.metadata.owner_references
    port = create_service(namespace, pod_name, selector, owner_references, 22, "NodePort")
    if port is None:
        return api.failed_response("SSH service creation failed.", 500)

    return api.success_response("sshinfo", [address, port, username, private_key])

def create_cloudshell(namespace, target_pod, command):
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
            "commandAction": f"kubectl exec -n {namespace} -it {container_name} -- {command}"
        }
    }

    try:
        return client.CustomObjectsApi().create_namespaced_custom_object(
            group="cloudshell.cloudtty.io",
            version="v1alpha1",
            namespace=namespace,
            plural="cloudshells",
            body=body
        )
    except client.rest.ApiException as e:
        if e.status == 409:
            print(f"CloudShell for {container_name} already exists.")
        else:
            print(f"Error creating CloudShell: {e}")

def delete_previous_cloudshell(namespace, pod):
    cloudshell_name = f"cloudshell-{pod.metadata.name}"
    custom_api = client.CustomObjectsApi()

    try:
        custom_api.get_namespaced_custom_object(
            group="cloudshell.cloudtty.io",
            version="v1alpha1",
            namespace=namespace,
            plural="cloudshells",
            name=cloudshell_name
        )

        custom_api.delete_namespaced_custom_object(
            group="cloudshell.cloudtty.io",
            version="v1alpha1",
            namespace=namespace,
            plural="cloudshells",
            name=cloudshell_name,
            body=client.V1DeleteOptions()
        )
        time.sleep(2)
    except client.exceptions.ApiException as e:
        if e.status != 404:
            raise

@bp.route("/api/namespaces/<namespace>/containers/<container_name>/shell", methods=["POST"])
def ssh_container(container_name, namespace):
    command = request.args.get("command", type=str)
    label_selector = "notebook-name=" + container_name
    # There should be only one Pod for each Notebook,
    # so we expect items to have length = 1
    pods = api.list_pods(namespace=namespace, label_selector=label_selector)
    if pods.items:
        pod = pods.items[0]

    delete_previous_cloudshell(namespace, pod)
    cloudshell = create_cloudshell(namespace, pod, command)
    if cloudshell is not None:
        cloudshell_name = cloudshell["metadata"]["name"]
        owner_references = [{
            "apiVersion": cloudshell["apiVersion"],
            "kind": cloudshell["kind"],
            "name": cloudshell_name,
            "uid": cloudshell["metadata"]["uid"],
        }]

        target_service_name = None
        max_retries = 30
        for _ in range(max_retries):
            full_cloudshell = client.CustomObjectsApi().get_namespaced_custom_object(
                group="cloudshell.cloudtty.io",
                version="v1alpha1",
                namespace=namespace,
                plural="cloudshells",
                name=cloudshell_name
            )

            labels = full_cloudshell.get("metadata", {}).get("labels", {})
            target_service_name = labels.get("cloudshell.cloudtty.io/pod-name")

            if target_service_name:
                break
            time.sleep(1)
        else:
            return api.failed_response("Timed out waiting for CloudShell pod-name label", 500)

        address = f"/cloudtty/{namespace}/{container_name}/"
        create_virtual_service(namespace, target_service_name, owner_references, address, 7681)

    return api.success_response()

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

    pod_name = pod.metadata.name
    selector = {"notebook-name": notebook_name}
    owner_references = pod.metadata.owner_references
    nodeport = create_service(namespace, pod_name, selector, owner_references, port, "NodePort")
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
    # Environment variables supplied by the user
    envs = body.get("envs", [])

    # resources
    resources = client.V1ResourceRequirements(
        requests=resources_dict,
        limits=resources_dict
    )

    defaults = utils.load_spawner_ui_config()

    # Notebook volumes
    api_volumes = []
    api_volumes.extend(form.get_form_value(body, defaults, "datavols", "dataVolumes"))

    # ensure that all objects can be created
    for api_volume in api_volumes:
        pvc = volumes.get_new_pvc(api_volume)
        if pvc is None:
            continue

        api.create_pvc(pvc, namespace, dry_run=True)

    # create the new PVCs and set the Notebook volumes and mounts
    new_volumes = []
    new_volume_mounts = []
    for api_volume in api_volumes:
        pvc = volumes.get_new_pvc(api_volume)
        if pvc is not None:
            pvc = api.create_pvc(pvc, namespace)

        v1_volume = volumes.get_pod_volume(api_volume, pvc)
        mount = volumes.get_container_mount(api_volume, v1_volume["name"])

        new_volumes.append(v1_volume)
        new_volume_mounts.append(mount)

    command_list = shlex.split(command)

    # Convert environment variables into V1EnvVar list
    env_vars = []
    for env in envs:
        env_name = env.get("name")
        env_value = env.get("value")
        if env_name:
            env_vars.append(client.V1EnvVar(name=env_name, value=env_value))

    container = client.V1Container(
        name=name,
        image=image,
        command=command_list,
        ports=[client.V1ContainerPort(container_port=p) for p in ports],
        resources=resources,
        env=env_vars or None,
        volume_mounts=new_volume_mounts or None
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"app": name, "container-type": "custom-container", "notebook-name": name}),
        spec=client.V1PodSpec(
            scheduler_name="reservation-scheduler",
            containers=[container],
            restart_policy="Always",
            volumes=new_volumes or None
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
