from .. import authz
from . import app_api


def create_deployment(body, namespace, dry_run=False):
    authz.ensure_authorized(
        "create", "kubeflow.org", "v1beta1", "notebooks", namespace
    )

    return app_api.create_namespaced_deployment(namespace=namespace, body=body)


def delete_deployment(name, namespace):
    authz.ensure_authorized(
        "delete", "kubeflow.org", "v1beta1", "notebooks", namespace
    )

    return app_api.delete_namespaced_deployment(name=name, namespace=namespace)


def list_deployments(namespace):
    authz.ensure_authorized(
        "list", "kubeflow.org", "v1beta1", "notebooks", namespace
    )

    return app_api.list_namespaced_deployment(namespace=namespace)


def patch_deployment(name, namespace, body):
    authz.ensure_authorized(
        "patch", "kubeflow.org", "v1beta1", "notebooks", namespace
    )

    return app_api.patch_namespaced_deployment(
        name=name,
        namespace=namespace,
        body=body
    )
