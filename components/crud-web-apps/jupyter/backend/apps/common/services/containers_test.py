"""Tests for custom-container StatefulSet volume handling."""

import unittest
from types import SimpleNamespace
from unittest import mock

from . import containers


class PerReplicaVolumesTest(unittest.TestCase):

    def setUp(self):
        self.api_volume = {
            "mount": "/data",
            "perReplica": True,
            "newPvc": {
                "metadata": {"name": "workspace"},
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "5Gi"}},
                },
            },
        }

    @mock.patch.object(containers.api, "create_pvc")
    @mock.patch.object(containers.volumes, "get_container_mount")
    @mock.patch.object(containers.volumes, "get_new_pvc")
    def test_per_replica_volume_becomes_claim_template(
            self, get_new_pvc, get_mount, create_pvc):
        pvc = SimpleNamespace(metadata=SimpleNamespace(name="workspace"))
        get_new_pvc.return_value = pvc
        get_mount.return_value = {"name": "workspace", "mountPath": "/data"}

        pod_volumes, mounts, templates = containers._create_volumes(
            [self.api_volume], "team-a"
        )

        self.assertEqual(pod_volumes, [])
        self.assertEqual(mounts, [{"name": "workspace", "mountPath": "/data"}])
        self.assertEqual(templates, [pvc])
        create_pvc.assert_not_called()

    @mock.patch.object(containers.volumes, "get_new_pvc")
    def test_per_replica_volume_requires_multiple_replicas(self, get_new_pvc):
        get_new_pvc.return_value = SimpleNamespace(
            metadata=SimpleNamespace(name="workspace")
        )

        with self.assertRaisesRegex(ValueError, "at least two replicas"):
            containers._validate_per_replica_volumes([self.api_volume], 1)

    def test_long_headless_service_name_is_shortened(self):
        service_name = containers._dns_label_name(("a" * 63) + "-headless")

        self.assertEqual(len(service_name), 63)
        self.assertRegex(service_name, r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


if __name__ == "__main__":
    unittest.main()
