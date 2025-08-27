#!/bin/sh -x
set -eu
# 使用 kubeadm 生成相应的 kubeadm init 配置文件
[ -d /kubeadm_install ] || mkdir -p /kubeadm_install
[ -e /kubeadm_install/kubeadm_init.yaml ] || (kubeadm config print-default >/kubeadm_install/kubeadm_init.yaml)
# 由于只有一个生成配置的方式，所以 join 就直接复制
[ -e /kubeadm_install/kubeadm_join.yaml ] || cp -arf /kubeadm_install/kubeadm_init.yaml /kubeadm_install/kubeadm_join.yaml

# 1. kubeadm 的 init 以及 join 配置
env_configuration_modify.py
# 这里不需要配置这个
# fsync -d /etc/containerd/config.toml
fsync -d /kubeadm_install/kubeadm_init.yaml
fsync -d /kubeadm_install/kubeadm_join.yaml
