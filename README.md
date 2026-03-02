# k8s-in-dind

[中文文档](./README_CN.md)

Run Kubernetes clusters inside Docker-in-Docker containers. **For testing purposes only, not for production!**

## Overview

k8s-in-dind allows you to run complete Kubernetes clusters inside Docker containers. It's perfect for:
- CI/CD pipeline testing
- Development environments
- Kubernetes learning and experimentation

### Key Differences from kind

| Feature | k8s-in-dind | kind |
|---------|-------------|------|
| cgroup namespace | Not required | Required |
| CRI support | Docker & containerd | containerd only |
| Runtime options | runc & sysbox-runc | containerd only |

---

## Supported Versions

| Docker Version | Kubernetes Versions | Default CRI | cgroup | Image Tag |
|----------------|---------------------|-------------|--------|-----------|
| 18.09.0 | v1.12.0, v1.16.15 | docker | v1 only | `18.09.0-v1.16.15` |
| 20.10.9 | v1.23.17 | docker | v1/v2 | `20.10.9-v1.23.17` |
| 23.0.5 | v1.24.0 - v1.31.7 | containerd | v2 | `23.0.5-1.31.7` |

> **Note:** Kubernetes v1.18+ supports cgroup v2 (GA in v1.25). The 20.10.9-v1.23.17 image uses `cgroupfs` driver and works on both cgroup v1 and v2. The 23.0.5 image requires cgroup v2.

## Pre-built Images

The following images are pre-built and ready to use:

```bash
# Kubernetes v1.31.7 (latest, containerd, cgroup v2)
docker pull ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:23.0.5-1.31.7

# Kubernetes v1.23.17 (stable, docker, cgroup v1)
docker pull ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:20.10.9-v1.23.17

# Kubernetes v1.16.15 (legacy, docker, cgroup v1)
docker pull ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:18.09.0-v1.16.15

# Kubernetes v1.12.0 (legacy, docker, cgroup v1)
docker pull ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:18.09.0-1.12.0
```

| Image Tag | K8s Version | Docker Version | CRI | cgroup | Recommended For |
|-----------|-------------|----------------|-----|--------|-----------------|
| `23.0.5-1.31.7` | v1.31.7 | 23.0.5 | containerd | v2 | Latest features, K8s v1.24+ |
| `20.10.9-v1.23.17` | v1.23.17 | 20.10.9 | docker | v1/v2 | **Stable, recommended** |
| `18.09.0-v1.16.15` | v1.16.15 | 18.09.0 | docker | v1 only | Legacy applications |
| `18.09.0-1.12.0` | v1.12.0 | 18.09.0 | docker | v1 only | Very old K8s versions |

---

## Getting Started

### Prerequisites

Configure kernel parameters on the host:

```bash
# /etc/sysctl.conf
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1

# Apply changes
sudo sysctl -p
```

### Container Runtime Options

| Runtime | Privileged Mode | product_uuid | Use Case |
|---------|-----------------|--------------|----------|
| **runc** (default) | Required | Shared with host | Quick testing, single-node |
| **sysbox-runc** | Not required | Unique per container | Multi-node clusters, better isolation |

> **Note:** For multi-node clusters, sysbox-runc is recommended because each container gets a unique `product_uuid`. See [Sysbox Installation](https://github.com/nestybox/sysbox) for details.

### Quick Start (Recommended)

Using sysbox-runc with static IP and custom DNS:

```bash
# 1. Create custom network for static IP allocation
docker network create \
  --driver bridge \
  --subnet=172.20.0.0/16 \
  --gateway=172.20.0.1 \
  k8s-cluster-net

# 2. Create custom DNS config (avoids CoreDNS loop issue)
mkdir -p ~/k8s-dns-config
cat > ~/k8s-dns-config/resolv.conf << 'EOF'
nameserver 8.8.8.8
nameserver 8.8.4.4
search .
EOF

# 3. Start master node
docker run --runtime=sysbox-runc -d --name test-master \
  --network k8s-cluster-net \
  --ip 172.20.0.2 \
  -v ~/k8s-dns-config/resolv.conf:/etc/resolv.conf:ro \
  -e CONTAINERD_INDIVIDUALLY_START="true" \
  -e KUBEADM_INIT_WORKFLOW="enable" \
  -e KUBEADM_K8S_VERSION="v1.23.17" \
  -e CNI_CATEGORY="flannel" \
  -v /lib/modules:/lib/modules \
  ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:20.10.9-v1.23.17

# 4. Wait for cluster initialization (2-5 minutes)
docker logs -f test-master

# 5. Verify cluster
docker exec test-master kubectl get nodes
```

### Adding Worker Nodes

```bash
# 1. Get join command from master
docker exec test-master kubeadm token create --print-join-command

# 2. Start worker node (replace <token> and <hash> with values from above)
docker run --runtime=sysbox-runc -d --name test-node-1 \
  --network k8s-cluster-net \
  --ip 172.20.0.3 \
  -v ~/k8s-dns-config/resolv.conf:/etc/resolv.conf:ro \
  -e CONTAINERD_INDIVIDUALLY_START="true" \
  -e KUBEADM_JOIN_WORKFLOW="enable" \
  -e KUBEADM_K8S_VERSION="v1.23.17" \
  -e API_SERVER_ENDPOINT="172.20.0.2:6443" \
  -e BOOTSTRAP_TOKEN="<token>" \
  -e CA_CERT_HASHES="sha256:<hash>" \
  -v /lib/modules:/lib/modules \
  ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:20.10.9-v1.23.17

# 3. Verify node joined
docker exec test-master kubectl get nodes -o wide
```

### Using runc Runtime (Default Docker)

runc is the default Docker runtime. It requires `--privileged` mode and all containers share the host's `product_uuid`.

#### runc vs sysbox-runc Comparison

| Feature | runc | sysbox-runc |
|---------|------|-------------|
| Installation | Built-in | Requires separate installation |
| Privileged mode | Required | Not required |
| product_uuid | Shared with host | Unique per container |
| Security isolation | Standard | Enhanced (user namespaces) |
| Multi-node clusters | May have issues | Fully supported |

> **Note:** With runc, all containers share the same `product_uuid` from the host. This may cause issues in multi-node Kubernetes clusters as nodes may not be uniquely identifiable.

#### Start Master Node with runc

```bash
# 1. Create custom network (if not already created)
docker network create \
  --driver bridge \
  --subnet=172.20.0.0/16 \
  --gateway=172.20.0.1 \
  k8s-cluster-net

# 2. Create DNS config (if not already created)
mkdir -p ~/k8s-dns-config
cat > ~/k8s-dns-config/resolv.conf << 'EOF'
nameserver 8.8.8.8
nameserver 8.8.4.4
search .
EOF

# 3. Start master node with runc
docker run --runtime=runc --privileged -d --name test-master \
  --network k8s-cluster-net \
  --ip 172.20.0.2 \
  -v ~/k8s-dns-config/resolv.conf:/etc/resolv.conf:ro \
  -e CONTAINERD_INDIVIDUALLY_START="true" \
  -e KUBEADM_INIT_WORKFLOW="enable" \
  -e KUBEADM_K8S_VERSION="v1.23.17" \
  -e CNI_CATEGORY="flannel" \
  -v /lib/modules:/lib/modules \
  ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:20.10.9-v1.23.17

# 4. Wait for cluster initialization (2-5 minutes)
docker logs -f test-master

# 5. Verify cluster
docker exec test-master kubectl get nodes
```

#### Add Worker Node with runc

```bash
# 1. Get join command from master
docker exec test-master kubeadm token create --print-join-command

# 2. Start worker node
docker run --runtime=runc --privileged -d --name test-node-1 \
  --network k8s-cluster-net \
  --ip 172.20.0.3 \
  -v ~/k8s-dns-config/resolv.conf:/etc/resolv.conf:ro \
  -e CONTAINERD_INDIVIDUALLY_START="true" \
  -e KUBEADM_JOIN_WORKFLOW="enable" \
  -e KUBEADM_K8S_VERSION="v1.23.17" \
  -e API_SERVER_ENDPOINT="172.20.0.2:6443" \
  -e BOOTSTRAP_TOKEN="<token>" \
  -e CA_CERT_HASHES="sha256:<hash>" \
  -v /lib/modules:/lib/modules \
  ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:20.10.9-v1.23.17
```

#### When to Use runc

- Quick testing without installing additional software
- Single-node clusters
- Environments where sysbox-runc is not available

---

## Important Notes

### Static IP (Highly Recommended)

Kubernetes certificates are bound to the master node's IP address. If the container restarts with a different IP, the cluster will fail. **Always use static IP for production-like deployments.**

### DNS Configuration

When using custom bridge networks, Docker's built-in DNS (`127.0.0.11`) may cause CoreDNS loop detection errors:

```
[FATAL] plugin/loop: Loop (127.0.0.1:46348 -> :53) detected for zone "."
```

**Solution:** Mount a custom `/etc/resolv.conf` with external DNS servers (as shown in Quick Start).

### Container Restart Recovery

The cluster automatically recovers after container restart:

```bash
# Stop container
docker stop test-master

# Restart container
docker start test-master

# Wait for recovery (30-60 seconds)
sleep 30

# Verify cluster
docker exec test-master kubectl get nodes
```

**Recovery tips:**
- Start master node first, then worker nodes
- Recovery takes 30-60 seconds for master, additional 30 seconds for workers
- Ensure static IP is preserved after restart

### CNI Selection

| CNI Plugin | Status | Notes |
|------------|--------|-------|
| Flannel | Recommended | Works well in DinD environments |
| Calico | Limited | Requires special mount configuration for eBPF |

#### Using Flannel (Recommended)

Flannel is the recommended CNI for DinD environments. No special configuration required:

```bash
docker run --runtime=sysbox-runc -d --name test-master \
  --network k8s-cluster-net \
  --ip 172.20.0.2 \
  -v ~/k8s-dns-config/resolv.conf:/etc/resolv.conf:ro \
  -e CONTAINERD_INDIVIDUALLY_START="true" \
  -e KUBEADM_INIT_WORKFLOW="enable" \
  -e KUBEADM_K8S_VERSION="v1.23.17" \
  -e CNI_CATEGORY="flannel" \
  -v /lib/modules:/lib/modules \
  ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:20.10.9-v1.23.17
```

#### Using Calico

Calico uses eBPF which requires bidirectional mount propagation for `/sys/fs/bpf`. In DinD environments, `/sys` is mounted as `private` by default, which prevents Calico from working properly.

**Option 1: Automatic Fix (Built-in)**

The image includes an automatic mount propagation fix. Try this first:

```bash
docker run --runtime=sysbox-runc -d --name test-master \
  --network k8s-cluster-net \
  --ip 172.20.0.2 \
  -v ~/k8s-dns-config/resolv.conf:/etc/resolv.conf:ro \
  -e CONTAINERD_INDIVIDUALLY_START="true" \
  -e KUBEADM_INIT_WORKFLOW="enable" \
  -e KUBEADM_K8S_VERSION="v1.31.7" \
  -e CNI_CATEGORY="calico" \
  -v /lib/modules:/lib/modules \
  ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:23.0.5-1.31.7

# Check logs for mount propagation status
docker logs test-master 2>&1 | grep -i "mount"
```

If you see `WARN: Failed to set /sys as rshared mount`, use Option 2.

**Option 2: Manual Mount Propagation (If automatic fix fails)**

Add explicit mount propagation for `/sys`:

```bash
docker run --runtime=sysbox-runc -d --name test-master \
  --network k8s-cluster-net \
  --ip 172.20.0.2 \
  --mount type=bind,src=/sys,dst=/sys,bind-propagation=rshared \
  -v ~/k8s-dns-config/resolv.conf:/etc/resolv.conf:ro \
  -e CONTAINERD_INDIVIDUALLY_START="true" \
  -e KUBEADM_INIT_WORKFLOW="enable" \
  -e KUBEADM_K8S_VERSION="v1.31.7" \
  -e CNI_CATEGORY="calico" \
  -v /lib/modules:/lib/modules \
  ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:23.0.5-1.31.7
```

> **Note:** If Calico continues to have issues in your DinD environment, consider using Flannel instead. Calico's eBPF features have inherent limitations in nested container environments.

### Troubleshooting

```bash
# Check node status
docker exec test-master kubectl get nodes -o wide

# Check pod status
docker exec test-master kubectl get pods -A

# Check container logs
docker logs test-master --tail 100

# Check kubelet status
docker exec test-master systemctl status kubelet

# Check containerd status
docker exec test-master systemctl status containerd
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KUBEADM_K8S_VERSION` | Required | Kubernetes version (e.g., `v1.23.17`) |
| `KUBEADM_INIT_WORKFLOW` | - | Set to `enable` for master node |
| `KUBEADM_JOIN_WORKFLOW` | - | Set to `enable` for worker node |
| `CNI_CATEGORY` | `calico` | CNI type: `calico` or `flannel` |
| `CNI_VERSION` | `auto` | CNI version (auto-select based on K8s version) |
| `CRI_TYPE` | `auto` | CRI type: `docker`, `containerd`, `auto` |
| `API_SERVER_ENDPOINT` | - | Master API endpoint for worker nodes |
| `BOOTSTRAP_TOKEN` | - | Join token for worker nodes |
| `CA_CERT_HASHES` | - | CA certificate hash for worker nodes |
| `CONTAINERD_INDIVIDUALLY_START` | - | Set to `true` for K8s v1.24+ |

### CNI Version Compatibility

| K8s Version | Flannel | Calico |
|-------------|---------|--------|
| v1.12 - v1.16 | - | v3.14 |
| v1.19 - v1.24 | v0.22.0/v0.22.1 | v3.18 |
| v1.27+ | v0.22.1 | v3.29 |

---

## Building Custom Images

```bash
# Prerequisites: Compile kubeadm, kubectl, kubelet from Kubernetes source
# See: https://github.com/kubernetes/kubernetes/blob/master/docs/devel/building.md

export DOCKER_REGISTRY="your-registry"
export DOCKER_VERSION="23.0.5"
export K8S_VERSION="1.31.7"

bash -x ./common/build.sh
```

---

## License

MIT License
