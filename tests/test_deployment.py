"""
Deployment test cases for k8s_in_dind.

This module contains tests for verifying cluster deployment functionality
with different CRI and CNI combinations.
"""

import time
import pytest
import docker
import subprocess
from typing import Dict, Any, List

from utils.docker_helper import (
    create_container,
    wait_for_container,
    exec_in_container,
    remove_container,
    get_container_ip,
    cleanup_test_containers,
)


# ============================================================================
# Constants
# ============================================================================

CLUSTER_START_TIMEOUT = 300  # seconds
API_SERVER_READY_TIMEOUT = 300  # seconds (increased for slower systems)
CNI_READY_TIMEOUT = 120  # seconds
NODE_READY_TIMEOUT = 120  # seconds


# ============================================================================
# Helper Functions
# ============================================================================

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
    last_error = ""
    while time.time() - start_time < timeout:
        exit_code, output = exec_in_container(
            container,
            "kubectl get nodes --kubeconfig /etc/kubernetes/admin.conf"
        )
        if exit_code == 0 and "NAME" in output:
            return True
        if exit_code != 0:
            last_error = output[:200] if output else "no output"
        time.sleep(10)
    print(f"API server wait failed. Last error: {last_error}")
    return False


def wait_for_node_ready(
    container: docker.models.containers.Container,
    timeout: int = NODE_READY_TIMEOUT
) -> bool:
    """
    Wait for node to be in Ready state.

    Args:
        container: Docker container object
        timeout: Maximum wait time in seconds

    Returns:
        True if node is ready, False otherwise
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        exit_code, output = exec_in_container(
            container,
            "kubectl get nodes --kubeconfig /etc/kubernetes/admin.conf -o jsonpath='{.items[0].status.conditions[?(@.type==\"Ready\")].status}'"
        )
        if exit_code == 0 and "True" in output:
            return True
        time.sleep(5)
    return False


def wait_for_cni_pods(
    container: docker.models.containers.Container,
    cni_category: str,
    timeout: int = CNI_READY_TIMEOUT
) -> bool:
    """
    Wait for CNI pods to be ready.

    Args:
        container: Docker container object
        cni_category: CNI type (calico, flannel)
        timeout: Maximum wait time in seconds

    Returns:
        True if CNI pods are ready, False otherwise
    """
    namespace = "kube-flannel" if cni_category == "flannel" else "kube-system"
    label_selector = "app=flannel" if cni_category == "flannel" else "k8s-app=calico-node"

    start_time = time.time()
    while time.time() - start_time < timeout:
        exit_code, output = exec_in_container(
            container,
            f"kubectl get pods -n {namespace} -l {label_selector} --kubeconfig /etc/kubernetes/admin.conf -o jsonpath='{{.items[0].status.phase}}'"
        )
        if exit_code == 0 and "Running" in output:
            return True
        time.sleep(5)
    return False


def get_join_command(
    container: docker.models.containers.Container
) -> str:
    """
    Get the kubeadm join command from a master node.

    Args:
        container: Master node container

    Returns:
        Join command string or empty string if failed
    """
    exit_code, output = exec_in_container(
        container,
        "kubeadm token create --print-join-command"
    )
    if exit_code == 0:
        return output.strip()
    return ""


def verify_cluster_health(
    container: docker.models.containers.Container,
    expected_nodes: int = 1
) -> Dict[str, Any]:
    """
    Verify cluster health status.

    Args:
        container: Master node container
        expected_nodes: Expected number of nodes

    Returns:
        Dict with health check results
    """
    result = {
        "nodes_ready": False,
        "pods_running": False,
        "core_pods": [],
        "errors": []
    }

    # Check nodes
    exit_code, output = exec_in_container(
        container,
        "kubectl get nodes --kubeconfig /etc/kubernetes/admin.conf -o wide"
    )
    if exit_code == 0:
        result["nodes_output"] = output
        if "Ready" in output and output.count("Ready") >= expected_nodes:
            result["nodes_ready"] = True
    else:
        result["errors"].append(f"Failed to get nodes: {output}")

    # Check all pods
    exit_code, output = exec_in_container(
        container,
        "kubectl get pods -A --kubeconfig /etc/kubernetes/admin.conf"
    )
    if exit_code == 0:
        result["pods_output"] = output
        if "Running" in output:
            result["pods_running"] = True
            # Count running pods
            running_count = output.count("Running")
            result["running_pods"] = running_count
    else:
        result["errors"].append(f"Failed to get pods: {output}")

    return result


# ============================================================================
# Test Classes
# ============================================================================

class TestDockerFlannelSingle:
    """Tests for Docker CRI + Flannel CNI single node deployment."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-flannel-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass
        # Also try to remove by name in case of partial setup
        try:
            cleanup_test_containers(self.docker_client, "k8s_in_dind_test")
        except Exception:
            pass

    @pytest.mark.integration
    @pytest.mark.slow
    def test_docker_flannel_single(self, docker_registry):
        """Test Docker CRI + Flannel CNI single node deployment."""
        image = f"{docker_registry}/k8s-in-dind:20.10.9-v1.23.17"

        # 1. Start container with Flannel CNI
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            hostname=self.container_name,
            privileged=True,
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "flannel",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "flannel_single",
            },
        )

        # 2. Wait for container to be running
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Wait for API server to be ready
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"

        # 4. Wait for node to be ready
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Wait for Flannel CNI pods
        assert wait_for_cni_pods(self.container, "flannel"), \
            "Flannel pods failed to become ready"

        # 6. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"
        assert health["pods_running"], f"Pods not running: {health.get('errors', [])}"

        # 7. Verify Flannel pod specifically
        exit_code, output = exec_in_container(
            self.container,
            "kubectl get pods -n kube-flannel --kubeconfig /etc/kubernetes/admin.conf"
        )
        assert exit_code == 0, f"Failed to get Flannel pods: {output}"
        assert "kube-flannel" in output, "Flannel pod not found"
        assert "Running" in output, "Flannel pod not running"


class TestDockerCalicoMasterWorker:
    """Tests for Docker CRI + Calico CNI multi-node deployment."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.master_name = f"test-calico-master-{request.node.name}"
        self.worker_name = f"test-calico-worker-{request.node.name}"
        self.master = None
        self.worker = None
        yield
        # Cleanup
        for container in [self.master, self.worker]:
            if container:
                try:
                    remove_container(container)
                except Exception:
                    pass

    @pytest.mark.integration
    @pytest.mark.slow
    def test_docker_calico_master_worker(self, docker_registry):
        """Test Docker CRI + Calico CNI one master one worker deployment."""
        image = f"{docker_registry}/k8s-in-dind:20.10.9-v1.23.17"

        # 1. Start master node
        self.master = create_container(
            self.docker_client,
            image=image,
            name=self.master_name,
            privileged=True,
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "calico",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "calico_master",
            },
        )

        # 2. Wait for master to be ready
        assert wait_for_container(self.master, timeout=60), \
            "Master container failed to start"
        assert wait_for_api_server(self.master), \
            "Master API server failed to become ready"
        assert wait_for_node_ready(self.master), \
            "Master node failed to become ready"

        # 3. Get join command
        join_cmd = get_join_command(self.master)
        assert join_cmd, "Failed to get join command"

        # 4. Get master IP
        master_ip = get_container_ip(self.master)
        assert master_ip, "Failed to get master IP"

        # 5. Start worker node
        self.worker = create_container(
            self.docker_client,
            image=image,
            name=self.worker_name,
            privileged=True,
            environment={
                "KUBEADM_JOIN_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "API_SERVER_ENDPOINT": f"{master_ip}:6443",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "calico_worker",
            },
        )

        # 6. Wait for worker to join
        assert wait_for_container(self.worker, timeout=60), \
            "Worker container failed to start"

        # 7. Verify two nodes in cluster
        # Wait longer for worker to join
        time.sleep(60)

        # 8. Verify cluster health with 2 nodes
        health = verify_cluster_health(self.master, expected_nodes=2)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"

        # 9. Verify Calico pods
        assert wait_for_cni_pods(self.master, "calico"), \
            "Calico pods failed to become ready"


class TestDockerAuto:
    """Tests for Docker CRI + auto CNI selection."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-auto-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass

    @pytest.mark.integration
    @pytest.mark.slow
    def test_docker_auto_cni(self, docker_registry):
        """Test Docker CRI + auto CNI selection (should default to calico)."""
        image = f"{docker_registry}/k8s-in-dind:20.10.9-v1.23.17"

        # 1. Start container with auto CNI
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            privileged=True,
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "auto",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "auto_cni",
            },
        )

        # 2. Wait for container to be running
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Wait for API server to be ready
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"

        # 4. Wait for node to be ready
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Verify cluster health (auto should default to calico for this version)
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"
        assert health["pods_running"], f"Pods not running: {health.get('errors', [])}"


# ============================================================================
# Containerd CRI Tests
# ============================================================================

class TestContainerdFlannelSingle:
    """Tests for Containerd CRI + Flannel CNI single node deployment."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-containerd-flannel-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass
        try:
            cleanup_test_containers(self.docker_client, "k8s_in_dind_test")
        except Exception:
            pass

    @pytest.mark.integration
    @pytest.mark.slow
    def test_containerd_flannel_single(self, docker_registry):
        """Test Containerd CRI + Flannel CNI single node deployment."""
        # Use 23.0.5-v1.31.7 image which supports containerd CRI
        image = f"{docker_registry}/k8s-in-dind:23.0.5-v1.31.7"

        # 1. Start container with Containerd CRI + Flannel CNI
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            privileged=True,
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.31.7",
                "CNI_CATEGORY": "flannel",
                "CRI_TYPE": "containerd",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "containerd_flannel_single",
            },
        )

        # 2. Wait for container to be running
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Wait for API server to be ready
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"

        # 4. Wait for node to be ready
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Wait for Flannel CNI pods
        assert wait_for_cni_pods(self.container, "flannel"), \
            "Flannel pods failed to become ready"

        # 6. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"
        assert health["pods_running"], f"Pods not running: {health.get('errors', [])}"

        # 7. Verify containerd is being used
        exit_code, output = exec_in_container(
            self.container,
            "crictl info 2>&1 | head -5"
        )
        assert exit_code == 0, f"Failed to check CRI: {output}"
        assert "containerd" in output.lower() or "Containerd" in output, \
            f"Containerd CRI not detected: {output}"


class TestContainerdCalicoMasterWorker:
    """Tests for Containerd CRI + Calico CNI multi-node deployment."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.master_name = f"test-containerd-calico-master-{request.node.name}"
        self.worker_name = f"test-containerd-calico-worker-{request.node.name}"
        self.master = None
        self.worker = None
        yield
        # Cleanup
        for container in [self.master, self.worker]:
            if container:
                try:
                    remove_container(container)
                except Exception:
                    pass

    @pytest.mark.integration
    @pytest.mark.slow
    def test_containerd_calico_master_worker(self, docker_registry):
        """Test Containerd CRI + Calico CNI one master one worker deployment."""
        # Use 23.0.5-v1.31.7 image which supports containerd CRI
        image = f"{docker_registry}/k8s-in-dind:23.0.5-v1.31.7"

        # 1. Start master node
        self.master = create_container(
            self.docker_client,
            image=image,
            name=self.master_name,
            privileged=True,
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.31.7",
                "CNI_CATEGORY": "calico",
                "CRI_TYPE": "containerd",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "containerd_calico_master",
            },
        )

        # 2. Wait for master to be ready
        assert wait_for_container(self.master, timeout=60), \
            "Master container failed to start"
        assert wait_for_api_server(self.master), \
            "Master API server failed to become ready"
        assert wait_for_node_ready(self.master), \
            "Master node failed to become ready"

        # 3. Get join command
        join_cmd = get_join_command(self.master)
        assert join_cmd, "Failed to get join command"

        # 4. Get master IP
        master_ip = get_container_ip(self.master)
        assert master_ip, "Failed to get master IP"

        # 5. Start worker node
        self.worker = create_container(
            self.docker_client,
            image=image,
            name=self.worker_name,
            privileged=True,
            environment={
                "KUBEADM_JOIN_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.31.7",
                "API_SERVER_ENDPOINT": f"{master_ip}:6443",
                "CRI_TYPE": "containerd",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "containerd_calico_worker",
            },
        )

        # 6. Wait for worker to join
        assert wait_for_container(self.worker, timeout=60), \
            "Worker container failed to start"

        # 7. Verify two nodes in cluster
        time.sleep(60)

        # 8. Verify cluster health with 2 nodes
        health = verify_cluster_health(self.master, expected_nodes=2)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"

        # 9. Verify Calico pods
        assert wait_for_cni_pods(self.master, "calico"), \
            "Calico pods failed to become ready"

        # 10. Verify containerd is being used on master
        exit_code, output = exec_in_container(
            self.master,
            "crictl info 2>&1 | head -5"
        )
        assert exit_code == 0, f"Failed to check CRI on master: {output}"


# ============================================================================
# Version Compatibility Tests
# ============================================================================

class TestVersionCompatibility:
    """Tests for version compatibility checks."""

    @pytest.mark.unit
    def test_version_matrix_valid(self, test_versions):
        """Verify version matrix contains valid entries."""
        assert len(test_versions) > 0, "Version matrix is empty"

        for version in test_versions:
            assert "docker" in version, "Missing docker version"
            assert "k8s" in version, "Missing k8s version"
            assert "cri" in version, "Missing CRI type"

    @pytest.mark.unit
    def test_cri_compatibility_docker(self):
        """Verify Docker CRI is only supported for K8s < v1.24."""
        # v1.23.x should support Docker
        assert _is_docker_cri_supported("v1.23.17"), \
            "Docker CRI should be supported for K8s v1.23"

        # v1.24+ should not support Docker
        assert not _is_docker_cri_supported("v1.24.0"), \
            "Docker CRI should not be supported for K8s v1.24+"


def _is_docker_cri_supported(k8s_version: str) -> bool:
    """
    Check if Docker CRI is supported for a K8s version.

    Args:
        k8s_version: Kubernetes version string

    Returns:
        True if Docker CRI is supported
    """
    # Parse version (e.g., "v1.23.17" -> (1, 23))
    try:
        version_str = k8s_version.lstrip("v")
        major, minor = map(int, version_str.split(".")[:2])
        # Docker CRI (dockershim) was removed in K8s v1.24
        return (major, minor) < (1, 24)
    except (ValueError, AttributeError):
        return False


# ============================================================================
# Sysbox Runtime Helper Functions
# ============================================================================

def is_sysbox_available() -> bool:
    """Check if sysbox-runc runtime is available.

    Returns:
        True if sysbox-runc runtime is installed and available
    """
    try:
        client = docker.from_env()
        info = client.info()
        runtimes = info.get('Runtimes', {})
        return 'sysbox-runc' in runtimes
    except Exception:
        return False


def get_product_uuid(container: docker.models.containers.Container) -> str:
    """Get product_uuid from inside a container.

    Args:
        container: Docker container object

    Returns:
        Product UUID string, or 'unknown' if not readable
    """
    exit_code, output = exec_in_container(
        container,
        "cat /sys/class/dmi/id/product_uuid 2>/dev/null || echo 'unknown'"
    )
    return output.strip() if exit_code == 0 else "unknown"


def get_host_product_uuid() -> str:
    """Get host product_uuid (requires sudo).

    Returns:
        Host product UUID string, or 'unknown' if not readable
    """
    try:
        result = subprocess.run(
            ["sudo", "cat", "/sys/class/dmi/id/product_uuid"],
            capture_output=True, text=True, timeout=5
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


# ============================================================================
# Runc Runtime Tests (Explicit Runtime Specification)
# ============================================================================

class TestRuncDockerFlannelSingle:
    """Tests for Docker CRI + Flannel CNI with explicit runc runtime."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-runc-flannel-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass
        try:
            cleanup_test_containers(self.docker_client, "k8s_in_dind_test")
        except Exception:
            pass

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.runtime_runc
    def test_runc_docker_flannel_single(self, docker_registry):
        """Test Docker CRI + Flannel CNI with explicit runc runtime (requires privileged)."""
        image = f"{docker_registry}/k8s-in-dind:20.10.9-v1.23.17"

        # 1. Start container with explicit runc runtime
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            hostname=self.container_name,
            privileged=True,  # runc requires privileged for DinD
            runtime="runc",  # Explicit runc runtime
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "flannel",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "runc_flannel_single",
            },
        )

        # 2. Wait for container to be running
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Wait for API server to be ready
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"

        # 4. Wait for node to be ready
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Wait for Flannel CNI pods
        assert wait_for_cni_pods(self.container, "flannel"), \
            "Flannel pods failed to become ready"

        # 6. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"
        assert health["pods_running"], f"Pods not running: {health.get('errors', [])}"

        # 7. Verify Flannel pod specifically
        exit_code, output = exec_in_container(
            self.container,
            "kubectl get pods -n kube-flannel --kubeconfig /etc/kubernetes/admin.conf"
        )
        assert exit_code == 0, f"Failed to get Flannel pods: {output}"
        assert "kube-flannel" in output, "Flannel pod not found"
        assert "Running" in output, "Flannel pod not running"


class TestRuncContainerdFlannelSingle:
    """Tests for Containerd CRI + Flannel CNI with explicit runc runtime."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-runc-containerd-flannel-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass
        try:
            cleanup_test_containers(self.docker_client, "k8s_in_dind_test")
        except Exception:
            pass

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.runtime_runc
    def test_runc_containerd_flannel_single(self, docker_registry):
        """Test Containerd CRI + Flannel CNI with explicit runc runtime."""
        image = f"{docker_registry}/k8s-in-dind:23.0.5-v1.31.7"

        # 1. Start container with explicit runc runtime
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            privileged=True,  # runc requires privileged for DinD
            runtime="runc",  # Explicit runc runtime
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.31.7",
                "CNI_CATEGORY": "flannel",
                "CRI_TYPE": "containerd",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "runc_containerd_flannel_single",
            },
        )

        # 2. Wait for container to be running
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Wait for API server to be ready
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"

        # 4. Wait for node to be ready
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Wait for Flannel CNI pods
        assert wait_for_cni_pods(self.container, "flannel"), \
            "Flannel pods failed to become ready"

        # 6. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"
        assert health["pods_running"], f"Pods not running: {health.get('errors', [])}"

        # 7. Verify containerd is being used
        exit_code, output = exec_in_container(
            self.container,
            "crictl info 2>&1 | head -5"
        )
        assert exit_code == 0, f"Failed to check CRI: {output}"
        assert "containerd" in output.lower() or "Containerd" in output, \
            f"Containerd CRI not detected: {output}"


class TestRuncDockerCalicoSingle:
    """Tests for Docker CRI + Calico CNI with explicit runc runtime."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-runc-calico-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.runtime_runc
    def test_runc_docker_calico_single(self, docker_registry):
        """Test Docker CRI + Calico CNI with explicit runc runtime."""
        image = f"{docker_registry}/k8s-in-dind:20.10.9-v1.23.17"

        # 1. Start container with explicit runc runtime
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            privileged=True,  # runc requires privileged for DinD
            runtime="runc",  # Explicit runc runtime
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "calico",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "runc_calico_single",
            },
        )

        # 2. Wait for container to be running
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Wait for API server to be ready
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"

        # 4. Wait for node to be ready
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"
        assert health["pods_running"], f"Pods not running: {health.get('errors', [])}"

        # 6. Verify Calico CNI pods
        assert wait_for_cni_pods(self.container, "calico"), \
            "Calico pods failed to become ready"


class TestRuncContainerdCalicoSingle:
    """Tests for Containerd CRI + Calico CNI with explicit runc runtime."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-runc-containerd-calico-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.runtime_runc
    def test_runc_containerd_calico_single(self, docker_registry):
        """Test Containerd CRI + Calico CNI with explicit runc runtime."""
        image = f"{docker_registry}/k8s-in-dind:23.0.5-v1.31.7"

        # 1. Start container with explicit runc runtime
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            privileged=True,  # runc requires privileged for DinD
            runtime="runc",  # Explicit runc runtime
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.31.7",
                "CNI_CATEGORY": "calico",
                "CRI_TYPE": "containerd",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "runc_containerd_calico_single",
            },
        )

        # 2. Wait for container to be running
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Wait for API server to be ready
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"

        # 4. Wait for node to be ready
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"

        # 6. Verify Calico CNI pods
        assert wait_for_cni_pods(self.container, "calico"), \
            "Calico pods failed to become ready"

        # 7. Verify containerd is being used
        exit_code, output = exec_in_container(
            self.container,
            "crictl info 2>&1 | head -5"
        )
        assert exit_code == 0, f"Failed to check CRI: {output}"


# ============================================================================
# Sysbox Runtime Tests
# ============================================================================

@pytest.mark.skipif(not is_sysbox_available(), reason="sysbox-runc not installed")
class TestSysboxDockerFlannelSingle:
    """Tests for Docker CRI + Flannel CNI with sysbox runtime (no privileged)."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-sysbox-flannel-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.runtime_sysbox
    def test_sysbox_docker_flannel_single(self, docker_registry):
        """Test sysbox runtime without privileged mode."""
        image = f"{docker_registry}/k8s-in-dind:20.10.9-v1.23.17"

        # 1. Create container with sysbox runtime (no privileged needed)
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            hostname=self.container_name,
            privileged=False,  # sysbox does NOT need privileged
            runtime="sysbox-runc",
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "flannel",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "sysbox_flannel_single",
            },
        )

        # 2. Verify container started
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Verify unique product_uuid (key sysbox feature)
        container_uuid = get_product_uuid(self.container)
        assert container_uuid != "unknown", \
            "Could not read container product_uuid"

        # 4. Wait for cluster
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"
        assert health["pods_running"], f"Pods not running: {health.get('errors', [])}"

        # 6. Verify Flannel CNI pods
        assert wait_for_cni_pods(self.container, "flannel"), \
            "Flannel pods failed to become ready"


@pytest.mark.skipif(not is_sysbox_available(), reason="sysbox-runc not installed")
class TestSysboxContainerdFlannelSingle:
    """Tests for Containerd CRI + Flannel CNI with sysbox runtime."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-sysbox-containerd-flannel-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.runtime_sysbox
    def test_sysbox_containerd_flannel_single(self, docker_registry):
        """Test sysbox runtime with Containerd CRI."""
        image = f"{docker_registry}/k8s-in-dind:23.0.5-v1.31.7"

        # 1. Create container with sysbox runtime
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            hostname=self.container_name,
            privileged=False,
            runtime="sysbox-runc",
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.31.7",
                "CNI_CATEGORY": "flannel",
                "CRI_TYPE": "containerd",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "sysbox_containerd_flannel_single",
            },
        )

        # 2. Verify container started
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Verify unique product_uuid
        container_uuid = get_product_uuid(self.container)
        assert container_uuid != "unknown", \
            "Could not read container product_uuid"

        # 4. Wait for cluster
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"

        # 6. Verify containerd is being used
        exit_code, output = exec_in_container(
            self.container,
            "crictl info 2>&1 | head -5"
        )
        assert exit_code == 0, f"Failed to check CRI: {output}"


@pytest.mark.skipif(not is_sysbox_available(), reason="sysbox-runc not installed")
class TestSysboxProductUuidUniqueness:
    """Tests for sysbox product_uuid uniqueness feature."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name1 = f"test-sysbox-uuid-1-{request.node.name}"
        self.container_name2 = f"test-sysbox-uuid-2-{request.node.name}"
        self.container1 = None
        self.container2 = None
        yield
        # Cleanup
        for container in [self.container1, self.container2]:
            if container:
                try:
                    remove_container(container)
                except Exception:
                    pass

    @pytest.mark.integration
    @pytest.mark.runtime_sysbox
    def test_sysbox_unique_product_uuids(self, docker_registry):
        """Test that each sysbox container has a unique product_uuid."""
        image = f"{docker_registry}/k8s-in-dind:20.10.9-v1.23.17"

        # 1. Create two containers with sysbox runtime
        self.container1 = create_container(
            self.docker_client,
            image=image,
            name=self.container_name1,
            privileged=False,
            runtime="sysbox-runc",
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "flannel",
            },
            volumes={"/lib/modules": {"bind": "/lib/modules", "mode": "ro"}},
            labels={"k8s_in_dind_test": "true", "test_type": "sysbox_uuid_test"},
        )

        self.container2 = create_container(
            self.docker_client,
            image=image,
            name=self.container_name2,
            privileged=False,
            runtime="sysbox-runc",
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "flannel",
            },
            volumes={"/lib/modules": {"bind": "/lib/modules", "mode": "ro"}},
            labels={"k8s_in_dind_test": "true", "test_type": "sysbox_uuid_test"},
        )

        # 2. Get product_uuids from both containers
        uuid1 = get_product_uuid(self.container1)
        uuid2 = get_product_uuid(self.container2)

        # 3. Verify both UUIDs are readable and unique
        assert uuid1 != "unknown", "Container 1 product_uuid is unknown"
        assert uuid2 != "unknown", "Container 2 product_uuid is unknown"
        assert uuid1 != uuid2, \
            f"Product UUIDs are not unique: {uuid1} == {uuid2}"

        # 4. Optionally verify they differ from host (requires sudo)
        host_uuid = get_host_product_uuid()
        if host_uuid != "unknown":
            assert uuid1 != host_uuid, \
                f"Container 1 UUID matches host: {uuid1} == {host_uuid}"
            assert uuid2 != host_uuid, \
                f"Container 2 UUID matches host: {uuid2} == {host_uuid}"


@pytest.mark.skipif(not is_sysbox_available(), reason="sysbox-runc not installed")
class TestSysboxDockerCalicoSingle:
    """Tests for Docker CRI + Calico CNI with sysbox runtime."""

    @pytest.fixture(autouse=True)
    def setup(self, docker_client, request):
        """Setup and cleanup for each test."""
        self.docker_client = docker_client
        self.container_name = f"test-sysbox-calico-{request.node.name}"
        self.container = None
        yield
        # Cleanup
        if self.container:
            try:
                remove_container(self.container)
            except Exception:
                pass

    @pytest.mark.integration
    @pytest.mark.slow
    @pytest.mark.runtime_sysbox
    def test_sysbox_docker_calico_single(self, docker_registry):
        """Test sysbox runtime with Calico CNI."""
        image = f"{docker_registry}/k8s-in-dind:20.10.9-v1.23.17"

        # 1. Create container with sysbox runtime
        self.container = create_container(
            self.docker_client,
            image=image,
            name=self.container_name,
            hostname=self.container_name,
            privileged=False,
            runtime="sysbox-runc",
            environment={
                "KUBEADM_INIT_WORKFLOW": "enable",
                "KUBEADM_K8S_VERSION": "v1.23.17",
                "CNI_CATEGORY": "calico",
            },
            volumes={
                "/lib/modules": {"bind": "/lib/modules", "mode": "ro"},
            },
            labels={
                "k8s_in_dind_test": "true",
                "test_type": "sysbox_calico_single",
            },
        )

        # 2. Verify container started
        assert wait_for_container(self.container, timeout=60), \
            "Container failed to start"

        # 3. Verify unique product_uuid
        container_uuid = get_product_uuid(self.container)
        assert container_uuid != "unknown", \
            "Could not read container product_uuid"

        # 4. Wait for cluster
        assert wait_for_api_server(self.container), \
            "API server failed to become ready"
        assert wait_for_node_ready(self.container), \
            "Node failed to become ready"

        # 5. Verify cluster health
        health = verify_cluster_health(self.container, expected_nodes=1)
        assert health["nodes_ready"], f"Nodes not ready: {health.get('errors', [])}"

        # 6. Verify Calico CNI pods
        assert wait_for_cni_pods(self.container, "calico"), \
            "Calico pods failed to become ready"
