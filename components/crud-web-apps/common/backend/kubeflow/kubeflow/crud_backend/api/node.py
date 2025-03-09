from . import v1_core


def list_nodes():
    return v1_core.list_node()


def get_node(node_name):
    return v1_core.read_node(node_name)
