#!/bin/bash
# 可以在这里实现挂在构建容器进行编译的工作
set -eu
DOCKER_REGISTRY=${DOCKER_REGISTRY-"ccr.ccs.tencentyun.com/fuzhibo"}
DOCKER_VERSION=${DOCKER_VERSION-"23.0.5"}
K8S_VERSION=${K8S_VERSION-"1.31.7"}

# 修正 self_path 的计算逻辑
self_path=$(
    cd "$(dirname "$0")"
    pwd
)

# 将 kubernetes 的源码编译的结果复制到这里
cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubelet" "$self_path/kubelet"
cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubectl" "$self_path/kubectl"
cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubeadm" "$self_path/kubeadm"

# 检查 ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:base-$DOCKER_VERSION 镜像是否存在，不存在则构建
cd "$self_path"
docker pull "$DOCKER_REGISTRY/k8s-in-dind:base-$DOCKER_VERSION" || docker build -f Dockerfile-base --build-arg DOCKER_VERSION=$DOCKER_VERSION -t "$DOCKER_REGISTRY/k8s-in-dind:base-$DOCKER_VERSION" .
docker build --no-cache --build-arg DOCKER_VERSION=$DOCKER_VERSION --build-arg DOCKER_REGISTRY=$DOCKER_REGISTRY -t "$DOCKER_REGISTRY/k8s-in-dind:$DOCKER_VERSION-$K8S_VERSION" .
rm -rf "$self_path/kubelet" "$self_path/kubectl" "$self_path/kubeadm"
cd -
