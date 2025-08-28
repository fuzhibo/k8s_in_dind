#!/bin/sh -x
set -eu
# 使用 kubeadm 生成相应的 kubeadm init 配置文件
[ -d /kubeadm_install ] || mkdir -p /kubeadm_install

if [ "$KUBEADM_K8S_VERSION" = 'v1.12.0' ]
then
    [ -e /kubeadm_install/kubeadm_init.yaml ] || (kubeadm config print-default >/kubeadm_install/kubeadm_init.yaml)
    # 由于只有一个生成配置的方式，所以 join 就直接复制
    [ -e /kubeadm_install/kubeadm_join.yaml ] || cp -arf /kubeadm_install/kubeadm_init.yaml /kubeadm_install/kubeadm_join.yaml
elif [ "$KUBEADM_K8S_VERSION" = 'v1.16.15' ]
then
    [ -e /kubeadm_install/kubeadm_init.yaml ] || (kubeadm config print init-defaults >/kubeadm_install/kubeadm_init.yaml)
    # 使用 kubeadm 生成相应的 kubeadm join 配置文件
    [ -e /kubeadm_install/kubeadm_join.yaml ] || (kubeadm config print join-defaults >/kubeadm_install/kubeadm_join.yaml)
fi

# 1. kubeadm 的 init 以及 join 配置
env_configuration_modify.py
# 这里不需要配置这个
# fsync -d /etc/containerd/config.toml
fsync -d /kubeadm_install/kubeadm_init.yaml
fsync -d /kubeadm_install/kubeadm_join.yaml
