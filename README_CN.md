# k8s-in-dind

[English](./README.md)

在 Docker-in-Docker 容器中运行 Kubernetes 集群。**仅用于测试环境，请勿用于生产环境！**

## 项目简介

k8s-in-dind 允许您在 Docker 容器内运行完整的 Kubernetes 集群。适用于：

- CI/CD 流水线测试
- 开发环境
- Kubernetes 学习和实验

### 与 kind 的主要区别

| 特性 | k8s-in-dind | kind |
|------|-------------|------|
| cgroup namespace | 不需要 | 必需 |
| CRI 支持 | Docker 和 containerd | 仅 containerd |
| 运行时选项 | runc 和 sysbox-runc | 仅 containerd |

---

## 支持的版本

| Docker 版本 | Kubernetes 版本 | 默认 CRI | cgroup | 镜像标签 |
|-------------|-----------------|----------|--------|----------|
| 18.09.0 | v1.12.0, v1.16.15 | docker | 仅 v1 | `18.09.0-v1.16.15` |
| 20.10.9 | v1.23.17 | docker | v1/v2 | `20.10.9-v1.23.17` |
| 23.0.5 | v1.24.0 - v1.31.7 | containerd | v2 | `23.0.5-1.31.7` |

> **注意：** Kubernetes v1.18+ 开始支持 cgroup v2（v1.25 正式稳定）。20.10.9-v1.23.17 镜像使用 `cgroupfs` 驱动，可在 cgroup v1 和 v2 上运行。23.0.5 镜像需要 cgroup v2。

## 预构建镜像

以下镜像已预构建完成，可直接拉取使用：

```bash
# Kubernetes v1.31.7（最新版，containerd，cgroup v2）
docker pull ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:23.0.5-1.31.7

# Kubernetes v1.23.17（稳定版，docker，cgroup v1）
docker pull ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:20.10.9-v1.23.17

# Kubernetes v1.16.15（旧版本，docker，cgroup v1）
docker pull ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:18.09.0-v1.16.15

# Kubernetes v1.12.0（旧版本，docker，cgroup v1）
docker pull ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:18.09.0-1.12.0
```

| 镜像标签 | K8s 版本 | Docker 版本 | CRI | cgroup | 推荐场景 |
|----------|----------|-------------|-----|--------|----------|
| `23.0.5-1.31.7` | v1.31.7 | 23.0.5 | containerd | v2 | 最新特性，K8s v1.24+ |
| `20.10.9-v1.23.17` | v1.23.17 | 20.10.9 | docker | v1/v2 | **稳定版，推荐使用** |
| `18.09.0-v1.16.15` | v1.16.15 | 18.09.0 | docker | 仅 v1 | 旧版应用兼容 |
| `18.09.0-1.12.0` | v1.12.0 | 18.09.0 | docker | 仅 v1 | 非常旧的 K8s 版本 |

---

## 使用入门

### 环境要求

在宿主机上配置内核参数：

```bash
# /etc/sysctl.conf
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1

# 应用配置
sudo sysctl -p
```

### 容器运行时选项

| 运行时 | 特权模式 | product_uuid | 适用场景 |
|--------|----------|--------------|----------|
| **runc**（默认） | 必需 | 与宿主机共享 | 快速测试、单节点 |
| **sysbox-runc** | 不需要 | 每容器唯一 | 多节点集群、更好的隔离 |

> **注意：** 对于多节点集群，推荐使用 sysbox-runc，因为每个容器会获得唯一的 `product_uuid`。安装方法请参考 [Sysbox 安装指南](https://github.com/nestybox/sysbox)。

### 快速开始（推荐）

使用 sysbox-runc，配置静态 IP 和自定义 DNS：

```bash
# 1. 创建自定义网络（用于静态 IP 分配）
docker network create \
  --driver bridge \
  --subnet=172.20.0.0/16 \
  --gateway=172.20.0.1 \
  k8s-cluster-net

# 2. 创建自定义 DNS 配置（避免 CoreDNS 循环问题）
mkdir -p ~/k8s-dns-config
cat > ~/k8s-dns-config/resolv.conf << 'EOF'
nameserver 223.5.5.5
nameserver 8.8.8.8
search .
EOF

# 3. 启动 Master 节点
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

# 4. 等待集群初始化完成（2-5 分钟）
docker logs -f test-master

# 5. 验证集群状态
docker exec test-master kubectl get nodes
```

### 添加 Worker 节点

```bash
# 1. 从 Master 获取加入命令
docker exec test-master kubeadm token create --print-join-command

# 2. 启动 Worker 节点（将 <token> 和 <hash> 替换为上面的值）
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

# 3. 验证节点加入
docker exec test-master kubectl get nodes -o wide
```

### 使用 runc 运行时（默认 Docker）

runc 是 Docker 的默认运行时。它需要 `--privileged` 特权模式，且所有容器共享宿主机的 `product_uuid`。

#### runc 与 sysbox-runc 对比

| 特性 | runc | sysbox-runc |
|------|------|-------------|
| 安装方式 | 内置 | 需要单独安装 |
| 特权模式 | 必需 | 不需要 |
| product_uuid | 与宿主机共享 | 每容器唯一 |
| 安全隔离 | 标准 | 增强（用户命名空间） |
| 多节点集群 | 可能有问题 | 完全支持 |

> **注意：** 使用 runc 时，所有容器共享宿主机的 `product_uuid`。这可能导致多节点 Kubernetes 集群出现问题，因为节点可能无法被唯一标识。

#### 使用 runc 启动 Master 节点

```bash
# 1. 创建自定义网络（如尚未创建）
docker network create \
  --driver bridge \
  --subnet=172.20.0.0/16 \
  --gateway=172.20.0.1 \
  k8s-cluster-net

# 2. 创建 DNS 配置（如尚未创建）
mkdir -p ~/k8s-dns-config
cat > ~/k8s-dns-config/resolv.conf << 'EOF'
nameserver 223.5.5.5
nameserver 8.8.8.8
search .
EOF

# 3. 使用 runc 启动 Master 节点
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

# 4. 等待集群初始化完成（2-5 分钟）
docker logs -f test-master

# 5. 验证集群状态
docker exec test-master kubectl get nodes
```

#### 使用 runc 添加 Worker 节点

```bash
# 1. 从 Master 获取加入命令
docker exec test-master kubeadm token create --print-join-command

# 2. 启动 Worker 节点
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

#### 何时使用 runc

- 快速测试，无需安装额外软件
- 单节点集群
- 无法安装 sysbox-runc 的环境

---

## 注意事项

### 静态 IP（强烈推荐）

Kubernetes 证书绑定到 Master 节点的 IP 地址。如果容器重启后 IP 发生变化，集群将无法正常工作。**生产环境部署时务必使用静态 IP。**

### DNS 配置

使用自定义桥接网络时，Docker 内置 DNS（`127.0.0.11`）可能导致 CoreDNS 循环检测错误：

```
[FATAL] plugin/loop: Loop (127.0.0.1:46348 -> :53) detected for zone "."
```

**解决方案：** 挂载自定义的 `/etc/resolv.conf` 文件，指定外部 DNS 服务器（参见快速开始示例）。

### 容器重启恢复

集群在容器重启后会自动恢复：

```bash
# 停止容器
docker stop test-master

# 重启容器
docker start test-master

# 等待恢复（30-60 秒）
sleep 30

# 验证集群
docker exec test-master kubectl get nodes
```

**恢复提示：**

- 先启动 Master 节点，再启动 Worker 节点
- Master 恢复需要 30-60 秒，Worker 额外需要 30 秒
- 确保重启后静态 IP 保持不变

### CNI 选择

| CNI 插件 | 状态 | 说明 |
|----------|------|------|
| Flannel | 推荐 | 在 DinD 环境中运行良好 |
| Calico | 有限 | eBPF 功能需要特殊的挂载配置 |

#### 使用 Flannel（推荐）

Flannel 是 DinD 环境推荐的 CNI，无需特殊配置：

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

#### 使用 Calico

Calico 使用 eBPF，需要 `/sys/fs/bpf` 的双向挂载传播。在 DinD 环境中，`/sys` 默认以 `private` 方式挂载，这会阻止 Calico 正常工作。

**方案 1：自动修复（内置）**

镜像内置了自动挂载传播修复功能，请先尝试此方案：

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

# 检查日志中的挂载传播状态
docker logs test-master 2>&1 | grep -i "mount"
```

如果看到 `WARN: Failed to set /sys as rshared mount`，请使用方案 2。

**方案 2：手动挂载传播（如果自动修复失败）**

为 `/sys` 添加显式的挂载传播：

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

> **注意：** 如果 Calico 在您的 DinD 环境中仍有问题，建议改用 Flannel。Calico 的 eBPF 功能在嵌套容器环境中存在固有限制。

### 故障排查

```bash
# 检查节点状态
docker exec test-master kubectl get nodes -o wide

# 检查 Pod 状态
docker exec test-master kubectl get pods -A

# 查看容器日志
docker logs test-master --tail 100

# 检查 kubelet 状态
docker exec test-master systemctl status kubelet

# 检查 containerd 状态
docker exec test-master systemctl status containerd
```

---

## 配置参考

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `KUBEADM_K8S_VERSION` | 必需 | Kubernetes 版本（如 `v1.23.17`） |
| `KUBEADM_INIT_WORKFLOW` | - | Master 节点设置为 `enable` |
| `KUBEADM_JOIN_WORKFLOW` | - | Worker 节点设置为 `enable` |
| `CNI_CATEGORY` | `calico` | CNI 类型：`calico` 或 `flannel` |
| `CNI_VERSION` | `auto` | CNI 版本（根据 K8s 版本自动选择） |
| `CRI_TYPE` | `auto` | CRI 类型：`docker`、`containerd`、`auto` |
| `API_SERVER_ENDPOINT` | - | Worker 节点使用的 Master API 端点 |
| `BOOTSTRAP_TOKEN` | - | Worker 节点加入令牌 |
| `CA_CERT_HASHES` | - | Worker 节点使用的 CA 证书哈希 |
| `CONTAINERD_INDIVIDUALLY_START` | - | K8s v1.24+ 设置为 `true` |

### CNI 版本兼容性

| K8s 版本 | Flannel | Calico |
|----------|---------|--------|
| v1.12 - v1.16 | - | v3.14 |
| v1.19 - v1.24 | v0.22.0/v0.22.1 | v3.18 |
| v1.27+ | v0.22.1 | v3.29 |

---

## 构建自定义镜像

```bash
# 前置条件：从 Kubernetes 源码编译 kubeadm、kubectl、kubelet
# 参考：https://github.com/kubernetes/kubernetes/blob/master/docs/devel/building.md

export DOCKER_REGISTRY="your-registry"
export DOCKER_VERSION="23.0.5"
export K8S_VERSION="1.31.7"

bash -x ./common/build.sh
```

---

## 许可证

GPL-3.0 License
