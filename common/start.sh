#!/bin/sh -x
set -eu

# 根据启动参数对配置进行一些提前的配置
preconfig.sh
# 配置成功了才能继续，否则就提前退出
if [ $? -ne 0 ]; then
    echo "preconfig failed, will not continue..."
    exit 1
fi
# 首先启动 dockerd，同时也将 containerd 也启动了
dockerd-entrypoint.sh &
# 我们需要等待 dockerd 和 containerd 都启动完成
while ! [ -e /run/containerd/containerd.sock ] || ! [ -e /var/run/docker.sock ]; do
    echo "Waiting for dockerd and containerd to start..."
    sleep 3
done
# 这里要进行一些安装检测，如果发现没有安装 kubernetes 集群，就进行安装
k8s-cluster-check.sh &
# 然后进行 kubelet 的启动
exec kubelet-entrypoint.sh
