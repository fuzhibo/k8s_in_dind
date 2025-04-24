#!/bin/sh
set -eu
# 需要进行配置参数的更改
# 这里就具体来执行安装

KUBEADM_INIT_WORKFLOW=${KUBEADM_INIT_WORKFLOW:-"disable"}
KUBEADM_JOIN_WORKFLOW=${KUBEADM_JOIN_WORKFLOW:-"disable"}
CNI_CATEGORY=${CNI_CATEGORY:-"calico"}
CNI_VERSION=${CNI_VERSION:-"calico-v3.29.3"}

if [ $KUBEADM_INIT_WORKFLOW = 'enable' ]; then
    kubeadm -v=5 init --config /kubeadm_install/kubeadm_init.yaml --ignore-preflight-errors=Swap,SystemVerification
    # 一旦完成创建，还需要应用 cni 插件，完成部署
    if [ $? -eq 0 ]; then
        mkdir -p $HOME/.kube
        cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
        chown $(id -u):$(id -g) $HOME/.kube/config
        kubectl cluster-info
        kubectl -n kube-system apply -f "/cni_repo/$CNI_CATEGORY/$CNI_VERSION.yaml"
    else
        echo "Faield to create kubernetes cluster, will not continue to create cni plugin."
    fi
elif [ $KUBEADM_JOIN_WORKFLOW = 'enable' ]; then
    kubeadm -v=5 join --config /kubeadm_install/kubeadm_join.yaml --ignore-preflight-errors=Swap,SystemVerification
fi
