#!/bin/sh -x
set -eu

# Kata Containers 存储初始化函数
# 使用 loop 设备 + ext4 解决 Kata 的 mount 权限问题
init_kata_storage() {
    echo "INFO: Detected Kata Containers runtime, initializing loop storage..."

    # 检查是否已经初始化
    if [ -f /var/lib/docker/.kata_initialized ]; then
        echo "INFO: Kata storage already initialized"
        return 0
    fi

    # 创建 loop 设备
    if [ ! -e /dev/loop0 ]; then
        mknod /dev/loop0 b 7 0 2>/dev/null || {
            echo "WARN: Failed to create /dev/loop0, trying alternative..."
        }
    fi

    # 设置磁盘镜像大小 (默认 20GB)
    DISK_SIZE="${KATA_DISK_SIZE:-20G}"
    DISK_IMG="/var/lib/docker-disk.img"

    echo "INFO: Creating ${DISK_SIZE} disk image for Docker storage..."

    # 创建稀疏磁盘镜像文件
    truncate -s ${DISK_SIZE} ${DISK_IMG} 2>/dev/null || {
        echo "ERROR: Failed to create disk image"
        return 1
    }

    # 格式化为 ext4
    mkfs.ext4 -F ${DISK_IMG} 2>/dev/null || {
        echo "ERROR: Failed to format disk image"
        return 1
    }

    # 创建挂载点
    mkdir -p /var/lib/docker

    # 挂载磁盘镜像
    mount -o loop ${DISK_IMG} /var/lib/docker 2>/dev/null || {
        echo "ERROR: Failed to mount disk image"
        return 1
    }

    # 标记初始化完成
    touch /var/lib/docker/.kata_initialized

    echo "INFO: Kata storage initialized successfully"
    return 0
}

# 检测是否使用 Kata Containers
detect_kata_runtime() {
    USE_KATA_CNT="${USE_KATA_CNT:-disable}"

    if [ "$USE_KATA_CNT" = "enable" ]; then
        echo "INFO: Kata Containers mode enabled"

        # 检查是否在 Kata VM 中运行（通过检查内核版本或特定标识）
        KERNEL_VERSION=$(uname -r)
        echo "INFO: Kernel version: ${KERNEL_VERSION}"

        # 初始化 Kata 存储如果检测到 VirtIO 设备或特定的 Kata 内核版本
        if [ -e /sys/class/dmi/id/product_name ] && grep -qi "kata" /sys/class/dmi/id/product_name 2>/dev/null; then
            echo "INFO: Running inside Kata VM"
            init_kata_storage || {
                echo "WARN: Kata storage init failed, continuing anyway..."
            }
        elif echo "$KERNEL_VERSION" | grep -q "kata\|6\.18\|6\.19"; then
            echo "INFO: Detected Kata kernel pattern"
            init_kata_storage || {
                echo "WARN: Kata storage init failed, continuing anyway..."
            }
        else
            # 强制启用模式（用户明确指定）
            echo "INFO: Force enabling Kata storage mode"
            init_kata_storage || {
                echo "WARN: Kata storage init failed, continuing anyway..."
            }
        fi
    fi
}

# Calico mount propagation 修复函数
# Calico 需要 bidirectional mount propagation 来挂载 bpffs
# 在 DinD 环境中，/sys 默认是 private mount，需要修复
fix_calico_mount_propagation() {
    CNI_CATEGORY="${CNI_CATEGORY:-calico}"

    if [ "$CNI_CATEGORY" = "calico" ]; then
        echo "INFO: Calico CNI detected, fixing mount propagation for /sys..."

        # 检查 /sys 是否已经是 shared mount
        if findmnt -n -o PROPAGATION /sys 2>/dev/null | grep -q "shared"; then
            echo "INFO: /sys is already a shared mount"
            return 0
        fi

        # 尝试将 /sys 设置为 rshared
        if mount --make-rshared /sys 2>/dev/null; then
            echo "INFO: Successfully set /sys as rshared mount"
        else
            echo "WARN: Failed to set /sys as rshared mount"
            echo "WARN: Calico may not work properly in DinD environment"
            echo "WARN: Consider running container with: --mount type=bind,src=/sys,dst=/sys,bind-propagation=rshared"
        fi

        # 确保 /sys/fs/bpf 目录存在
        mkdir -p /sys/fs/bpf 2>/dev/null || true
    fi
}

# CRI 类型检测函数
detect_cri_type() {
    CRI_TYPE="${CRI_TYPE:-auto}"
    K8S_VERSION="${KUBEADM_K8S_VERSION:-v1.31.7}"

    # 解析 K8s 版本号
    MAJOR=$(echo "$K8S_VERSION" | sed 's/v//' | cut -d. -f1)
    MINOR=$(echo "$K8S_VERSION" | sed 's/v//' | cut -d. -f2)

    # v1.24+ 移除了 dockershim，只能使用 containerd
    if [ "$MAJOR" -gt 1 ] || ([ "$MAJOR" -eq 1 ] && [ "$MINOR" -ge 24 ]); then
        if [ "$CRI_TYPE" = "auto" ]; then
            CRI_TYPE="containerd"
        elif [ "$CRI_TYPE" = "docker" ]; then
            echo "ERROR: K8s $K8S_VERSION does not support docker CRI (dockershim removed in v1.24)"
            echo "ERROR: Use CRI_TYPE=containerd instead"
            exit 1
        fi
    fi

    # 默认使用 docker
    if [ "$CRI_TYPE" = "auto" ]; then
        CRI_TYPE="docker"
    fi

    echo "INFO: CRI_TYPE=$CRI_TYPE, K8s version=$K8S_VERSION (major=$MAJOR, minor=$MINOR)"
    export CRI_TYPE
}

# 检测 CRI 类型
detect_cri_type

# 检测并初始化 Kata Containers 存储
detect_kata_runtime

# 修复 Calico mount propagation (DinD 环境需要)
fix_calico_mount_propagation

# 这里需要确定不同版本的 kubernetes 初始化使用的脚本是不同的
# 根据启动参数对配置进行一些提前的配置
preconfig.sh
# 配置成功了才能继续，否则就提前退出
if [ $? -ne 0 ]; then
    echo "preconfig failed, will not continue..."
    exit 1
fi

# 根据不同的 CRI 类型启动对应的守护进程
if [ "$CRI_TYPE" = "containerd" ]; then
    # 启动独立的 containerd 守护进程
    echo "INFO: Starting standalone containerd for K8s $KUBEADM_K8S_VERSION"
    containerd-entrypoint.sh &

    # 等待独立 containerd socket 就绪
    while ! [ -e /run/containerd/containerd.sock ]; do
        echo "Waiting for containerd to start (/run/containerd/containerd.sock)..."
        sleep 3
    done
    echo "INFO: containerd is ready"

    # 同时启动 Docker（用于支持 docker 命令）
    echo "INFO: Starting dockerd for docker CLI support"
    dockerd-entrypoint.sh &
    while ! [ -e /var/run/docker.sock ]; do
        echo "Waiting for dockerd to start..."
        sleep 3
    done
    echo "INFO: dockerd is ready"
else
    # Docker CRI 模式：启动 dockerd（内部包含 containerd）
    echo "INFO: Starting dockerd with embedded containerd (Docker CRI mode)"
    dockerd-entrypoint.sh &

    : ${CONTAINERD_INDIVIDUALLY_START:="false"}

    if [ $CONTAINERD_INDIVIDUALLY_START = 'true' ]; then
        # 我们需要等待 dockerd 和 containerd 都启动完成
        # 注意：在 Docker DinD 中，containerd socket 位于 /run/docker/containerd/containerd.sock
        while ! [ -e /run/docker/containerd/containerd.sock ] || ! [ -e /var/run/docker.sock ]; do
            echo "Waiting for dockerd and containerd to start..."
            sleep 3
        done
    else
        while ! [ -e /var/run/docker.sock ]; do
            echo "Waiting for dockerd to start..."
            sleep 3
        done
    fi
fi

# 预拉取所有必需的镜像（pause 镜像和 CNI 镜像）
# 支持重试机制，失败时明确报错退出
image-prepull.sh || {
    echo "ERROR: Image pre-pull failed, will not continue..."
    exit 1
}

# 这里要进行一些安装检测，如果发现没有安装 kubernetes 集群，就进行安装
k8s-cluster-check.sh &
# 然后进行 kubelet 的启动
exec kubelet-entrypoint.sh
