from kubeflow.kubeflow.crud_backend import api, logging

from ..services import networking, workloads
from . import bp

log = logging.getLogger(__name__)


@bp.route(
    "/api/namespaces/<namespace>/notebooks/<notebook>", methods=["DELETE"]
)
def delete_notebook(notebook, namespace):
    log.info("Deleting Notebook '%s/%s'" % (namespace, notebook))
    api.delete_notebook(notebook, namespace)

    return api.success_response(
        "message", "Notebook %s successfully deleted." % notebook
    )

@bp.route("/api/namespaces/<namespace>/containers/<name>", methods=["DELETE"])
def delete_container(namespace, name):

    try:
        workload = workloads.get_container_workload(namespace, name)
        if workload is None:
            return api.failed_response("No container detected.", 404)
        workloads.delete_container_workload(
            name=name, namespace=namespace, workload=workload
        )
        return api.success_response("container", {"message": "Container deleted"})
    except Exception as e:
        return api.failed_response(f"Container deletion failed: {e}", 500)


@bp.route(
    "/api/namespaces/<namespace>/notebooks/<notebook>/ports/<service_name>",
    methods=["DELETE"],
)
def delete_notebook_port(namespace, notebook, service_name):
    try:
        if service_name.startswith("gateway-"):
            networking.delete_gateway_exposure(namespace, service_name)
        else:
            networking.delete_node_port_service(
                namespace,
                service_name,
                {"notebook-name": notebook},
            )
        return api.success_response(
            "message",
            "Port service %s successfully deleted." % service_name,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return api.failed_response(f"Port service deletion failed: {exc}", 500)


@bp.route(
    "/api/namespaces/<namespace>/containers/<name>/ports/<service_name>",
    methods=["DELETE"],
)
def delete_container_port(namespace, name, service_name):
    try:
        if service_name.startswith("gateway-"):
            networking.delete_gateway_exposure(namespace, service_name)
        else:
            networking.delete_node_port_service(
                namespace,
                service_name,
                {"notebook-name": name},
            )
        return api.success_response(
            "message",
            "Port service %s successfully deleted." % service_name,
        )
    except Exception as exc:  # pylint: disable=broad-except
        return api.failed_response(f"Port service deletion failed: {exc}", 500)
