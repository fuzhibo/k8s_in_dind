#!/bin/bash -x
# 可以在这里实现挂在构建容器进行编译的工作
set -eu
DOCKER_REGISTRY=${DOCKER_REGISTRY-"ccr.ccs.tencentyun.com/fuzhibo"}
DOCKER_VERSION=${DOCKER_VERSION-"23.0.5"}
K8S_VERSION=${K8S_VERSION-"v1.31.7"}

# 修正 self_path 的计算逻辑
self_path=$(
    cd "$(dirname "$0")"
    pwd
)

# 使用自动生成 dockerfile 的脚本
$self_path/dockerfile-gen.sh

# # 将 kubernetes 的源码编译的结果复制到这里
# cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubelet" "$self_path/kubelet"
# cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubectl" "$self_path/kubectl"
# cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubeadm" "$self_path/kubeadm"
# # 针对不同的版本，还需要拷贝不同的内容，以顺利构建

# if [ "$K8S_VERSION" = "1.12.0" ]; then
#     cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/ld-2.24.so" "$self_path/ld-2.24.so"
#     cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libc-2.24.so" "$self_path/libc-2.24.so"
#     cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libdl-2.24.so" "$self_path/libdl-2.24.so"
#     cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libpthread-2.24.so" "$self_path/libpthread-2.24.so"
# else if [ "$K8S_VERSION" = "1.16.15" ]; then
#     cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/ld-2.28.so" "$self_path/ld-2.28.so"
#     cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libc-2.28.so" "$self_path/libc-2.28.so"
#     cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libdl-2.28.so" "$self_path/libdl-2.28.so"
#     cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libpthread-2.28.so" "$self_path/libpthread-2.28.so"
# fi
$self_path/cp_k8s_res.sh

# 检查 ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:base-$DOCKER_VERSION 镜像是否存在，不存在则构建
cd "$self_path"
# 根据不同的 docker 版本和 kuberntes 版本需要选择不同的构建脚本，因为不同的版本之间可能存在特有的流程
docker pull "$DOCKER_REGISTRY/k8s-in-dind:base-$DOCKER_VERSION" || docker build -f Dockerfile-base --build-arg DOCKER_VERSION=$DOCKER_VERSION -t "$DOCKER_REGISTRY/k8s-in-dind:base-$DOCKER_VERSION" .
docker build -f AutoDockerfile_${DOCKER_VERSION}_${K8S_VERSION} --no-cache --build-arg DOCKER_VERSION=$DOCKER_VERSION --build-arg DOCKER_REGISTRY=$DOCKER_REGISTRY -t "$DOCKER_REGISTRY/k8s-in-dind:$DOCKER_VERSION-$K8S_VERSION" .
rm -rf "$self_path/kubelet" "$self_path/kubectl" "$self_path/kubeadm"
if [ "$K8S_VERSION" = "v1.12.0" ]; then
    rm -rf "$self_path/ld-2.24.so" "$self_path/libc-2.24.so" "$self_path/libdl-2.24.so" "$self_path/libpthread-2.24.so"
elif [ "$K8S_VERSION" = "v1.16.15" ]; then
    rm -rf "$self_path/ld-2.28.so" "$self_path/libc-2.28.so" "$self_path/libdl-2.28.so" "$self_path/libpthread-2.28.so"
elif [ "$K8S_VERSION" = "v1.23.17" ]; then
    # v1.23.17 不需要额外的动态库清理
    echo "No extra libraries to clean for K8S_VERSION=$K8S_VERSION"
fi
cd -
