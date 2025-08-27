#!/bin/sh -x
set -eu
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
