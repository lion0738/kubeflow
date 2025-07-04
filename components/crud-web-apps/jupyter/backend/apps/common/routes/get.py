"""GET request handlers."""

from flask import request
from kubeflow.kubeflow.crud_backend import api, logging
from kubernetes import client
from werkzeug.exceptions import NotFound

from .. import utils
from .. import status
from . import bp

log = logging.getLogger(__name__)


@bp.route("/api/config")
def get_config():
    config = utils.load_spawner_ui_config()
    return api.success_response("config", config)


@bp.route("/api/namespaces/<namespace>/pvcs")
def get_pvcs(namespace):
    pvcs = api.list_pvcs(namespace).items
    data = [{"name": pvc.metadata.name,
             "size": pvc.spec.resources.requests["storage"],
             "mode": pvc.spec.access_modes[0]} for pvc in pvcs]

    return api.success_response("pvcs", data)


@bp.route("/api/namespaces/<namespace>/poddefaults")
def get_poddefaults(namespace):
    pod_defaults = api.list_poddefaults(namespace)

    # Return a list of pod defaults adding custom fields (label, desc) for
    # forms
    contents = []
    for pd in pod_defaults["items"]:
        label = "unknown"
        if "matchLabels" in pd and pd["matchLabels"]:
            label = list(pd["matchLabels"].keys())[0]
        elif "matchExpressions" in pd and pd["matchExpressions"]:
            label = pd["matchExpressions"][0].get("key", "unknown")
        if "desc" in pd["spec"]:
            desc = pd["spec"]["desc"]
        else:
            desc = pd["metadata"]["name"]

        pd["label"] = label
        pd["desc"] = desc
        contents.append(pd)

    log.info("Found poddefaults: %s", contents)

    return api.success_response("poddefaults", contents)


@bp.route("/api/namespaces/<namespace>/notebooks")
def get_notebooks(namespace):
    # notebook 목록
    notebook_list = api.list_notebooks(namespace)["items"]
    pod_list = api.list_pods(namespace=namespace)
    notebook_items = [utils.notebook_dict_from_k8s_obj(nb, pod_list) for nb in notebook_list]

    # container 목록
    deployments = api.list_deployments(namespace=namespace).items
    container_items = []
    for dep in deployments:
        labels = dep.metadata.labels or {}
        if labels.get("container-type") != "custom-container":
            continue
        matching_pod = next(
            (pod for pod in pod_list.items if pod.metadata.labels.get("app") == dep.metadata.name),
            None
        )
        container_items.append(utils.container_dict_from_k8s_obj(dep, matching_pod))

    contents = notebook_items + container_items

    return api.success_response("notebooks", contents)


@bp.route("/api/namespaces/<namespace>/notebooks/<name>")
def get_notebook(name, namespace):
    notebook = api.get_notebook(name, namespace)
    notebook["processed_status"] = status.process_status(notebook)

    return api.success_response("notebook", notebook)


@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/pod")
def get_notebook_pod(notebook_name, namespace):
    label_selector = "notebook-name=" + notebook_name
    # There should be only one Pod for each Notebook,
    # so we expect items to have length = 1
    pods = api.list_pods(namespace=namespace, label_selector=label_selector)
    if pods.items:
        pod = pods.items[0]
        return api.success_response(
            "pod", api.serialize(pod),
        )
    else:
        raise NotFound("No pod detected.")


@bp.route("/api/namespaces/<namespace>/pod")
def get_pod(namespace):
    label_selector = request.args.get("labelSelector")
    pods = api.list_pods(namespace, label_selector=label_selector)
    if pods.items:
        pod = pods.items[0]
        return api.success_response("pod", api.serialize(pod))
    else:
        raise NotFound("No pod detected.")


@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/pod/<pod_name>/logs")  # noqa: E501
def get_pod_logs(namespace, notebook_name, pod_name):
    container = notebook_name
    logs = api.get_pod_logs(namespace, pod_name, container)
    return api.success_response(
        "logs", logs.split("\n"),
    )


@bp.route("/api/namespaces/<namespace>/notebooks/<notebook_name>/events")
def get_notebook_events(notebook_name, namespace):
    events = api.list_notebook_events(notebook_name, namespace).items

    return api.success_response(
        "events", api.serialize(events),
    )


@bp.route("/api/gpus")
def get_gpu_vendors():
    """
    Return a list of GPU vendors for which at least one node has the necessary
    annotation required to schedule pods
    """
    frontend_config = utils.load_spawner_ui_config()
    gpus_value = frontend_config.get("gpus", {}).get("value", {})
    config_vendor_keys = [
        v.get("limitsKey", "") for v in gpus_value.get("vendors", [])
    ]

    # Get all of the different resources installed in all nodes
    installed_resources = set()
    nodes = api.list_nodes().items
    for node in nodes:
        if node.status.capacity:
            installed_resources.update(node.status.capacity.keys())
        else:
            log.debug(
                f"Capacity was not available for node {node.metadata.name}"
            )

    # Keep the vendors the key of which exists in at least one node
    available_vendors = installed_resources.intersection(config_vendor_keys)

    return api.success_response("vendors", list(available_vendors))
