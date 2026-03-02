"""
Kubernetes cluster fixtures for k8s_in_dind tests.

Provides fixtures for:
- Cluster creation and teardown
- Kubeconfig management
- Node join operations
"""

import os
import time
import subprocess
import pytest
import docker
from typing import Generator, Dict, Any, Optional, List


# ============================================================================
# Constants
# ============================================================================

CLUSTER_START_TIMEOUT = 300  # seconds
NODE_READY_TIMEOUT = 120  # seconds
API_SERVER_READY_TIMEOUT = 60  # seconds
CNI_READY_TIMEOUT = 120  # seconds

# Supported CNI types
CNI_TYPES = ["calico", "flannel", "auto"]


# ============================================================================
# Helper Functions
# ============================================================================

def wait_for_container_ready(
    container: docker.models.containers.Container,
    timeout: int = CLUSTER_START_TIMEOUT
) -> bool:
    """
    Wait for container to be in running state.

    Args:
        container: Docker container object
        timeout: Maximum wait time in seconds

    Returns:
        True if container is ready, False otherwise
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        container.reload()
        if container.status == "running":
            return True
        if container.status == "exited":
            return False
        time.sleep(1)
    return False


def wait_for_api_server(
    container: docker.models.containers.Container,
    timeout: int = API_SERVER_READY_TIMEOUT
) -> bool:
    """
    Wait for Kubernetes API server to be ready.

    Args:
        container: Docker container object
        timeout: Maximum wait time in seconds

    Returns:
        True if API server is ready, False otherwise
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            exit_code, output = container.exec_run(
                "kubectl get nodes --kubeconfig /etc/kubernetes/admin.conf"
            )
            if exit_code == 0:
                return True
        except docker.errors.APIError:
            pass
        time.sleep(5)
    return False


def get_join_command(container: docker.models.containers.Container) -> Optional[str]:
    """
    Get the kubeadm join command from a master node.

    Args:
        container: Master node container

    Returns:
        Join command string or None if failed
    """
    try:
        exit_code, output = container.exec_run(
            "kubeadm token create --print-join-command"
        )
        if exit_code == 0:
            return output.decode("utf-8").strip()
    except docker.errors.APIError:
        pass
    return None


# ============================================================================
# Fixtures: Master Node
# ============================================================================

@pytest.fixture(scope="function")
def k8s_master(
    docker_client: docker.DockerClient,
    request: pytest.FixtureRequest,
    test_env: Dict[str, Any],
    docker_registry: str,
    test_versions: List[Dict[str, str]]
) -> Generator[Dict[str, Any], None, None]:
    """
    Create a single-node K8s master for testing.

    Yields:
        Dict with container info, kubeconfig, and connection details.
    """
    # Get version from parametrization or use first available
    version = test_versions[0] if test_versions else VERSION_MATRIX[0]

    image_name = f"k8s-in-dind:{version['docker']}-{version['k8s']}"

    container_name = f"k8s-test-master-{request.node.name}"

    # Create container
    container = docker_client.containers.run(
        image_name,
        name=container_name,
        privileged=True,
        detach=True,
        environment={
            "CONTAINERD_INDIVIDUALLY_START": "true",
            "KUBEADM_INIT_WORKFLOW": "enable",
            "KUBEADM_K8S_VERSION": version["k8s"],
            "CNI_CATEGORY": "calico",
        },
        volumes={
            "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
        },
        labels={
            "k8s_in_dind_test": "true",
            "test_node": request.node.name,
        },
    )

    try:
        # Wait for container to be ready
        if not wait_for_container_ready(container):
            raise RuntimeError(f"Container {container_name} failed to start")

        # Wait for API server
        if not wait_for_api_server(container):
            raise RuntimeError(f"API server not ready in {container_name}")

        # Extract kubeconfig
        exit_code, kubeconfig = container.exec_run(
            "cat /etc/kubernetes/admin.conf"
        )
        if exit_code == 0:
            with open(test_env["kubeconfig"], "w") as f:
                f.write(kubeconfig.decode("utf-8"))

        yield {
            "container": container,
            "container_id": container.id,
            "container_name": container_name,
            "kubeconfig": test_env["kubeconfig"],
            "version": version,
        }

    finally:
        # Cleanup
        try:
            container.remove(force=True)
        except docker.errors.APIError:
            pass


# ============================================================================
# Fixtures: Multi-Node Cluster
# ============================================================================

@pytest.fixture(scope="function")
def k8s_cluster(
    docker_client: docker.DockerClient,
    request: pytest.FixtureRequest,
    test_env: Dict[str, Any],
    docker_registry: str,
    test_versions: List[Dict[str, str]]
) -> Generator[Dict[str, Any], None, None]:
    """
    Create a multi-node K8s cluster for testing.

    Yields:
        Dict with master and worker nodes info, kubeconfig.
    """
    version = test_versions[0] if test_versions else VERSION_MATRIX[0]
    image_name = f"k8s-in-dind:{version['docker']}-{version['k8s']}"

    master_name = f"k8s-test-master-{request.node.name}"
    worker_name = f"k8s-test-worker-{request.node.name}"

    containers = []

    try:
        # Create master node
        master = docker_client.containers.run(
            image_name,
            name=master_name,
            privileged=True,
            detach=True,
            environment={
                "CONTAINERD_INDIVIDUALLY_START": "true",
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": version["k8s"],
                "CNI_CATEGORY": "calico",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_node": request.node.name,
                "role": "master",
            },
        )
        containers.append(master)

        # Wait for master to be ready
        if not wait_for_container_ready(master):
            raise RuntimeError(f"Master container {master_name} failed to start")

        if not wait_for_api_server(master):
            raise RuntimeError(f"API server not ready in master {master_name}")

        # Get master IP for worker join
        master.reload()
        master_ip = master.attrs["NetworkSettings"]["IPAddress"]

        # Get join command
        join_cmd = get_join_command(master)
        if not join_cmd:
            raise RuntimeError("Failed to get join command from master")

        # Create worker node
        worker = docker_client.containers.run(
            image_name,
            name=worker_name,
            privileged=True,
            detach=True,
            environment={
                "CONTAINERD_INDIVIDUALLY_START": "true",
                "KUBEADM_JOIN_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": version["k8s"],
                "API_SERVER_ENDPOINT": f"{master_ip}:6443",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_node": request.node.name,
                "role": "worker",
            },
        )
        containers.append(worker)

        # Wait for worker to be ready
        if not wait_for_container_ready(worker):
            raise RuntimeError(f"Worker container {worker_name} failed to start")

        # Extract kubeconfig
        exit_code, kubeconfig = master.exec_run(
            "cat /etc/kubernetes/admin.conf"
        )
        if exit_code == 0:
            with open(test_env["kubeconfig"], "w") as f:
                f.write(kubeconfig.decode("utf-8"))

        yield {
            "master": {
                "container": master,
                "container_id": master.id,
                "container_name": master_name,
                "ip": master_ip,
            },
            "workers": [
                {
                    "container": worker,
                    "container_id": worker.id,
                    "container_name": worker_name,
                }
            ],
            "kubeconfig": test_env["kubeconfig"],
            "version": version,
        }

    finally:
        # Cleanup all containers
        for container in containers:
            try:
                container.remove(force=True)
            except docker.errors.APIError:
                pass


# ============================================================================
# Helper Functions: CNI
# ============================================================================

def wait_for_cni_ready(
    container: docker.models.containers.Container,
    cni_type: str = "calico",
    timeout: int = CNI_READY_TIMEOUT
) -> bool:
    """
    Wait for CNI pods to be ready.

    Args:
        container: Master node container
        cni_type: CNI type (calico, flannel)
        timeout: Maximum wait time in seconds

    Returns:
        True if CNI is ready, False otherwise
    """
    cni_selectors = {
        "calico": "k8s-app=calico-node",
        "flannel": "app=flannel",
    }

    selector = cni_selectors.get(cni_type, "k8s-app=calico-node")
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            exit_code, output = container.exec_run(
                f"kubectl get pods -n kube-system -l {selector} "
                f"--kubeconfig /etc/kubernetes/admin.conf -o jsonpath='{{.items[*].status.phase}}'"
            )
            if exit_code == 0:
                phases = output.decode("utf-8").strip().split()
                if phases and all(p == "Running" for p in phases):
                    return True
        except docker.errors.APIError:
            pass
        time.sleep(5)
    return False


def wait_for_node_ready(
    container: docker.models.containers.Container,
    node_name: str = "",
    timeout: int = NODE_READY_TIMEOUT
) -> bool:
    """
    Wait for a node to be in Ready state.

    Args:
        container: Master node container
        node_name: Node name (empty for all nodes)
        timeout: Maximum wait time in seconds

    Returns:
        True if node is ready, False otherwise
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        try:
            cmd = "kubectl get nodes --kubeconfig /etc/kubernetes/admin.conf -o jsonpath='{.items[*].status.conditions[?(@.type==\"Ready\")].status}'"
            exit_code, output = container.exec_run(cmd)
            if exit_code == 0:
                statuses = output.decode("utf-8").strip().split()
                if statuses and all(s == "True" for s in statuses):
                    return True
        except docker.errors.APIError:
            pass
        time.sleep(5)
    return False


# ============================================================================
# Fixtures: Single Node with CNI
# ============================================================================

@pytest.fixture(scope="function")
def k8s_single_node(
    docker_client: docker.DockerClient,
    request: pytest.FixtureRequest,
    test_env: Dict[str, Any],
    docker_registry: str,
    test_versions: List[Dict[str, str]]
) -> Generator[Dict[str, Any], None, None]:
    """
    Create a single-node K8s cluster with configurable CNI.

    Yields:
        Dict with container info, kubeconfig, and connection details.

    Usage:
        @pytest.mark.parametrize("k8s_single_node", ["flannel"], indirect=True)
        def test_with_flannel(k8s_single_node):
            ...
    """
    # Get CNI type from parametrization or default to calico
    cni_type = getattr(request, "param", "calico")
    if cni_type not in CNI_TYPES:
        cni_type = "calico"

    version = test_versions[0] if test_versions else VERSION_MATRIX[0]
    image_name = f"{docker_registry}/k8s-in-dind:{version['docker']}-{version['k8s']}"

    container_name = f"k8s-test-single-{cni_type}-{request.node.name}"

    # Create container
    container = docker_client.containers.run(
        image_name,
        name=container_name,
        privileged=True,
        detach=True,
        environment={
            "CONTAINERD_INDIVIDUALLY_START": "true",
            "KUBEADM_INIT_WORKFLOW": "enable",
            "KUBEADM_K8S_VERSION": version["k8s"],
            "CNI_CATEGORY": cni_type,
        },
        volumes={
            "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
        },
        labels={
            "k8s_in_dind_test": "true",
            "test_node": request.node.name,
            "cni": cni_type,
        },
    )

    try:
        # Wait for container to be ready
        if not wait_for_container_ready(container):
            raise RuntimeError(f"Container {container_name} failed to start")

        # Wait for API server
        if not wait_for_api_server(container):
            raise RuntimeError(f"API server not ready in {container_name}")

        # Wait for node to be ready
        if not wait_for_node_ready(container):
            raise RuntimeError(f"Node not ready in {container_name}")

        # Wait for CNI to be ready
        if not wait_for_cni_ready(container, cni_type):
            raise RuntimeError(f"CNI {cni_type} not ready in {container_name}")

        # Extract kubeconfig
        exit_code, kubeconfig = container.exec_run(
            "cat /etc/kubernetes/admin.conf"
        )
        if exit_code == 0:
            with open(test_env["kubeconfig"], "w") as f:
                f.write(kubeconfig.decode("utf-8"))

        yield {
            "container": container,
            "container_id": container.id,
            "container_name": container_name,
            "kubeconfig": test_env["kubeconfig"],
            "version": version,
            "cni_type": cni_type,
        }

    finally:
        # Cleanup
        try:
            container.remove(force=True)
        except docker.errors.APIError:
            pass


# ============================================================================
# Fixtures: Multi-Node Cluster with CNI
# ============================================================================

@pytest.fixture(scope="function")
def k8s_multi_node(
    docker_client: docker.DockerClient,
    request: pytest.FixtureRequest,
    test_env: Dict[str, Any],
    docker_registry: str,
    test_versions: List[Dict[str, str]]
) -> Generator[Dict[str, Any], None, None]:
    """
    Create a multi-node K8s cluster with configurable CNI.

    Yields:
        Dict with master and worker nodes info, kubeconfig.

    Usage:
        @pytest.mark.parametrize("k8s_multi_node", ["calico"], indirect=True)
        def test_with_calico(k8s_multi_node):
            ...
    """
    # Get CNI type from parametrization or default to calico
    cni_type = getattr(request, "param", "calico")
    if cni_type not in CNI_TYPES:
        cni_type = "calico"

    version = test_versions[0] if test_versions else VERSION_MATRIX[0]
    image_name = f"{docker_registry}/k8s-in-dind:{version['docker']}-{version['k8s']}"

    master_name = f"k8s-test-master-{cni_type}-{request.node.name}"
    worker_name = f"k8s-test-worker-{cni_type}-{request.node.name}"

    containers = []

    try:
        # Create master node
        master = docker_client.containers.run(
            image_name,
            name=master_name,
            privileged=True,
            detach=True,
            environment={
                "CONTAINERD_INDIVIDUALLY_START": "true",
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": version["k8s"],
                "CNI_CATEGORY": cni_type,
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_node": request.node.name,
                "role": "master",
                "cni": cni_type,
            },
        )
        containers.append(master)

        # Wait for master to be ready
        if not wait_for_container_ready(master):
            raise RuntimeError(f"Master container {master_name} failed to start")

        if not wait_for_api_server(master):
            raise RuntimeError(f"API server not ready in master {master_name}")

        # Get master IP for worker join
        master.reload()
        master_ip = master.attrs["NetworkSettings"]["IPAddress"]

        # Get join command and extract token/hash
        join_cmd = get_join_command(master)
        if not join_cmd:
            raise RuntimeError("Failed to get join command from master")

        # Create worker node
        worker = docker_client.containers.run(
            image_name,
            name=worker_name,
            privileged=True,
            detach=True,
            environment={
                "CONTAINERD_INDIVIDUALLY_START": "true",
                "KUBEADM_JOIN_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": version["k8s"],
                "API_SERVER_ENDPOINT": f"{master_ip}:6443",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_node": request.node.name,
                "role": "worker",
                "cni": cni_type,
            },
        )
        containers.append(worker)

        # Wait for worker to be ready
        if not wait_for_container_ready(worker):
            raise RuntimeError(f"Worker container {worker_name} failed to start")

        # Wait for both nodes to be ready
        if not wait_for_node_ready(master):
            raise RuntimeError("Nodes not ready in cluster")

        # Wait for CNI to be ready
        if not wait_for_cni_ready(master, cni_type):
            raise RuntimeError(f"CNI {cni_type} not ready in cluster")

        # Extract kubeconfig
        exit_code, kubeconfig = master.exec_run(
            "cat /etc/kubernetes/admin.conf"
        )
        if exit_code == 0:
            with open(test_env["kubeconfig"], "w") as f:
                f.write(kubeconfig.decode("utf-8"))

        yield {
            "master": {
                "container": master,
                "container_id": master.id,
                "container_name": master_name,
                "ip": master_ip,
            },
            "workers": [
                {
                    "container": worker,
                    "container_id": worker.id,
                    "container_name": worker_name,
                }
            ],
            "kubeconfig": test_env["kubeconfig"],
            "version": version,
            "cni_type": cni_type,
        }

    finally:
        # Cleanup all containers
        for container in containers:
            try:
                container.remove(force=True)
            except docker.errors.APIError:
                pass
