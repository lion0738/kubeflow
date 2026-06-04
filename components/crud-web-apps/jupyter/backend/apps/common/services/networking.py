"""Helpers for exposing Notebook pods through Kubernetes networking objects."""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

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
                   service_type: str,
                   node_port: Optional[int] = None,
                   protocol: str = "TCP") -> Optional[ServiceHandle]:
    """Create a Service and AuthorizationPolicy to expose a pod port."""
    service_name = f"{service_type}-service-{pod_name}-{port}".lower()
    service_port = client.V1ServicePort(
        protocol=protocol,
        port=port,
        target_port=port,
    )
    if node_port is not None:
        service_port.node_port = node_port

    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=service_name,
            owner_references=owner_references
        ),
        spec=client.V1ServiceSpec(
            selector=selector,
            ports=[service_port],
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


def list_node_port_services(namespace: str,
                            selector: Dict[str, str]) -> List[Dict]:
    """Return NodePort service ports whose service selector matches selector."""
    services = api.list_services(namespace=namespace).items
    ports = []
    for service in services:
        if service.spec.type != "NodePort":
            continue
        if not _selector_matches(service.spec.selector or {}, selector):
            continue
        ports.extend(_serialize_service_ports(service))

    return sorted(ports, key=lambda item: (item["name"], item["port"]))


def patch_node_port_service(namespace: str,
                            service_name: str,
                            port: int,
                            node_port: Optional[int] = None,
                            protocol: str = "TCP",
                            selector: Optional[Dict[str, str]] = None) -> Dict:
    """Patch the first Service port on a NodePort Service."""
    service = api.get_service(namespace=namespace, service_name=service_name)
    if selector and not _selector_matches(service.spec.selector or {}, selector):
        raise ValueError("Service does not belong to the requested workload.")

    old_port = _first_service_port_number(service)
    service_port = {
        "protocol": protocol,
        "port": port,
        "targetPort": port,
    }
    if node_port is not None:
        service_port["nodePort"] = node_port

    body = {
        "spec": {
            "type": "NodePort",
            "ports": [{"$patch": "replace"}, service_port],
        },
    }
    result = api.patch_service(
        namespace=namespace,
        service_name=service_name,
        body=body,
    )

    selector = result.spec.selector or {}
    owner_references = result.metadata.owner_references or []
    pod_name = _pod_name_from_service_name(service_name, old_port)
    if old_port is not None and old_port != port:
        _delete_authorization_policy(namespace, "NodePort", pod_name, old_port)
    _create_authorization_policy(
        namespace,
        "NodePort",
        pod_name,
        owner_references,
        selector,
        port,
    )

    serialized = _serialize_service_ports(result)
    return serialized[0] if serialized else {}


def delete_node_port_service(namespace: str,
                             service_name: str,
                             selector: Optional[Dict[str, str]] = None) -> None:
    """Delete a NodePort Service and its generated AuthorizationPolicies."""
    service = api.get_service(namespace=namespace, service_name=service_name)
    if selector and not _selector_matches(service.spec.selector or {}, selector):
        raise ValueError("Service does not belong to the requested workload.")

    pod_name = _pod_name_from_service_name(
        service_name,
        _first_service_port_number(service),
    )
    for service_port in service.spec.ports or []:
        if service_port.port:
            _delete_authorization_policy(
                namespace,
                "NodePort",
                pod_name,
                service_port.port,
            )

    api.delete_service(namespace=namespace, service_name=service_name)


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


def _delete_authorization_policy(namespace: str,
                                 service_type: str,
                                 pod_name: str,
                                 port: int) -> None:
    policy_name = f"allow-{service_type}-{pod_name}-{port}".lower()
    try:
        client.CustomObjectsApi().delete_namespaced_custom_object(
            group="security.istio.io",
            version="v1beta1",
            namespace=namespace,
            plural="authorizationpolicies",
            name=policy_name,
        )
        log.info("Deleted AuthorizationPolicy %s", policy_name)
    except client.rest.ApiException as exc:
        if exc.status != 404:
            log.error("Error deleting AuthorizationPolicy %s: %s",
                      policy_name, exc)


def _serialize_service_ports(service) -> List[Dict]:
    serialized = []
    for service_port in service.spec.ports or []:
        serialized.append({
            "name": service.metadata.name,
            "port": service_port.port,
            "targetPort": service_port.target_port,
            "nodePort": service_port.node_port,
            "protocol": service_port.protocol,
            "type": service.spec.type,
        })

    return serialized


def _selector_matches(service_selector: Dict[str, str],
                      selector: Dict[str, str]) -> bool:
    return all(service_selector.get(key) == value
               for key, value in selector.items())


def _first_service_port_number(service) -> Optional[int]:
    if not service.spec.ports:
        return None
    return service.spec.ports[0].port


def _pod_name_from_service_name(service_name: str,
                                port: Optional[int] = None) -> str:
    prefix = "nodeport-service-"
    if service_name.lower().startswith(prefix):
        pod_name = service_name[len(prefix):]
        if port is not None and pod_name.endswith(f"-{port}"):
            return pod_name[:-(len(str(port)) + 1)]
        parts = pod_name.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0]
        return pod_name

    return service_name


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
