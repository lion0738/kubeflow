"""Helpers for exposing Notebook pods through Kubernetes networking objects."""

import hashlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from kubeflow.kubeflow.crud_backend import api, logging
from kubernetes import client

log = logging.getLogger(__name__)

PORTS_PREFIX = "ports.kubeflow.org"
ACCESS_TYPE_ANNOTATION = f"{PORTS_PREFIX}/access-type"
EXPOSURE_ID_ANNOTATION = f"{PORTS_PREFIX}/exposure-id"
WORKLOAD_ANNOTATION = f"{PORTS_PREFIX}/workload"
DOMAIN_ANNOTATION = f"{PORTS_PREFIX}/domain"
PER_REPLICA_ANNOTATION = f"{PORTS_PREFIX}/per-replica"
ORDINAL_ANNOTATION = f"{PORTS_PREFIX}/ordinal"
GATEWAY_ACCESS_TYPE = "Gateway"
DNS_LABEL_MAX_LENGTH = 63


class DomainConflictError(ValueError):
    """Raised when a requested Gateway hostname is already in use."""


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
                   protocol: str = "TCP",
                   service_name: Optional[str] = None,
                   annotations: Optional[Dict[str, str]] = None
                   ) -> Optional[ServiceHandle]:
    """Create a Service and AuthorizationPolicy to expose a pod port."""
    service_name = service_name or f"{service_type}-service-{pod_name}-{port}".lower()
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
            owner_references=owner_references,
            annotations=annotations,
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
                                 owner_references, selector, port, annotations)

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


def list_port_exposures(namespace: str,
                        selector: Dict[str, str]) -> List[Dict]:
    """Return legacy NodePorts and managed Gateway exposures for a workload."""
    services = api.list_services(namespace=namespace).items
    exposures = []
    gateway_groups: Dict[str, Dict] = {}

    for service in services:
        annotations = service.metadata.annotations or {}
        access_type = annotations.get(ACCESS_TYPE_ANNOTATION)
        if service.spec.type == "NodePort":
            if _selector_matches(service.spec.selector or {}, selector):
                exposures.extend(_serialize_service_ports(service))
            continue
        if access_type != GATEWAY_ACCESS_TYPE:
            continue
        if not _selector_matches_workload(service, selector):
            continue

        exposure_id = annotations.get(EXPOSURE_ID_ANNOTATION)
        if not exposure_id:
            continue
        service_port = _first_service_port_number(service)
        group = gateway_groups.setdefault(exposure_id, {
            "name": exposure_id,
            "port": service_port,
            "targetPort": service_port,
            "nodePort": None,
            "protocol": "TCP",
            "type": GATEWAY_ACCESS_TYPE,
            "accessType": GATEWAY_ACCESS_TYPE,
            "domain": annotations.get(DOMAIN_ANNOTATION),
            "perReplica": annotations.get(PER_REPLICA_ANNOTATION) == "true",
            "endpoints": [],
        })
        hostname = _hostname_for_service(service)
        ordinal = annotations.get(ORDINAL_ANNOTATION)
        group["endpoints"].append({
            "serviceName": service.metadata.name,
            "podName": (
                f"{annotations.get(WORKLOAD_ANNOTATION)}-{ordinal}"
                if ordinal is not None else None
            ),
            "hostname": hostname,
            "url": f"https://{hostname}" if hostname else None,
        })

    for group in gateway_groups.values():
        group["endpoints"].sort(
            key=lambda endpoint: endpoint.get("podName") or ""
        )
        exposures.append(group)
    return sorted(exposures, key=lambda item: (item["name"], item["port"]))


def create_gateway_exposure(namespace: str,
                            workload_name: str,
                            selector: Dict[str, str],
                            owner_references: Iterable,
                            port: int,
                            domain: str,
                            domain_suffix: str,
                            gateway: str,
                            per_replica: bool = False,
                            replicas: int = 1,
                            exclude_exposure_id: Optional[str] = None) -> Dict:
    """Create a shared or per-replica Gateway exposure."""
    exposure_id = f"gateway-{workload_name}-{port}".lower()
    _ensure_exposure_available(namespace, exposure_id, exclude_exposure_id)
    ordinals = list(range(max(1, replicas))) if per_replica else [None]
    hostnames = [
        _gateway_hostname(domain, domain_suffix, ordinal) for ordinal in ordinals
    ]
    _ensure_hostnames_available(
        namespace, hostnames, gateway, exclude_exposure_id
    )

    created_services = []
    created_virtual_services = []
    try:
        for ordinal, hostname in zip(ordinals, hostnames):
            suffix = f"-{ordinal}" if ordinal is not None else ""
            service_name = _dns_label_name(
                f"gateway-service-{workload_name}-{port}{suffix}"
            )
            vs_name = _dns_label_name(
                f"gateway-vs-{workload_name}-{port}{suffix}"
            )
            endpoint_selector = selector
            if ordinal is not None:
                endpoint_selector = {
                    "statefulset.kubernetes.io/pod-name":
                        f"{workload_name}-{ordinal}"
                }
            annotations = _gateway_annotations(
                exposure_id, workload_name, domain, per_replica, ordinal,
                hostname,
            )
            handle = create_service(
                namespace=namespace,
                pod_name=_policy_pod_name(service_name),
                selector=endpoint_selector,
                owner_references=owner_references,
                port=port,
                service_type="ClusterIP",
                protocol="TCP",
                service_name=service_name,
                annotations=annotations,
            )
            if handle is None:
                raise RuntimeError(f"Failed to create Service {service_name}.")
            created_services.append(service_name)
            if not create_host_virtual_service(
                    namespace, vs_name, service_name, owner_references,
                    hostname, port, gateway, annotations):
                raise RuntimeError(f"Failed to create VirtualService {vs_name}.")
            created_virtual_services.append(vs_name)
    except Exception:
        _rollback_gateway_resources(
            namespace, created_services, created_virtual_services
        )
        raise

    exposures = list_port_exposures(namespace, selector)
    return next(item for item in exposures if item["name"] == exposure_id)


def replace_gateway_exposure(namespace: str,
                             old_exposure_id: str,
                             **kwargs) -> Dict:
    """Replace every resource in a managed Gateway exposure."""
    ordinals = (
        list(range(max(1, kwargs.get("replicas", 1))))
        if kwargs.get("per_replica") else [None]
    )
    hostnames = [
        _gateway_hostname(
            kwargs["domain"], kwargs["domain_suffix"], ordinal
        )
        for ordinal in ordinals
    ]
    _ensure_hostnames_available(
        namespace, hostnames, kwargs["gateway"], old_exposure_id
    )
    delete_gateway_exposure(namespace, old_exposure_id)
    return create_gateway_exposure(
        namespace=namespace,
        exclude_exposure_id=old_exposure_id,
        **kwargs,
    )


def delete_gateway_exposure(namespace: str, exposure_id: str) -> None:
    """Delete every managed resource belonging to a Gateway exposure."""
    for service in api.list_services(namespace=namespace).items:
        annotations = service.metadata.annotations or {}
        if annotations.get(EXPOSURE_ID_ANNOTATION) != exposure_id:
            continue
        for service_port in service.spec.ports or []:
            _delete_authorization_policy(
                namespace, "ClusterIP",
                _policy_pod_name(service.metadata.name), service_port.port,
            )
        api.delete_service(namespace=namespace,
                           service_name=service.metadata.name)
    _delete_virtual_services_for_exposure(namespace, exposure_id)


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
                                 port: int,
                                 annotations: Optional[Dict[str, str]] = None) -> None:
    policy_name = f"allow-{service_type}-{pod_name}-{port}".lower()
    body = {
        "apiVersion": "security.istio.io/v1beta1",
        "kind": "AuthorizationPolicy",
        "metadata": {
            "name": policy_name,
            "namespace": namespace,
            "ownerReferences": owner_references,
            "annotations": annotations or {},
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
            "accessType": "NodePort",
            "domain": None,
            "perReplica": False,
            "endpoints": [{
                "serviceName": service.metadata.name,
                "nodePort": service_port.node_port,
            }],
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


def create_host_virtual_service(namespace: str,
                                vs_name: str,
                                service_name: str,
                                owner_references: Iterable,
                                hostname: str,
                                port: int,
                                gateway: str,
                                annotations: Dict[str, str]) -> Optional[str]:
    """Create an exact-host VirtualService for a managed port exposure."""
    body = {
        "apiVersion": "networking.istio.io/v1beta1",
        "kind": "VirtualService",
        "metadata": {
            "name": vs_name,
            "namespace": namespace,
            "ownerReferences": owner_references,
            "annotations": annotations,
        },
        "spec": {
            "hosts": [hostname],
            "gateways": [gateway],
            "http": [{
                "route": [{
                    "destination": {
                        "host": f"{service_name}.{namespace}.svc.cluster.local",
                        "port": {"number": port},
                    }
                }]
            }],
        },
    }
    try:
        client.CustomObjectsApi().create_namespaced_custom_object(
            group="networking.istio.io",
            version="v1beta1",
            namespace=namespace,
            plural="virtualservices",
            body=body,
        )
        return vs_name
    except client.rest.ApiException as exc:
        log.error("Error creating VirtualService %s: %s", vs_name, exc)
        return None


def _gateway_annotations(exposure_id: str,
                         workload_name: str,
                         domain: str,
                         per_replica: bool,
                         ordinal: Optional[int],
                         hostname: str) -> Dict[str, str]:
    annotations = {
        ACCESS_TYPE_ANNOTATION: GATEWAY_ACCESS_TYPE,
        EXPOSURE_ID_ANNOTATION: exposure_id,
        WORKLOAD_ANNOTATION: workload_name,
        DOMAIN_ANNOTATION: domain,
        PER_REPLICA_ANNOTATION: str(per_replica).lower(),
        f"{PORTS_PREFIX}/hostname": hostname,
    }
    if ordinal is not None:
        annotations[ORDINAL_ANNOTATION] = str(ordinal)
    return annotations


def _gateway_hostname(domain: str,
                      domain_suffix: str,
                      ordinal: Optional[int]) -> str:
    ordinal_suffix = f"-{ordinal}" if ordinal is not None else ""
    return f"{domain}{ordinal_suffix}.{domain_suffix}"


def _dns_label_name(value: str) -> str:
    """Return a stable Kubernetes DNS-label name no longer than 63 chars."""
    value = value.lower()
    if len(value) <= DNS_LABEL_MAX_LENGTH:
        return value

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    prefix_length = DNS_LABEL_MAX_LENGTH - len(digest) - 1
    prefix = value[:prefix_length].rstrip("-")
    return f"{prefix}-{digest}"


def _hostname_for_service(service) -> Optional[str]:
    return (service.metadata.annotations or {}).get(f"{PORTS_PREFIX}/hostname")


def _selector_matches_workload(service, selector: Dict[str, str]) -> bool:
    annotations = service.metadata.annotations or {}
    workload = annotations.get(WORKLOAD_ANNOTATION)
    requested_workload = selector.get("notebook-name")
    if workload and requested_workload:
        return workload == requested_workload
    return _selector_matches(service.spec.selector or {}, selector)


def _ensure_hostnames_available(namespace: str,
                                hostnames: List[str],
                                gateway: str,
                                exclude_exposure_id: Optional[str]) -> None:
    try:
        result = client.CustomObjectsApi().list_cluster_custom_object(
            group="networking.istio.io",
            version="v1beta1",
            plural="virtualservices",
        )
    except client.rest.ApiException as exc:
        log.error("Failed to check VirtualService hostnames: %s", exc)
        raise

    requested = {_normalize_hostname(hostname) for hostname in hostnames}
    for virtual_service in result.get("items", []):
        metadata = virtual_service.get("metadata", {})
        if not _virtual_service_uses_gateway(virtual_service, gateway):
            continue
        annotations = metadata.get("annotations") or {}
        is_current_exposure = (
            exclude_exposure_id is not None
            and metadata.get("namespace") == namespace
            and annotations.get(EXPOSURE_ID_ANNOTATION) == exclude_exposure_id
        )
        if is_current_exposure:
            continue
        existing = {
            _normalize_hostname(host)
            for host in (virtual_service.get("spec", {}).get("hosts") or [])
        }
        conflict = requested.intersection(existing)
        if conflict:
            raise DomainConflictError(
                f"Domain already in use: {sorted(conflict)[0]}"
            )


def _normalize_hostname(hostname: str) -> str:
    return str(hostname).strip().lower().rstrip(".")


def _virtual_service_uses_gateway(virtual_service: Dict, gateway: str) -> bool:
    metadata = virtual_service.get("metadata", {})
    namespace = metadata.get("namespace", "")
    configured_gateway = _qualified_gateway_name(gateway, namespace)
    gateways = virtual_service.get("spec", {}).get("gateways") or []
    return any(
        _qualified_gateway_name(item, namespace) == configured_gateway
        for item in gateways
        if item != "mesh"
    )


def _qualified_gateway_name(gateway: str, namespace: str) -> str:
    gateway = str(gateway).strip()
    if "/" in gateway:
        return gateway
    return f"{namespace}/{gateway}"


def _ensure_exposure_available(namespace: str,
                               exposure_id: str,
                               exclude_exposure_id: Optional[str]) -> None:
    if exposure_id == exclude_exposure_id:
        return
    for service in api.list_services(namespace=namespace).items:
        annotations = service.metadata.annotations or {}
        if annotations.get(EXPOSURE_ID_ANNOTATION) == exposure_id:
            raise DomainConflictError(
                f"Port exposure already exists: {exposure_id}"
            )


def _delete_virtual_services_for_exposure(namespace: str,
                                           exposure_id: str) -> None:
    custom_api = client.CustomObjectsApi()
    result = custom_api.list_namespaced_custom_object(
        group="networking.istio.io",
        version="v1beta1",
        namespace=namespace,
        plural="virtualservices",
    )
    for virtual_service in result.get("items", []):
        annotations = virtual_service.get("metadata", {}).get("annotations", {})
        if annotations.get(EXPOSURE_ID_ANNOTATION) != exposure_id:
            continue
        custom_api.delete_namespaced_custom_object(
            group="networking.istio.io",
            version="v1beta1",
            namespace=namespace,
            plural="virtualservices",
            name=virtual_service["metadata"]["name"],
        )


def _rollback_gateway_resources(namespace: str,
                                service_names: List[str],
                                virtual_service_names: List[str]) -> None:
    custom_api = client.CustomObjectsApi()
    for vs_name in virtual_service_names:
        try:
            custom_api.delete_namespaced_custom_object(
                group="networking.istio.io", version="v1beta1",
                namespace=namespace, plural="virtualservices", name=vs_name,
            )
        except client.rest.ApiException as exc:
            if exc.status != 404:
                log.error("Failed rolling back VirtualService %s: %s", vs_name, exc)
    for service_name in service_names:
        try:
            service = api.get_service(namespace, service_name)
            for service_port in service.spec.ports or []:
                _delete_authorization_policy(
                    namespace, "ClusterIP", _policy_pod_name(service_name),
                    service_port.port,
                )
            api.delete_service(namespace, service_name)
        except client.rest.ApiException as exc:
            if exc.status != 404:
                log.error("Failed rolling back Service %s: %s", service_name, exc)


def _policy_pod_name(service_name: str) -> str:
    prefix = "gateway-service-"
    if service_name.startswith(prefix):
        return service_name[len(prefix):]
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
