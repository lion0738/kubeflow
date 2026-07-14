"""Tests for custom-container workload compatibility helpers."""

import unittest
from types import SimpleNamespace
from unittest import mock

from . import workloads


def _workload(name, kind, custom=True):
    return SimpleNamespace(
        api_version="apps/v1",
        kind=kind,
        metadata=SimpleNamespace(
            name=name,
            uid=f"{name}-uid",
            labels={"container-type": "custom-container"} if custom else {},
        ),
    )


class ContainerWorkloadsTest(unittest.TestCase):

    @mock.patch.object(workloads.api, "list_deployments")
    @mock.patch.object(workloads.api, "list_statefulsets")
    def test_lists_statefulsets_and_legacy_deployments(
            self, list_statefulsets, list_deployments):
        list_statefulsets.return_value = SimpleNamespace(items=[
            _workload("new", "StatefulSet"),
            _workload("same", "StatefulSet"),
        ])
        list_deployments.return_value = SimpleNamespace(items=[
            _workload("legacy", "Deployment"),
            _workload("same", "Deployment"),
            _workload("other", "Deployment", custom=False),
        ])

        result = workloads.list_container_workloads("team-a")

        self.assertEqual(
            [(item.metadata.name, item.kind) for item in result],
            [
                ("new", "StatefulSet"),
                ("same", "StatefulSet"),
                ("legacy", "Deployment"),
            ],
        )

    @mock.patch.object(workloads.api, "patch_deployment")
    @mock.patch.object(workloads.api, "patch_statefulset")
    def test_patches_the_actual_workload_kind(
            self, patch_statefulset, patch_deployment):
        statefulset = _workload("new", "StatefulSet")
        deployment = _workload("legacy", "Deployment")

        workloads.patch_container_workload(
            "team-a", "new", {"spec": {"replicas": 2}}, statefulset
        )
        workloads.patch_container_workload(
            "team-a", "legacy", {"spec": {"replicas": 2}}, deployment
        )

        patch_statefulset.assert_called_once()
        patch_deployment.assert_called_once()

    def test_owner_reference_preserves_workload_kind(self):
        reference = workloads.owner_reference(
            _workload("new", "StatefulSet")
        )

        self.assertEqual(reference.kind, "StatefulSet")
        self.assertEqual(reference.name, "new")

if __name__ == "__main__":
    unittest.main()
