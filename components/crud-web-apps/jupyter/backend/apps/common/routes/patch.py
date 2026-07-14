import datetime as dt
import shlex

from flask import request
from werkzeug import exceptions

from kubeflow.kubeflow.crud_backend import api, decorators, logging

from .. import status, utils, volumes
from ..services import networking
from ..services.containers import LAST_REPLICAS_ANNOTATION
from . import bp
from .post import (
    _desired_replicas,
    _gateway_config,
    _get_access_values,
    _owner_reference_from_deployment,
)

log = logging.getLogger(__name__)

NODE_PORT_MIN = 30000
NODE_PORT_MAX = 32767
STOP_ATTR = "stopped"
RESOURCES_ATTR = "resources"
REPLICAS_ATTR = "replicas"
IMAGE_ATTR = "image"
IMAGE_PULL_POLICY_ATTR = "imagePullPolicy"
COMMAND_ATTR = "command"
ENVS_ATTR = "envs"
DATAVOLS_ATTR = "datavols"
ATTRIBUTES = set([
    STOP_ATTR,
    RESOURCES_ATTR,
    REPLICAS_ATTR,
    IMAGE_ATTR,
    IMAGE_PULL_POLICY_ATTR,
    COMMAND_ATTR,
    ENVS_ATTR,
    DATAVOLS_ATTR,
])
SETTINGS_ATTRIBUTES = ATTRIBUTES - {STOP_ATTR}


# Routes
@bp.route(
    "/api/namespaces/<namespace>/notebooks/<notebook>", methods=["PATCH"]
)
@decorators.request_is_json_type
def patch_notebook(namespace, notebook):
    request_body = request.get_json()
    log.info("Got body: %s", request_body)

    if request_body is None:
        raise exceptions.BadRequest("Request doesn't have a body.")

    # Ensure request has at least one valid command
    if not any(attr in ATTRIBUTES for attr in request_body.keys()):
        raise exceptions.BadRequest(
            "Request body must include at least one supported key: %s"
            % list(ATTRIBUTES)
        )

    # start/stop a notebook
    if STOP_ATTR in request_body:
        start_stop_notebook(namespace, notebook, request_body)

    if not any(attr in SETTINGS_ATTRIBUTES for attr in request_body.keys()):
        return api.success_response()

    notebook_obj = api.get_notebook(notebook, namespace)
    existing_container = (
        notebook_obj.get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [{}])[0]
    )
    existing_pod_spec = (
        notebook_obj.get("spec", {})
        .get("template", {})
        .get("spec", {})
    )
    patch_body = _build_pod_template_patch(
        request_body,
        existing_container,
        existing_pod_spec,
        namespace,
        use_delete_directives=False,
    )
    if patch_body:
        log.info(
            "Patching Notebook %s/%s settings: %s",
            namespace,
            notebook,
            patch_body,
        )
        api.patch_notebook(notebook, namespace, patch_body)

    return api.success_response()


# helper functions
def start_stop_notebook(namespace, notebook, request_body):
    stop = request_body[STOP_ATTR]

    patch_body = {}
    if stop:
        if notebook_is_stopped(namespace, notebook):
            raise exceptions.Conflict(
                "Notebook %s/%s is already stopped." % (namespace, notebook)
            )

        log.info("Stopping Notebook Server '%s/%s'", namespace, notebook)
        now = dt.datetime.now(dt.timezone.utc)
        timestamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")

        patch_body = {
            "metadata": {"annotations": {status.STOP_ANNOTATION: timestamp}}
        }
    else:
        log.info("Starting Notebook Server '%s/%s'", namespace, notebook)
        patch_body = {
            "metadata": {"annotations": {status.STOP_ANNOTATION: None}}
        }

    log.info(
        "Sending PATCH to Notebook %s/%s: %s", namespace, notebook, patch_body
    )
    api.patch_notebook(notebook, namespace, patch_body)


def notebook_is_stopped(namespace, notebook):
    log.info(
        "Checking if Notebook %s/%s is already stopped", namespace, notebook,
    )
    notebook = api.get_notebook(notebook, namespace)
    annotations = notebook.get("metadata", {}).get("annotations", {})

    return status.STOP_ANNOTATION in annotations

@bp.route("/api/namespaces/<namespace>/containers/<name>", methods=["PATCH"])
def patch_container(namespace, name):
    body = request.get_json()
    if body is None:
        raise exceptions.BadRequest("Request doesn't have a body.")

    if not any(attr in ATTRIBUTES for attr in body.keys()):
        raise exceptions.BadRequest(
            "Request body must include at least one supported key: %s"
            % list(ATTRIBUTES)
        )

    deployment = _get_container_deployment(namespace, name)
    if deployment is None:
        return api.failed_response("No container detected.", 404)

    annotations = deployment.metadata.annotations or {}
    current_replicas = deployment.spec.replicas or 0
    desired_replicas = _get_desired_replicas(annotations, current_replicas)

    patch_body = {}
    if STOP_ATTR in body:
        stopped = body.get(STOP_ATTR)
        patch_body = {
            "metadata": {
                "annotations": {
                    LAST_REPLICAS_ANNOTATION: str(desired_replicas),
                },
            },
            "spec": {
                "replicas": 0 if stopped else desired_replicas
            }
        }

    if any(attr in SETTINGS_ATTRIBUTES for attr in body.keys()):
        settings_patch = _build_deployment_patch(body, deployment, namespace)
        if settings_patch:
            patch_body = _deep_merge(patch_body, settings_patch)

    try:
        result = api.patch_deployment(
            name=name,
            namespace=namespace,
            body=patch_body
        )
        if REPLICAS_ATTR in body:
            _reconcile_per_replica_exposures(namespace, result)
        return api.success_response("container", result.to_dict())
    except Exception as e:
        return api.failed_response(f"Failed to patch container: {e}", 500)


@bp.route(
    "/api/namespaces/<namespace>/notebooks/<notebook>/ports/<service_name>",
    methods=["PATCH"],
)
def patch_notebook_port(namespace, notebook, service_name):
    body = request.get_json() or {}
    access_type, domain, per_replica, error = _get_access_values(body, False)
    if error:
        return api.failed_response(error, 400)
    port, node_port, protocol = _get_port_request_values(body)
    if port is None:
        return api.failed_response("Port must be an integer from 1 to 65535.", 400)
    if node_port is False:
        return api.failed_response(
            "NodePort must be an integer from 30000 to 32767.",
            400,
        )
    if protocol is None:
        return api.failed_response("Protocol must be TCP or UDP.", 400)

    selector = {"notebook-name": notebook}
    if access_type == "Gateway":
        pods = api.list_pods(
            namespace=namespace, label_selector=f"notebook-name={notebook}"
        )
        if not pods.items:
            return api.failed_response("No pod detected.", 404)
        pod = pods.items[0]
        try:
            kwargs = dict(
                workload_name=notebook,
                selector=selector,
                owner_references=pod.metadata.owner_references,
                port=port,
                domain=domain,
                per_replica=per_replica,
                replicas=1,
                **_gateway_config(),
            )
            if service_name.startswith("gateway-"):
                result = networking.replace_gateway_exposure(
                    namespace, service_name, **kwargs
                )
            else:
                result = networking.create_gateway_exposure(
                    namespace=namespace, **kwargs
                )
                networking.delete_node_port_service(
                    namespace, service_name, selector
                )
            return api.success_response("port", result)
        except networking.DomainConflictError as exc:
            return api.failed_response(str(exc), 409)
        except Exception as exc:  # pylint: disable=broad-except
            return api.failed_response(f"Failed to patch port: {exc}", 500)

    try:
        if service_name.startswith("gateway-"):
            pod = api.list_pods(
                namespace=namespace, label_selector=f"notebook-name={notebook}"
            ).items[0]
            handle = networking.create_service(
                namespace, pod.metadata.name, selector,
                pod.metadata.owner_references, port, "NodePort", node_port,
                protocol,
            )
            if handle is None:
                raise RuntimeError("Service creation failed.")
            networking.delete_gateway_exposure(namespace, service_name)
            result = next(
                item for item in networking.list_port_exposures(namespace, selector)
                if item["name"] == handle.name
            )
        else:
            result = networking.patch_node_port_service(
                namespace=namespace,
                service_name=service_name,
                port=port,
                node_port=node_port,
                protocol=protocol,
                selector=selector,
            )
        return api.success_response("port", result)
    except Exception as exc:  # pylint: disable=broad-except
        return api.failed_response(f"Failed to patch port: {exc}", 500)


@bp.route(
    "/api/namespaces/<namespace>/containers/<name>/ports/<service_name>",
    methods=["PATCH"],
)
def patch_container_port(namespace, name, service_name):
    body = request.get_json() or {}
    access_type, domain, per_replica, error = _get_access_values(body, True)
    if error:
        return api.failed_response(error, 400)
    port, node_port, protocol = _get_port_request_values(body)
    if port is None:
        return api.failed_response("Port must be an integer from 1 to 65535.", 400)
    if node_port is False:
        return api.failed_response(
            "NodePort must be an integer from 30000 to 32767.",
            400,
        )
    if protocol is None:
        return api.failed_response("Protocol must be TCP or UDP.", 400)

    workload = _get_container_deployment(namespace, name)
    if workload is None:
        return api.failed_response("No container detected.", 404)
    selector = {"notebook-name": name}
    owner_references = [_owner_reference_from_deployment(workload)]
    if access_type == "Gateway":
        try:
            kwargs = dict(
                workload_name=name,
                selector=selector,
                owner_references=owner_references,
                port=port,
                domain=domain,
                per_replica=per_replica,
                replicas=_desired_replicas(workload),
                **_gateway_config(),
            )
            if service_name.startswith("gateway-"):
                result = networking.replace_gateway_exposure(
                    namespace, service_name, **kwargs
                )
            else:
                result = networking.create_gateway_exposure(
                    namespace=namespace, **kwargs
                )
                networking.delete_node_port_service(
                    namespace, service_name, selector
                )
            return api.success_response("port", result)
        except networking.DomainConflictError as exc:
            return api.failed_response(str(exc), 409)
        except Exception as exc:  # pylint: disable=broad-except
            return api.failed_response(f"Failed to patch port: {exc}", 500)

    try:
        if service_name.startswith("gateway-"):
            pods = api.list_pods(
                namespace=namespace, label_selector=f"notebook-name={name}"
            )
            if not pods.items:
                return api.failed_response("No pod detected.", 404)
            handle = networking.create_service(
                namespace, pods.items[0].metadata.name, selector,
                owner_references, port, "NodePort", node_port, protocol,
            )
            if handle is None:
                raise RuntimeError("Service creation failed.")
            networking.delete_gateway_exposure(namespace, service_name)
            result = next(
                item for item in networking.list_port_exposures(namespace, selector)
                if item["name"] == handle.name
            )
        else:
            result = networking.patch_node_port_service(
                namespace=namespace,
                service_name=service_name,
                port=port,
                node_port=node_port,
                protocol=protocol,
                selector=selector,
            )
        return api.success_response("port", result)
    except Exception as exc:  # pylint: disable=broad-except
        return api.failed_response(f"Failed to patch port: {exc}", 500)


def _get_container_deployment(namespace, name):
    deployments = api.list_deployments(namespace=namespace).items
    return next((dep for dep in deployments if dep.metadata.name == name), None)


def _reconcile_per_replica_exposures(namespace, workload):
    selector = {"notebook-name": workload.metadata.name}
    exposures = networking.list_port_exposures(namespace, selector)
    for exposure in exposures:
        if exposure.get("accessType") != "Gateway" or not exposure.get("perReplica"):
            continue
        networking.replace_gateway_exposure(
            namespace=namespace,
            old_exposure_id=exposure["name"],
            workload_name=workload.metadata.name,
            selector=selector,
            owner_references=[_owner_reference_from_deployment(workload)],
            port=exposure["port"],
            domain=exposure["domain"],
            per_replica=True,
            replicas=_desired_replicas(workload),
            **_gateway_config(),
        )


def _get_desired_replicas(annotations, current_replicas):
    stored_replicas = annotations.get(LAST_REPLICAS_ANNOTATION)

    try:
        if stored_replicas is not None:
            return max(1, int(stored_replicas))
    except (TypeError, ValueError):
        pass

    try:
        return max(1, int(current_replicas))
    except (TypeError, ValueError):
        return 1


def _get_port_request_values(body):
    port = _valid_port(body.get("port"))
    if port is None:
        return None, None, None

    node_port_value = body.get("nodePort")
    node_port = None
    if node_port_value not in (None, ""):
        node_port = _valid_node_port(node_port_value)
        if node_port is None:
            return port, False, None

    protocol = _valid_protocol(body.get("protocol", "TCP"))
    return port, node_port, protocol


def _valid_port(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        return None

    if port < 1 or port > 65535:
        return None

    return port


def _valid_node_port(value):
    port = _valid_port(value)
    if port is None:
        return None

    if port < NODE_PORT_MIN or port > NODE_PORT_MAX:
        return None

    return port


def _valid_protocol(value):
    protocol = str(value).upper()
    if protocol not in ("TCP", "UDP"):
        return None

    return protocol


def _build_pod_template_patch(
    body,
    existing_container=None,
    existing_pod_spec=None,
    namespace=None,
    use_delete_directives=True,
):
    container_patch = _build_container_patch(
        body,
        existing_container,
        use_delete_directives,
    )
    pod_spec_patch = {}

    if DATAVOLS_ATTR in body:
        volume_patch = _build_volumes_patch(
            body[DATAVOLS_ATTR],
            existing_pod_spec or {},
            existing_container or {},
            namespace,
            use_delete_directives,
        )
        if "volumeMounts" in volume_patch:
            if "name" not in container_patch:
                container_patch["name"] = _container_name(existing_container)
            container_patch["volumeMounts"] = volume_patch.pop("volumeMounts")
        pod_spec_patch.update(volume_patch)

    if not container_patch and not pod_spec_patch:
        return {}

    if container_patch:
        pod_spec_patch["containers"] = [container_patch]

    return {
        "spec": {
            "template": {
                "spec": pod_spec_patch,
            },
        },
    }


def _build_deployment_patch(body, deployment, namespace):
    existing_container = None
    containers = deployment.spec.template.spec.containers
    if containers:
        existing_container = {
            "name": containers[0].name,
            "volumeMounts": [
                _volume_mount_to_dict(mount)
                for mount in containers[0].volume_mounts or []
            ],
            "env": [
                _env_to_dict(env)
                for env in containers[0].env or []
            ],
        }

    existing_pod_spec = {
        "volumes": [
            _volume_to_dict(volume)
            for volume in deployment.spec.template.spec.volumes or []
        ],
    }
    patch_body = _build_pod_template_patch(
        body,
        existing_container,
        existing_pod_spec,
        namespace,
        use_delete_directives=True,
    )

    if REPLICAS_ATTR in body and body[REPLICAS_ATTR] is not None:
        replicas = _normalize_replicas(body[REPLICAS_ATTR])
        replicas_patch = {
            "metadata": {
                "annotations": {
                    LAST_REPLICAS_ANNOTATION: str(replicas),
                },
            },
        }

        if (deployment.spec.replicas or 0) > 0:
            replicas_patch["spec"] = {
                "replicas": replicas,
            }

        patch_body = _deep_merge(patch_body, replicas_patch)

    return patch_body


def _build_container_patch(
    body,
    existing_container=None,
    use_delete_directives=True,
):
    if not any(
        attr in body
        for attr in [
            RESOURCES_ATTR,
            IMAGE_ATTR,
            IMAGE_PULL_POLICY_ATTR,
            COMMAND_ATTR,
            ENVS_ATTR,
        ]
    ):
        return {}

    patch = dict(existing_container or {})

    if IMAGE_ATTR in body and body[IMAGE_ATTR]:
        patch["image"] = body[IMAGE_ATTR].strip()

    if IMAGE_PULL_POLICY_ATTR in body and body[IMAGE_PULL_POLICY_ATTR]:
        patch["imagePullPolicy"] = body[IMAGE_PULL_POLICY_ATTR]

    if COMMAND_ATTR in body and body[COMMAND_ATTR] is not None:
        command = body[COMMAND_ATTR] or ""
        patch["command"] = shlex.split(command) if command.strip() else None

    if ENVS_ATTR in body and body[ENVS_ATTR] is not None:
        envs = _normalize_envs(body[ENVS_ATTR])
        if use_delete_directives:
            envs = _build_envs_patch(envs, existing_container or {})

        patch["env"] = envs

    if RESOURCES_ATTR in body:
        patch["resources"] = _normalize_resources(body[RESOURCES_ATTR])

    return patch


def _build_volumes_patch(api_volumes, existing_pod_spec, existing_container,
                         namespace, use_delete_directives):
    if api_volumes is None:
        return {}

    if not isinstance(api_volumes, list):
        raise exceptions.BadRequest("'datavols' must be a list.")

    existing_volumes = existing_pod_spec.get("volumes") or []
    existing_mounts = existing_container.get("volumeMounts") or (
        existing_container.get("volume_mounts") or []
    )
    pvc_volume_names = {
        volume.get("name")
        for volume in existing_volumes
        if volume.get("persistentVolumeClaim") or
        volume.get("persistent_volume_claim")
    }

    preserved_volumes = [
        volume for volume in existing_volumes
        if volume.get("name") not in pvc_volume_names
    ]
    preserved_mounts = [
        mount for mount in existing_mounts
        if mount.get("name") not in pvc_volume_names
    ]

    new_volumes = []
    new_mounts = []
    for api_volume in api_volumes:
        pvc = volumes.get_new_pvc(api_volume)
        if pvc is not None:
            pvc = api.create_pvc(pvc, namespace)

        pod_volume = volumes.get_pod_volume(api_volume, pvc)
        pod_mount = volumes.get_container_mount(
            api_volume,
            pod_volume["name"],
        )
        new_volumes.append(pod_volume)
        new_mounts.append(pod_mount)

    new_volume_names = {volume["name"] for volume in new_volumes}
    new_mounts_by_name = {mount["name"]: mount for mount in new_mounts}
    delete_volumes = [
        {"name": name, "$patch": "delete"}
        for name in pvc_volume_names
        if name not in new_volume_names
    ]
    delete_mounts = []
    for mount in existing_mounts:
        mount_name = mount.get("name")
        if mount_name not in pvc_volume_names:
            continue

        new_mount = new_mounts_by_name.get(mount_name)
        if new_mount and new_mount.get("mountPath") == mount.get("mountPath"):
            continue

        delete_mounts.append({
            "mountPath": mount.get("mountPath"),
            "$patch": "delete",
        })

    if use_delete_directives:
        return {
            "volumes": preserved_volumes + delete_volumes + new_volumes,
            "volumeMounts": preserved_mounts + delete_mounts + new_mounts,
        }

    return {
        "volumes": preserved_volumes + new_volumes,
        "volumeMounts": preserved_mounts + new_mounts,
    }


def _container_name(container):
    if not container:
        return None

    return container.get("name")


def _normalize_envs(envs):
    if not isinstance(envs, list):
        raise exceptions.BadRequest("'envs' must be a list.")

    normalized = []
    for env in envs:
        if not isinstance(env, dict):
            raise exceptions.BadRequest("Each env must be an object.")

        name = env.get("name")
        if not name:
            continue

        normalized.append({
            "name": name,
            "value": str(env.get("value", "")),
        })

    return normalized


def _build_envs_patch(new_envs, existing_container):
    new_env_names = {env["name"] for env in new_envs}
    existing_editable_env_names = {
        env.get("name")
        for env in existing_container.get("env", [])
        if env.get("name") and "value" in env
    }

    delete_envs = [
        {"name": name, "$patch": "delete"}
        for name in existing_editable_env_names
        if name not in new_env_names
    ]

    return delete_envs + new_envs


def _env_to_dict(env):
    env_dict = {"name": env.name}
    if env.value is not None:
        env_dict["value"] = env.value
    if env.value_from is not None:
        env_dict["valueFrom"] = api.serialize(env.value_from)

    return env_dict


def _volume_to_dict(volume):
    if not volume.persistent_volume_claim:
        return api.serialize(volume)

    volume_dict = {
        "name": volume.name,
        "persistentVolumeClaim": {
            "claimName": volume.persistent_volume_claim.claim_name,
        },
    }
    if volume.persistent_volume_claim.read_only is not None:
        volume_dict["persistentVolumeClaim"]["readOnly"] = (
            volume.persistent_volume_claim.read_only
        )
    return volume_dict


def _volume_mount_to_dict(mount):
    mount_dict = {
        "name": mount.name,
        "mountPath": mount.mount_path,
    }
    if mount.read_only is not None:
        mount_dict["readOnly"] = mount.read_only
    if mount.sub_path is not None:
        mount_dict["subPath"] = mount.sub_path
    return mount_dict


def _normalize_resources(resources):
    if not isinstance(resources, dict):
        raise exceptions.BadRequest("'resources' must be an object.")

    requests = resources.get("requests") or {}
    limits = resources.get("limits") or {}

    if not isinstance(requests, dict) or not isinstance(limits, dict):
        raise exceptions.BadRequest(
            "'resources.requests' and 'resources.limits' must be objects."
        )

    requests = dict(requests)
    limits = dict(limits)

    _sync_gpu_requests_limits(requests, limits)

    return {
        "requests": _clean_resource_values(requests),
        "limits": _clean_resource_values(limits),
    }


def _sync_gpu_requests_limits(requests, limits):
    for key in _gpu_resource_keys():
        request_value = requests.get(key)
        limit_value = limits.get(key)
        value = limit_value if limit_value not in [None, ""] else request_value

        if value is None or str(value) == "":
            continue

        requests[key] = value
        limits[key] = value


def _gpu_resource_keys():
    config = utils.load_spawner_ui_config()
    vendors = config.get("gpus", {}).get("value", {}).get("vendors", [])

    return {
        vendor.get("limitsKey")
        for vendor in vendors
        if vendor.get("limitsKey")
    }


def _clean_resource_values(values):
    return {
        key: str(value)
        for key, value in values.items()
        if value is not None and str(value) != ""
    }


def _normalize_replicas(replicas):
    try:
        value = int(replicas)
    except (TypeError, ValueError):
        raise exceptions.BadRequest("'replicas' must be an integer.")

    if value < 1:
        raise exceptions.BadRequest("'replicas' must be at least 1.")

    return value


def _deep_merge(base, patch):
    merged = dict(base)
    for key, value in patch.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value

    return merged
