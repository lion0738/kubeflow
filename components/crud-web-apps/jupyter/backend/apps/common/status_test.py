import unittest
from types import SimpleNamespace

from apps.common import status


class TestStatusFromContainerState(unittest.TestCase):
    """Test the different cases of status from containerState"""

    def test_terminating_container_state(self):
        container_state = {
            "status": {
                "containerState": {
                    "terminating": {}
                }
            }
        }

        self.assertEqual(
            status.get_status_from_container_state(container_state),
            (None, None)
        )

    def test_ready_container_state(self):
        container_state = {
            "status": {
                "containerState": {
                    "running": {}
                }
            }
        }

        self.assertEqual(
            status.get_status_from_container_state(container_state),
            (None, None)
        )

    def test_no_message_container_state(self):
        container_state = {
            "status": {
                "containerState": {
                    "waiting": {
                        "reason": "PodInitializing",
                    }
                }
            }
        }

        self.assertEqual(
            status.get_status_from_container_state(container_state),
            ("waiting", "PodInitializing")
        )

    def test_error_container_state(self):
        container_state = {
            "status": {
                "containerState": {
                    "waiting": {
                        "reason": "FailedScheduling",
                        "message": "0/1 nodes are available: 1 Insufficient cpu.",
                    }
                }
            }
        }

        self.assertEqual(
            status.get_status_from_container_state(container_state),
            (
                "error",
                "FailedScheduling: 0/1 nodes are available: 1 Insufficient cpu.",
            )
        )

    def test_downloading_container_state(self):
        container_state = {
            "status": {
                "containerState": {
                    "waiting": {
                        "reason": "ContainerCreating",
                    }
                }
            }
        }

        self.assertEqual(
            status.get_status_from_container_state(container_state),
            ("downloading", "Container image is being downloaded.")
        )


class TestStatusFromEvents(unittest.TestCase):
    def test_error_event(self):
        event = SimpleNamespace(
            type="Warning",
            reason="FailedScheduling",
            message="0/1 nodes are available: 1 Insufficient memory.",
            metadata=SimpleNamespace(
                creation_timestamp=SimpleNamespace(
                    replace=lambda tzinfo=None: SimpleNamespace()
                )
            ),
        )

        self.assertEqual(
            status.get_status_from_events([event]),
            ("error", "0/1 nodes are available: 1 Insufficient memory.")
        )

    def test_downloading_event(self):
        event = SimpleNamespace(
            type="Normal",
            reason="Pulling",
            message='Pulling image "example:latest"',
            metadata=SimpleNamespace(
                creation_timestamp=SimpleNamespace(
                    replace=lambda tzinfo=None: SimpleNamespace()
                )
            ),
        )

        self.assertEqual(
            status.get_status_from_events([event]),
            ("downloading", 'Pulling image "example:latest"')
        )
