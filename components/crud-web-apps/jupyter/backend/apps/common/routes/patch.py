import datetime as dt
import shlex

from flask import request
from werkzeug import exceptions

from kubeflow.kubeflow.crud_backend import api, decorators, logging

from .. import status, volumes
from ..services.containers import LAST_REPLICAS_ANNOTATION
from . import bp

log = logging.getLogger(__name__)

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
        return api.success_response("container", result.to_dict())
    except Exception as e:
        return api.failed_response(f"Failed to patch container: {e}", 500)


def _get_container_deployment(namespace, name):
    deployments = api.list_deployments(namespace=namespace).items
    return next((dep for dep in deployments if dep.metadata.name == name), None)


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

    return {
        "requests": _clean_resource_values(requests),
        "limits": _clean_resource_values(limits),
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
