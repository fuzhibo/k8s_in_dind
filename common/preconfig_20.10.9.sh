#!/bin/sh -x
set -eu
# Docker 20.10.9 版本的预配置脚本
# 使用 dockershim 作为 CRI，不配置 containerd

# 使用 kubeadm 生成相应的 kubeadm init 配置文件
[ -d /kubeadm_install ] || mkdir -p /kubeadm_install

[ -e /kubeadm_install/kubeadm_init.yaml ] || \
    (kubeadm config print init-defaults >/kubeadm_install/kubeadm_init.yaml)

[ -e /kubeadm_install/kubeadm_join.yaml ] || \
    (kubeadm config print join-defaults >/kubeadm_install/kubeadm_join.yaml)

# 使用 Python 脚本修改配置
# 1. kubeadm 的 init 以及 join 配置
# 2. kube-proxy 模式配置为 iptables
env_configuration_modify.py

# 强制同步配置到磁盘
fsync -d /kubeadm_install/kubeadm_init.yaml
fsync -d /kubeadm_install/kubeadm_join.yaml
