"""Tests for managed port networking resources."""

import unittest
from types import SimpleNamespace
from unittest import mock

from . import networking


class GatewayExposureTest(unittest.TestCase):

    @mock.patch.object(networking.api, "list_services")
    @mock.patch.object(networking.client, "CustomObjectsApi")
    @mock.patch.object(networking, "list_port_exposures")
    @mock.patch.object(networking, "create_host_virtual_service")
    @mock.patch.object(networking, "create_service")
    def test_shared_exposure_uses_workload_selector(
            self, create_service, create_vs, list_exposures, custom_api,
            list_services):
        list_services.return_value = SimpleNamespace(items=[])
        custom_api.return_value.list_cluster_custom_object.return_value = {
            "items": []
        }
        create_service.return_value = networking.ServiceHandle("service")
        create_vs.return_value = "virtual-service"
        list_exposures.return_value = [{
            "name": "gateway-demo-8000", "port": 8000
        }]

        networking.create_gateway_exposure(
            namespace="team-a",
            workload_name="demo",
            selector={"notebook-name": "demo"},
            owner_references=[],
            port=8000,
            domain="abc",
            domain_suffix="knu-kubeflow.duckdns.org",
            gateway="kubeflow/custom-gateway",
        )

        self.assertEqual(
            create_service.call_args.kwargs["selector"],
            {"notebook-name": "demo"},
        )
        self.assertEqual(
            create_vs.call_args.args[4],
            "abc.knu-kubeflow.duckdns.org",
        )

    @mock.patch.object(networking.api, "list_services")
    @mock.patch.object(networking.client, "CustomObjectsApi")
    @mock.patch.object(networking, "list_port_exposures")
    @mock.patch.object(networking, "create_host_virtual_service")
    @mock.patch.object(networking, "create_service")
    def test_per_replica_exposure_uses_statefulset_pod_selector(
            self, create_service, create_vs, list_exposures, custom_api,
            list_services):
        list_services.return_value = SimpleNamespace(items=[])
        custom_api.return_value.list_cluster_custom_object.return_value = {
            "items": []
        }
        create_service.return_value = networking.ServiceHandle("service")
        create_vs.return_value = "virtual-service"
        list_exposures.return_value = [{
            "name": "gateway-demo-8000", "port": 8000
        }]

        networking.create_gateway_exposure(
            namespace="team-a",
            workload_name="demo",
            selector={"notebook-name": "demo"},
            owner_references=[],
            port=8000,
            domain="abc",
            domain_suffix="knu-kubeflow.duckdns.org",
            gateway="kubeflow/custom-gateway",
            per_replica=True,
            replicas=2,
        )

        selectors = [call.kwargs["selector"]
                     for call in create_service.call_args_list]
        self.assertEqual(selectors, [
            {"statefulset.kubernetes.io/pod-name": "demo-0"},
            {"statefulset.kubernetes.io/pod-name": "demo-1"},
        ])
        hostnames = [call.args[4] for call in create_vs.call_args_list]
        self.assertEqual(hostnames, [
            "abc-0.knu-kubeflow.duckdns.org",
            "abc-1.knu-kubeflow.duckdns.org",
        ])

    @mock.patch.object(networking.client, "CustomObjectsApi")
    def test_rejects_an_existing_hostname(self, custom_api):
        custom_api.return_value.list_cluster_custom_object.return_value = {
            "items": [{
                "metadata": {},
                "spec": {"hosts": ["abc.knu-kubeflow.duckdns.org"]},
            }]
        }

        with self.assertRaises(networking.DomainConflictError):
            networking._ensure_hostnames_available(
                ["abc.knu-kubeflow.duckdns.org"], None
            )

    def test_long_resource_names_are_stable_dns_labels(self):
        value = "gateway-service-" + ("a" * 63) + "-8000-0"

        first = networking._dns_label_name(value)
        second = networking._dns_label_name(value)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 63)
        self.assertRegex(first, r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


if __name__ == "__main__":
    unittest.main()
