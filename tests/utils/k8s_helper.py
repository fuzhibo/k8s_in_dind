"""
Kubernetes helper utilities for k8s_in_dind tests.

Provides functions for:
- Kubectl operations
- Node management
- Pod management
- Resource cleanup
"""

import os
import time
import yaml
from typing import Optional, List, Dict, Any
from kubernetes import client, config
from kubernetes.client import ApiException
from kubernetes.client.models import V1Node, V1Pod, V1Namespace


# ============================================================================
# Kubeconfig Management
# ============================================================================

def load_kubeconfig(kubeconfig_path: str) -> None:
    """
    Load kubeconfig from file.

    Args:
        kubeconfig_path: Path to kubeconfig file
    """
    config.load_kube_config(config_file=kubeconfig_path)


def load_incluster_config() -> None:
    """Load in-cluster Kubernetes configuration."""
    config.load_incluster_config()


# ============================================================================
# Node Operations
# ============================================================================

def get_nodes(
    core_v1: Optional[client.CoreV1Api] = None,
    label_selector: Optional[str] = None,
) -> List[V1Node]:
    """
    Get all nodes in the cluster.

    Args:
        core_v1: CoreV1Api client (created if None)
        label_selector: Label selector to filter nodes

    Returns:
        List of node objects
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    kwargs = {}
    if label_selector:
        kwargs["label_selector"] = label_selector

    response = core_v1.list_node(**kwargs)
    return response.items


def get_node_status(node: V1Node) -> Dict[str, Any]:
    """
    Get node status information.

    Args:
        node: Node object

    Returns:
        Dict with node status info
    """
    conditions = {}
    for condition in node.status.conditions:
        conditions[condition.type] = condition.status

    return {
        "name": node.metadata.name,
        "ready": conditions.get("Ready", "Unknown"),
        "conditions": conditions,
        "addresses": {addr.type: addr.address for addr in (node.status.addresses or [])},
    }


def wait_for_nodes_ready(
    core_v1: Optional[client.CoreV1Api] = None,
    expected_count: int = 1,
    timeout: int = 120,
    interval: float = 5.0,
) -> bool:
    """
    Wait for all nodes to be ready.

    Args:
        core_v1: CoreV1Api client
        expected_count: Expected number of nodes
        timeout: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        True if all nodes are ready, False on timeout
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    start_time = time.time()
    while time.time() - start_time < timeout:
        nodes = get_nodes(core_v1)
        if len(nodes) >= expected_count:
            all_ready = True
            for node in nodes:
                status = get_node_status(node)
                if status["ready"] != "True":
                    all_ready = False
                    break
            if all_ready:
                return True
        time.sleep(interval)
    return False


# ============================================================================
# Pod Operations
# ============================================================================

def get_pods(
    core_v1: Optional[client.CoreV1Api] = None,
    namespace: str = "default",
    label_selector: Optional[str] = None,
    field_selector: Optional[str] = None,
) -> List[V1Pod]:
    """
    Get pods in a namespace.

    Args:
        core_v1: CoreV1Api client
        namespace: Namespace to search
        label_selector: Label selector to filter pods
        field_selector: Field selector to filter pods

    Returns:
        List of pod objects
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    kwargs = {}
    if label_selector:
        kwargs["label_selector"] = label_selector
    if field_selector:
        kwargs["field_selector"] = field_selector

    response = core_v1.list_namespaced_pod(namespace, **kwargs)
    return response.items


def get_pod_status(pod: V1Pod) -> Dict[str, Any]:
    """
    Get pod status information.

    Args:
        pod: Pod object

    Returns:
        Dict with pod status info
    """
    return {
        "name": pod.metadata.name,
        "namespace": pod.metadata.namespace,
        "phase": pod.status.phase,
        "pod_ip": pod.status.pod_ip,
        "container_statuses": [
            {
                "name": cs.name,
                "ready": cs.ready,
                "restart_count": cs.restart_count,
            }
            for cs in (pod.status.container_statuses or [])
        ],
    }


def wait_for_pod_ready(
    core_v1: Optional[client.CoreV1Api] = None,
    pod_name: str = "",
    namespace: str = "default",
    timeout: int = 120,
    interval: float = 2.0,
) -> bool:
    """
    Wait for a specific pod to be ready.

    Args:
        core_v1: CoreV1Api client
        pod_name: Name of the pod
        namespace: Namespace of the pod
        timeout: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        True if pod is ready, False on timeout
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            pod = core_v1.read_namespaced_pod(pod_name, namespace)
            if pod.status.phase == "Running":
                all_ready = all(
                    cs.ready for cs in (pod.status.container_statuses or [])
                )
                if all_ready:
                    return True
        except ApiException:
            pass
        time.sleep(interval)
    return False


def wait_for_pods_by_label_ready(
    core_v1: Optional[client.CoreV1Api] = None,
    label_selector: str = "",
    namespace: str = "default",
    expected_count: int = 1,
    timeout: int = 120,
    interval: float = 2.0,
) -> bool:
    """
    Wait for pods matching a label selector to be ready.

    Args:
        core_v1: CoreV1Api client
        label_selector: Label selector
        namespace: Namespace to search
        expected_count: Expected number of ready pods
        timeout: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        True if pods are ready, False on timeout
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    start_time = time.time()
    while time.time() - start_time < timeout:
        pods = get_pods(core_v1, namespace, label_selector)
        ready_count = sum(
            1 for pod in pods
            if pod.status.phase == "Running"
            and all(cs.ready for cs in (pod.status.container_statuses or []))
        )
        if ready_count >= expected_count:
            return True
        time.sleep(interval)
    return False


# ============================================================================
# Namespace Operations
# ============================================================================

def create_namespace(
    core_v1: Optional[client.CoreV1Api] = None,
    name: str = "",
    labels: Optional[Dict[str, str]] = None,
) -> Optional[V1Namespace]:
    """
    Create a namespace.

    Args:
        core_v1: CoreV1Api client
        name: Namespace name
        labels: Namespace labels

    Returns:
        Namespace object if successful, None otherwise
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    try:
        namespace = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=name,
                labels=labels or {},
            )
        )
        return core_v1.create_namespace(namespace)
    except ApiException:
        return None


def delete_namespace(
    core_v1: Optional[client.CoreV1Api] = None,
    name: str = "",
) -> bool:
    """
    Delete a namespace.

    Args:
        core_v1: CoreV1Api client
        name: Namespace name

    Returns:
        True if deleted successfully
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    try:
        core_v1.delete_namespace(name)
        return True
    except ApiException:
        return False


# ============================================================================
# Resource Cleanup
# ============================================================================

def cleanup_test_resources(
    core_v1: Optional[client.CoreV1Api] = None,
    test_label: str = "k8s_in_dind_test=true",
) -> Dict[str, int]:
    """
    Clean up test resources in all namespaces.

    Args:
        core_v1: CoreV1Api client
        test_label: Label selector for test resources

    Returns:
        Dict with counts of deleted resources
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    deleted = {"pods": 0, "services": 0, "namespaces": 0}

    try:
        # Delete test namespaces
        namespaces = core_v1.list_namespace(label_selector=test_label)
        for ns in namespaces.items:
            try:
                core_v1.delete_namespace(ns.metadata.name)
                deleted["namespaces"] += 1
            except ApiException:
                pass
    except ApiException:
        pass

    return deleted


# ============================================================================
# Utility Functions
# ============================================================================

def get_cluster_info(
    core_v1: Optional[client.CoreV1Api] = None,
) -> Dict[str, Any]:
    """
    Get cluster information.

    Args:
        core_v1: CoreV1Api client

    Returns:
        Dict with cluster info
    """
    if core_v1 is None:
        core_v1 = client.CoreV1Api()

    nodes = get_nodes(core_v1)
    return {
        "node_count": len(nodes),
        "nodes": [get_node_status(node) for node in nodes],
    }
