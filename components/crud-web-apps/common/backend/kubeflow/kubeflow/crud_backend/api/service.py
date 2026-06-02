from .. import authz
from . import v1_core


def get_service(namespace, service_name, auth=True):
    if auth:
        authz.ensure_authorized("get", "", "v1", "services", namespace)

    return v1_core.read_namespaced_service(name=service_name, namespace=namespace)


def create_service(namespace, body, auth=True):
    if auth:
        authz.ensure_authorized("create", "", "v1", "services", namespace)

    return v1_core.create_namespaced_service(namespace=namespace, body=body)


def list_services(namespace, auth=True):
    if auth:
        authz.ensure_authorized("list", "", "v1", "services", namespace)

    return v1_core.list_namespaced_service(namespace=namespace)


def patch_service(namespace, service_name, body, auth=True):
    if auth:
        authz.ensure_authorized("patch", "", "v1", "services", namespace)

    return v1_core.patch_namespaced_service(
        name=service_name,
        namespace=namespace,
        body=body,
    )


def delete_service(namespace, service_name, auth=True):
    if auth:
        authz.ensure_authorized("delete", "", "v1", "services", namespace)

    return v1_core.delete_namespaced_service(
        name=service_name,
        namespace=namespace,
    )
