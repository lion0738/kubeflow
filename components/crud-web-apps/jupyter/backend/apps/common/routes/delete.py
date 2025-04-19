from kubeflow.kubeflow.crud_backend import api, logging

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
        result = api.delete_deployment(name=name, namespace=namespace)
        return api.success_response("container", {"message": "Container deleted"})
    except Exception as e:
        return api.failed_response(f"Container deletion failed: {e}", 500)

