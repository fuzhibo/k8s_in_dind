"""
pytest configuration and fixtures for k8s_in_dind tests.

This module provides:
- Parametrized image versions for testing
- Docker client fixtures
- Test environment cleanup
- Timeout configuration
"""

import os
import pytest
import docker
from typing import Generator, List, Dict, Any


# ============================================================================
# Configuration Constants
# ============================================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_DIR = os.path.dirname(os.path.abspath(__file__))

# Default timeout for cluster operations (seconds)
DEFAULT_CLUSTER_TIMEOUT = int(os.getenv("TEST_CLUSTER_TIMEOUT", "300"))

# Default timeout for individual tests (seconds)
DEFAULT_TEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "60"))

# Supported version matrix
# Each entry defines a test configuration with:
# - docker: Docker version
# - k8s: Kubernetes version
# - cri: Container runtime interface (docker, containerd)
# - cni: Supported CNI plugins (calico, flannel)
# - runtime: Supported runtimes (runc, sysbox) - sysbox requires sysbox-runc installed
# - cgroup: cgroup version (v1, v2)
VERSION_MATRIX = [
    # Docker 18.09.0 versions (cgroup v1, older K8s)
    {"docker": "18.09.0", "k8s": "v1.12.0", "cri": "docker", "cni": ["calico"], "runtime": ["runc"], "cgroup": "v1"},
    {"docker": "18.09.0", "k8s": "v1.16.15", "cri": "docker", "cni": ["calico"], "runtime": ["runc"], "cgroup": "v1"},

    # Docker 20.10.9 versions (cgroup v1, K8s 1.23 - last with dockershim)
    {"docker": "20.10.9", "k8s": "v1.23.17", "cri": "docker", "cni": ["calico", "flannel"], "runtime": ["runc", "sysbox"], "cgroup": "v1"},

    # Docker 23.0.5 versions (cgroup v2, K8s 1.24+ requires containerd)
    {"docker": "23.0.5", "k8s": "v1.31.7", "cri": "containerd", "cni": ["calico", "flannel"], "runtime": ["runc", "sysbox"], "cgroup": "v2"},
]

# Runtime availability check
def is_runtime_available(runtime: str) -> bool:
    """Check if a specific runtime is available."""
    try:
        client = docker.from_env()
        info = client.info()
        return runtime in info.get('Runtimes', {})
    except docker.errors.DockerException:
        return False


# CNI compatibility rules
def get_supported_cni_versions(k8s_version: str, cni_type: str) -> List[str]:
    """Get supported CNI versions for a K8s version."""
    # Calico versions
    if cni_type == "calico":
        if k8s_version.startswith("v1.12") or k8s_version.startswith("v1.16"):
            return ["v3.14"]
        elif k8s_version.startswith("v1.23"):
            return ["v3.18"]
        else:
            return ["v3.29"]

    # Flannel versions
    if cni_type == "flannel":
        return ["v0.22.0", "v0.22.1"]

    return []


def get_image_tag(docker_version: str, k8s_version: str) -> str:
    """Generate image tag from versions."""
    k8s_ver_clean = k8s_version.lstrip("v")
    return f"{docker_version}-{k8s_ver_clean}"


# ============================================================================
# Command Line Options
# ============================================================================

def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options."""
    parser.addoption(
        "--docker-version",
        action="store",
        default=None,
        help="Docker version to test (e.g., 20.10.9, 23.0.5)"
    )
    parser.addoption(
        "--k8s-version",
        action="store",
        default=None,
        help="Kubernetes version to test (e.g., v1.23.17, v1.31.7)"
    )
    parser.addoption(
        "--cri-type",
        action="store",
        default=None,
        choices=["docker", "containerd", "auto"],
        help="CRI type to use for testing"
    )
    parser.addoption(
        "--registry",
        action="store",
        default="ccr.ccs.tencentyun.com/fuzhibo",
        help="Docker registry to pull images from"
    )


# ============================================================================
# Fixtures: Configuration
# ============================================================================

@pytest.fixture(scope="session")
def docker_registry(request: pytest.FixtureRequest) -> str:
    """Get Docker registry from command line or default."""
    return request.config.getoption("--registry")


@pytest.fixture(scope="session")
def test_versions(request: pytest.FixtureRequest) -> List[Dict[str, str]]:
    """
    Get version matrix for parametrized tests.

    Filters VERSION_MATRIX based on command line options.
    """
    docker_ver = request.config.getoption("--docker-version")
    k8s_ver = request.config.getoption("--k8s-version")
    cri_type = request.config.getoption("--cri-type")

    filtered = VERSION_MATRIX

    if docker_ver:
        filtered = [v for v in filtered if v["docker"] == docker_ver]
    if k8s_ver:
        filtered = [v for v in filtered if v["k8s"] == k8s_ver]
    if cri_type:
        filtered = [v for v in filtered if v["cri"] == cri_type]

    return filtered


# ============================================================================
# Fixtures: Docker Client
# ============================================================================

@pytest.fixture(scope="session")
def docker_client() -> docker.DockerClient:
    """Create a Docker client for the test session."""
    client = docker.from_env()
    yield client
    # No cleanup needed - client is managed by docker library


@pytest.fixture(scope="session")
def docker_cleanup(docker_client: docker.DockerClient) -> Generator[None, None, None]:
    """
    Session-level cleanup for Docker resources.

    Removes all test containers and networks created during the session.
    """
    yield

    # Cleanup: remove containers with test label
    try:
        containers = docker_client.containers.list(
            all=True,
            filters={"label": "k8s_in_dind_test=true"}
        )
        for container in containers:
            try:
                container.remove(force=True)
            except docker.errors.APIError:
                pass
    except docker.errors.DockerException:
        pass


# ============================================================================
# Fixtures: Test Environment
# ============================================================================

@pytest.fixture(scope="function")
def test_env(tmp_path) -> Dict[str, Any]:
    """
    Create an isolated test environment.

    Returns:
        Dict with paths and configuration for the test.
    """
    return {
        "workdir": str(tmp_path),
        "kubeconfig": str(tmp_path / "kubeconfig"),
        "logs_dir": str(tmp_path / "logs"),
    }


@pytest.fixture(scope="function")
def cleanup_containers(docker_client: docker.DockerClient) -> Generator[None, None, None]:
    """
    Function-level cleanup for containers created during a test.

    Yields and then removes containers created during the test.
    """
    # Track containers before test
    before = set(c.id for c in docker_client.containers.list(all=True))

    yield

    # Remove new containers with test label
    after = set(c.id for c in docker_client.containers.list(all=True))
    new_containers = after - before

    for cid in new_containers:
        try:
            container = docker_client.containers.get(cid)
            if container.labels and container.labels.get("k8s_in_dind_test"):
                container.remove(force=True)
        except docker.errors.APIError:
            pass


# ============================================================================
# Markers and Skip Logic
# ============================================================================

def pytest_configure(config: pytest.Config) -> None:
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires Docker)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "requires_cluster: mark test as requiring a running K8s cluster"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: List[pytest.Item]) -> None:
    """Skip tests based on markers and environment."""
    skip_integration = pytest.mark.skip(
        reason="Integration tests require DOCKER_HOST or --run-integration flag"
    )

    docker_available = _check_docker_available()

    for item in items:
        # Skip integration tests if Docker is not available
        if "integration" in item.keywords and not docker_available:
            item.add_marker(skip_integration)


def _check_docker_available() -> bool:
    """Check if Docker daemon is accessible."""
    try:
        client = docker.from_env()
        client.ping()
        return True
    except docker.errors.DockerException:
        return False
