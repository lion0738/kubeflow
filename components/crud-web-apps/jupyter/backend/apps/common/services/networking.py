"""Helpers for exposing Notebook pods through Kubernetes networking objects."""

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

from kubeflow.kubeflow.crud_backend import api, logging
from kubernetes import client

log = logging.getLogger(__name__)


@dataclass
class ServiceHandle:
    """Lightweight reference to a Service that may expose a NodePort."""

    name: str
    node_port: Optional[int] = None


def create_service(namespace: str,
                   pod_name: str,
                   selector: Dict[str, str],
                   owner_references: Iterable,
                   port: int,
                   service_type: str) -> Optional[ServiceHandle]:
    """Create a Service and AuthorizationPolicy to expose a pod port."""
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

    try:
        api.create_service(namespace=namespace, body=service)
        log.info("Created %s service %s", service_type, service_name)
    except client.rest.ApiException as exc:
        if exc.status != 409:
            log.error("Failed creating %s service: %s", service_type, exc)
            return None
        log.info("%s service %s already exists.", service_type, service_name)

    _create_authorization_policy(namespace, service_type, pod_name,
                                 owner_references, selector, port)

    node_port = None
    if service_type == "NodePort":
        created_service = api.get_service(namespace=namespace,
                                          service_name=service_name)
        for svc_port in created_service.spec.ports:
            if svc_port.node_port:
                node_port = svc_port.node_port
                break

        if node_port is None:
            log.error("NodePort not assigned for %s", service_name)

    return ServiceHandle(name=service_name, node_port=node_port)


def _create_authorization_policy(namespace: str,
                                 service_type: str,
                                 pod_name: str,
                                 owner_references: Iterable,
                                 selector: Dict[str, str],
                                 port: int) -> None:
    policy_name = f"allow-{service_type}-{pod_name}-{port}".lower()
    body = {
        "apiVersion": "security.istio.io/v1beta1",
        "kind": "AuthorizationPolicy",
        "metadata": {
            "name": policy_name,
            "namespace": namespace,
            "ownerReferences": owner_references
        },
        "spec": {
            "selector": {"matchLabels": selector},
            "action": "ALLOW",
            "rules": [{
                "to": [{
                    "operation": {"ports": [str(port)]}
                }]
            }]
        }
    }

    try:
        client.CustomObjectsApi().create_namespaced_custom_object(
            group="security.istio.io",
            version="v1beta1",
            namespace=namespace,
            plural="authorizationpolicies",
            body=body,
        )
        log.info("Created AuthorizationPolicy %s", policy_name)
    except client.rest.ApiException as exc:
        if exc.status != 409:
            log.error("Error creating AuthorizationPolicy %s: %s",
                      policy_name, exc)


def create_virtual_service(namespace: str,
                           service_name: str,
                           owner_references: Iterable,
                           address: str,
                           port: int) -> Optional[str]:
    """Expose a Service through the Istio gateway."""
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
                "match": [{"uri": {"prefix": address}}],
                "rewrite": {"uri": "/"},
                "route": [{
                    "destination": {"host": service_host,
                                    "port": {"number": port}}
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
            body=body,
        )
        log.info("Created VirtualService %s", vs_name)
        return vs_name
    except client.rest.ApiException as exc:
        if exc.status == 409:
            log.info("VirtualService %s already exists.", vs_name)
        else:
            log.error("Error creating VirtualService %s: %s", vs_name, exc)
        return None


def get_node_internal_ip(node_name: str) -> Optional[str]:
    """Return the InternalIP for a node."""
    node = api.get_node(node_name)
    for address in node.status.addresses:
        if address.type == "InternalIP":
            return address.address

    return None
