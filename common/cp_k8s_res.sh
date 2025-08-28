#!/bin/bash
set -eu
# 修正 self_path 的计算逻辑
self_path=$(
    cd "$(dirname "$0")"
    pwd
)

# 将 kubernetes 的源码编译的结果复制到这里
cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubelet" "$self_path/kubelet"
cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubectl" "$self_path/kubectl"
cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/kubeadm" "$self_path/kubeadm"
# 针对不同的版本，还需要拷贝不同的内容，以顺利构建

if [ "$K8S_VERSION" = "v1.12.0" ]; then
    cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/ld-2.24.so" "$self_path/ld-2.24.so"
    cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libc-2.24.so" "$self_path/libc-2.24.so"
    cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libdl-2.24.so" "$self_path/libdl-2.24.so"
    cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libpthread-2.24.so" "$self_path/libpthread-2.24.so"
elif [ "$K8S_VERSION" = "v1.16.15" ]; then
    cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/ld-2.28.so" "$self_path/ld-2.28.so"
    cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libc-2.28.so" "$self_path/libc-2.28.so"
    cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libdl-2.28.so" "$self_path/libdl-2.28.so"
    cp "$self_path/../../kubernetes/_output/local/bin/linux/amd64/libpthread-2.28.so" "$self_path/libpthread-2.28.so"
fi