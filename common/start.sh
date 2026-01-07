#!/bin/sh -x
set -eu
# 这里需要确定不同版本的 kubernetes 初始化使用的脚本是不同的
# 根据启动参数对配置进行一些提前的配置
preconfig.sh
# 配置成功了才能继续，否则就提前退出
if [ $? -ne 0 ]; then
    echo "preconfig failed, will not continue..."
    exit 1
fi
# 首先启动 dockerd，同时也将 containerd 也启动了
# （启动 containerd 需要依赖 CONTAINERD_INDIVIDUALLY_START 这个环境变量）
dockerd-entrypoint.sh &

: ${CONTAINERD_INDIVIDUALLY_START:="false"}

if [ $CONTAINERD_INDIVIDUALLY_START = 'true' ]; then
    # 我们需要等待 dockerd 和 containerd 都启动完成
    while ! [ -e /run/containerd/containerd.sock ] || ! [ -e /var/run/docker.sock ]; do
        echo "Waiting for dockerd and containerd to start..."
        sleep 3
    done
else
    while ! [ -e /var/run/docker.sock ]; do
        echo "Waiting for dockerd to start..."
        sleep 3
    done
fi

# 预拉取并重新标记 pause 镜像（解决 Docker 从 registry.k8s.io 拉取的问题）
echo "Pre-pulling pause image from Aliyun registry..."
IMG_REGISTRY=${KUBEADM_IMG_REGISTRY:-"registry.aliyuncs.com/google_containers"}
docker pull "${IMG_REGISTRY}/pause:3.6" || echo "Warning: Failed to pull pause image, will try again later..."
docker tag "${IMG_REGISTRY}/pause:3.6" registry.k8s.io/pause:3.6 || echo "Warning: Failed to tag pause image"

# 这里要进行一些安装检测，如果发现没有安装 kubernetes 集群，就进行安装
k8s-cluster-check.sh &
# 然后进行 kubelet 的启动
exec kubelet-entrypoint.sh
