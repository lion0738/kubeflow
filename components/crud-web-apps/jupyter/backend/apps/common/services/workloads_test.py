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

    @mock.patch.object(workloads.api, "list_deployments")
    @mock.patch.object(workloads.api, "list_statefulsets")
    def test_records_kind_when_kubernetes_list_item_omits_it(
            self, list_statefulsets, list_deployments):
        statefulset = _workload("new", None)
        deployment = _workload("legacy", None)
        list_statefulsets.return_value = SimpleNamespace(items=[statefulset])
        list_deployments.return_value = SimpleNamespace(items=[deployment])

        result = workloads.list_container_workloads("team-a")

        self.assertEqual(workloads.workload_kind(result[0]), "StatefulSet")
        self.assertEqual(workloads.workload_kind(result[1]), "Deployment")

    @mock.patch.object(workloads.api, "delete_deployment")
    @mock.patch.object(workloads.api, "delete_statefulset")
    def test_deletes_kindless_statefulset_using_recorded_kind(
            self, delete_statefulset, delete_deployment):
        statefulset = _workload("new", None)
        workloads._set_workload_kind(statefulset, "StatefulSet")

        workloads.delete_container_workload(
            "team-a", "new", workload=statefulset
        )

        delete_statefulset.assert_called_once_with(
            name="new", namespace="team-a"
        )
        delete_deployment.assert_not_called()

    def test_kindless_statefulset_owner_reference_uses_recorded_kind(self):
        statefulset = _workload("new", None)
        workloads._set_workload_kind(statefulset, "StatefulSet")

        reference = workloads.owner_reference(statefulset)

        self.assertEqual(reference.kind, "StatefulSet")

if __name__ == "__main__":
    unittest.main()
