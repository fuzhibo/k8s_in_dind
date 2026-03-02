"""
Docker helper utilities for k8s_in_dind tests.

Provides functions for:
- Container lifecycle management
- Image building and pulling
- Network operations
- Volume management
"""

import os
import time
import docker
from docker.errors import DockerException, APIError, ImageNotFound
from typing import Optional, List, Dict, Any, Generator


# ============================================================================
# Container Operations
# ============================================================================

def create_container(
    client: docker.DockerClient,
    image: str,
    name: str,
    privileged: bool = True,
    environment: Optional[Dict[str, str]] = None,
    volumes: Optional[Dict[str, Dict[str, str]]] = None,
    labels: Optional[Dict[str, str]] = None,
    network: Optional[str] = None,
    hostname: Optional[str] = None,
    runtime: Optional[str] = None,
) -> docker.models.containers.Container:
    """
    Create and start a Docker container.

    Args:
        client: Docker client
        image: Image name or ID
        name: Container name
        privileged: Run in privileged mode
        environment: Environment variables
        volumes: Volume mounts
        labels: Container labels
        network: Network to connect to
        hostname: Container hostname
        runtime: OCI runtime (e.g., runc, sysbox-runc)

    Returns:
        Container object

    Raises:
        DockerException: If container creation fails
    """
    kwargs: Dict[str, Any] = {
        "image": image,
        "name": name,
        "privileged": privileged,
        "detach": True,
    }

    if environment:
        kwargs["environment"] = environment
    if volumes:
        kwargs["volumes"] = volumes
    if labels:
        kwargs["labels"] = labels
    if network:
        kwargs["network"] = network
    if hostname:
        kwargs["hostname"] = hostname
    if runtime:
        kwargs["runtime"] = runtime

    return client.containers.run(**kwargs)


def wait_for_container(
    container: docker.models.containers.Container,
    status: str = "running",
    timeout: int = 60,
    interval: float = 1.0,
) -> bool:
    """
    Wait for container to reach a specific status.

    Args:
        container: Container object
        status: Target status ("running", "exited", etc.)
        timeout: Maximum wait time in seconds
        interval: Check interval in seconds

    Returns:
        True if status reached, False on timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        container.reload()
        if container.status == status:
            return True
        if container.status == "exited" and status != "exited":
            return False
        time.sleep(interval)
    return False


def exec_in_container(
    container: docker.models.containers.Container,
    command: str,
    timeout: int = 60,
) -> tuple[int, str]:
    """
    Execute a command in a container.

    Args:
        container: Container object
        command: Command to execute
        timeout: Command timeout in seconds (used for demux)

    Returns:
        Tuple of (exit_code, output)
    """
    try:
        exit_code, output = container.exec_run(command)
        return exit_code, output.decode("utf-8")
    except APIError as e:
        return -1, str(e)


def get_container_logs(
    container: docker.models.containers.Container,
    tail: int = 100,
) -> str:
    """
    Get container logs.

    Args:
        container: Container object
        tail: Number of lines to return

    Returns:
        Log output as string
    """
    try:
        return container.logs(tail=tail).decode("utf-8")
    except APIError:
        return ""


def remove_container(
    container: docker.models.containers.Container,
    force: bool = True,
    remove_volumes: bool = True,
) -> bool:
    """
    Remove a container.

    Args:
        container: Container object
        force: Force removal
        remove_volumes: Remove associated volumes

    Returns:
        True if removed successfully
    """
    try:
        container.remove(force=force, v=remove_volumes)
        return True
    except APIError:
        return False


# ============================================================================
# Image Operations
# ============================================================================

def pull_image(
    client: docker.DockerClient,
    image: str,
    timeout: int = 600,
) -> bool:
    """
    Pull a Docker image.

    Args:
        client: Docker client
        image: Image name with tag
        timeout: Pull timeout in seconds

    Returns:
        True if pull succeeded
    """
    try:
        client.images.pull(image, timeout=timeout)
        return True
    except (APIError, ImageNotFound):
        return False


def image_exists(
    client: docker.DockerClient,
    image: str,
) -> bool:
    """
    Check if an image exists locally.

    Args:
        client: Docker client
        image: Image name with tag

    Returns:
        True if image exists
    """
    try:
        client.images.get(image)
        return True
    except ImageNotFound:
        return False


def build_image(
    client: docker.DockerClient,
    path: str,
    tag: str,
    dockerfile: str = "Dockerfile",
    buildargs: Optional[Dict[str, str]] = None,
) -> Optional[docker.models.images.Image]:
    """
    Build a Docker image.

    Args:
        client: Docker client
        path: Build context path
        tag: Image tag
        dockerfile: Dockerfile name
        buildargs: Build arguments

    Returns:
        Image object if successful, None otherwise
    """
    try:
        image, _ = client.images.build(
            path=path,
            tag=tag,
            dockerfile=dockerfile,
            buildargs=buildargs,
            rm=True,
        )
        return image
    except (APIError, DockerException):
        return None


# ============================================================================
# Network Operations
# ============================================================================

def create_network(
    client: docker.DockerClient,
    name: str,
    driver: str = "bridge",
    labels: Optional[Dict[str, str]] = None,
) -> Optional[docker.models.networks.Network]:
    """
    Create a Docker network.

    Args:
        client: Docker client
        name: Network name
        driver: Network driver
        labels: Network labels

    Returns:
        Network object if successful, None otherwise
    """
    try:
        return client.networks.create(
            name=name,
            driver=driver,
            labels=labels or {},
        )
    except APIError:
        return None


def remove_network(
    network: docker.models.networks.Network,
) -> bool:
    """
    Remove a Docker network.

    Args:
        network: Network object

    Returns:
        True if removed successfully
    """
    try:
        network.remove()
        return True
    except APIError:
        return False


# ============================================================================
# Utility Functions
# ============================================================================

def get_container_ip(
    container: docker.models.containers.Container,
    network: str = "bridge",
) -> Optional[str]:
    """
    Get container IP address on a network.

    Args:
        container: Container object
        network: Network name

    Returns:
        IP address or None if not found
    """
    container.reload()
    networks = container.attrs.get("NetworkSettings", {}).get("Networks", {})
    if network in networks:
        return networks[network].get("IPAddress")
    return None


def list_test_containers(
    client: docker.DockerClient,
    label: str = "k8s_in_dind_test",
) -> List[docker.models.containers.Container]:
    """
    List all test containers.

    Args:
        client: Docker client
        label: Label to filter by

    Returns:
        List of container objects
    """
    try:
        return client.containers.list(
            all=True,
            filters={"label": label}
        )
    except APIError:
        return []


def cleanup_test_containers(
    client: docker.DockerClient,
    label: str = "k8s_in_dind_test",
) -> int:
    """
    Remove all test containers.

    Args:
        client: Docker client
        label: Label to filter by

    Returns:
        Number of containers removed
    """
    containers = list_test_containers(client, label)
    removed = 0
    for container in containers:
        if remove_container(container):
            removed += 1
    return removed
