#!/bin/sh -x
set -eu

# CRI_TYPE 验证函数
validate_cri_type() {
    CRI_TYPE="${CRI_TYPE:-auto}"
    K8S_VERSION="${KUBEADM_K8S_VERSION:-v1.31.7}"

    # 解析 K8s 版本号
    MAJOR=$(echo "$K8S_VERSION" | sed 's/v//' | cut -d. -f1)
    MINOR=$(echo "$K8S_VERSION" | sed 's/v//' | cut -d. -f2)

    # v1.24+ 移除了 dockershim，只能使用 containerd
    if [ "$MAJOR" -gt 1 ] || ([ "$MAJOR" -eq 1 ] && [ "$MINOR" -ge 24 ]); then
        if [ "$CRI_TYPE" = "docker" ]; then
            echo "ERROR: K8s $K8S_VERSION does not support docker CRI (dockershim removed in v1.24)"
            echo "ERROR: Use CRI_TYPE=containerd instead"
            exit 1
        fi
    fi

    echo "INFO: CRI_TYPE=$CRI_TYPE, K8s version=$K8S_VERSION (major=$MAJOR, minor=$MINOR)"
}

# 执行 CRI_TYPE 验证
validate_cri_type

# 可以先尝试通过 containerd 生成相应的配置文件
[ -d /etc/containerd ] || mkdir -p /etc/containerd
[ -e /etc/containerd/config.toml ] || (containerd config default >/etc/containerd/config.toml)
# 使用 kubeadm 生成相应的 kubeadm init 配置文件
[ -d /kubeadm_install ] || mkdir -p /kubeadm_install
[ -e /kubeadm_install/kubeadm_init.yaml ] || (kubeadm config print init-defaults >/kubeadm_install/kubeadm_init.yaml)
# 使用 kubeadm 生成相应的 kubeadm join 配置文件
[ -e /kubeadm_install/kubeadm_join.yaml ] || (kubeadm config print join-defaults >/kubeadm_install/kubeadm_join.yaml)

# 要考虑不同版本的 containerd 碎片化配置的问题
export CONTAINERD_VERSION=$(containerd --version)
# 1. containerd 的 config.toml 配置
# 2. kubeadm 的 init 以及 join 配置
env_configuration_modify.py
fsync -d /etc/containerd/config.toml
fsync -d /kubeadm_install/kubeadm_init.yaml
fsync -d /kubeadm_install/kubeadm_join.yaml
