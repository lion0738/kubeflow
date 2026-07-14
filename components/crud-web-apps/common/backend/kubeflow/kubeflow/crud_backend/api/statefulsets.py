from .. import authz
from . import app_api


def create_statefulset(body, namespace):
    authz.ensure_authorized(
        "create", "kubeflow.org", "v1beta1", "notebooks", namespace
    )
    return app_api.create_namespaced_stateful_set(
        namespace=namespace, body=body
    )


def delete_statefulset(name, namespace):
    authz.ensure_authorized(
        "delete", "kubeflow.org", "v1beta1", "notebooks", namespace
    )
    return app_api.delete_namespaced_stateful_set(
        name=name, namespace=namespace
    )


def list_statefulsets(namespace):
    authz.ensure_authorized(
        "list", "kubeflow.org", "v1beta1", "notebooks", namespace
    )
    return app_api.list_namespaced_stateful_set(namespace=namespace)


def patch_statefulset(name, namespace, body):
    authz.ensure_authorized(
        "patch", "kubeflow.org", "v1beta1", "notebooks", namespace
    )
    return app_api.patch_namespaced_stateful_set(
        name=name, namespace=namespace, body=body
    )
