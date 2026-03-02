#!/bin/bash -x
# 可以在这里实现挂在构建容器进行编译的工作
set -eu
DOCKER_REGISTRY=${DOCKER_REGISTRY-"ccr.ccs.tencentyun.com/fuzhibo"}
DOCKER_VERSION=${DOCKER_VERSION-"23.0.5"}
K8S_VERSION=${K8S_VERSION-"v1.31.7"}
CRI_TYPE="${CRI_TYPE:-auto}"

# 修正 self_path 的计算逻辑
self_path=$(
    cd "$(dirname "$0")"
    pwd
)

# 清理之前可能残留的 AutoDockerfile 文件和 crictl tar 文件
rm -f "$self_path"/AutoDockerfile_*
rm -f "$self_path"/crictl-*.tar.gz
rm -f "$self_path"/crictl
echo "Cleaned up any existing AutoDockerfile_* and crictl files"

# 使用自动生成 dockerfile 的脚本
$self_path/dockerfile-gen.sh

# ============ 预下载 crictl（如果需要）============
CRICTL_VERSION="${CRICTL_VERSION:-v1.23.0}"
# 注意: crictl 版本需要与 K8s 版本和 containerd 版本兼容
# - containerd v1.4.x (Docker 20.10.x) 使用 CRI v1alpha2，需要 crictl v1.23.x
# - containerd v1.6+ (Docker 23.0.x) 使用 CRI v1，可以使用 crictl v1.26+

# 根据 Docker 版本选择兼容的 crictl 版本
DOCKER_MAJOR=$(echo "$DOCKER_VERSION" | cut -d. -f1)
DOCKER_MINOR=$(echo "$DOCKER_VERSION" | cut -d. -f2)

if [ "$DOCKER_MAJOR" -eq 20 ] && [ "$DOCKER_MINOR" -eq 10 ]; then
    # Docker 20.10.x 内置 containerd v1.4.x，需要 crictl v1.23.x
    CRICTL_VERSION="${CRICTL_VERSION:-v1.23.0}"
    echo "INFO: Docker 20.10.x detected, using crictl $CRICTL_VERSION (CRI v1alpha2 compatible)"
else
    # Docker 23.0.x+ 内置 containerd v1.6+，可以使用更新的 crictl
    CRICTL_VERSION="${CRICTL_VERSION:-v1.26.0}"
    echo "INFO: Docker $DOCKER_VERSION detected, using crictl $CRICTL_VERSION (CRI v1 compatible)"
fi

CRICTL_TAR="crictl-${CRICTL_VERSION}-linux-amd64.tar.gz"
CRICTL_URL="https://github.com/kubernetes-sigs/cri-tools/releases/download/${CRICTL_VERSION}/${CRICTL_TAR}"

# 检查是否需要 crictl（K8s v1.24+ 或 CRI_TYPE=containerd）
NEED_CRICTL="false"
K8S_MAJOR=$(echo "$K8S_VERSION" | sed 's/^v\?\([0-9]*\).*/\1/')
K8S_MINOR=$(echo "$K8S_VERSION" | sed 's/^v\?[0-9]*\.\([0-9]*\).*/\1/')

if [ "$K8S_MAJOR" -gt 1 ] || ([ "$K8S_MAJOR" -eq 1 ] && [ "$K8S_MINOR" -ge 24 ]); then
    NEED_CRICTL="true"
fi

if [ "$CRI_TYPE" = "containerd" ]; then
    NEED_CRICTL="true"
fi

if [ "$NEED_CRICTL" = "true" ]; then
    echo "INFO: Pre-downloading crictl ${CRICTL_VERSION} for K8s $K8S_VERSION..."

    MAX_RETRIES=10
    RETRY_COUNT=0
    DOWNLOAD_SUCCESS="false"

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "crictl download attempt $RETRY_COUNT of $MAX_RETRIES..."

        if curl --http1.1 -L --connect-timeout 30 --max-time 300 --retry 3 --retry-delay 5 \
            -o "$self_path/$CRICTL_TAR" "$CRICTL_URL"; then
            # 验证文件是否有效
            if [ -f "$self_path/$CRICTL_TAR" ] && tar -tzf "$self_path/$CRICTL_TAR" >/dev/null 2>&1; then
                DOWNLOAD_SUCCESS="true"
                echo "INFO: crictl downloaded successfully"
                break
            fi
        fi

        echo "WARN: crictl download failed, retrying in 10 seconds..."
        rm -f "$self_path/$CRICTL_TAR"
        sleep 10
    done

    if [ "$DOWNLOAD_SUCCESS" = "false" ]; then
        echo "ERROR: Failed to download crictl after $MAX_RETRIES attempts"
        exit 1
    fi
fi

# ============ 复制 K8s 二进制文件 ============
$self_path/cp_k8s_res.sh

# ============ 构建 Docker 镜像 ============
cd "$self_path"
# 根据不同的 docker 版本和 kuberntes 版本需要选择不同的构建脚本，因为不同的版本之间可能存在特有的流程
docker pull "$DOCKER_REGISTRY/k8s-in-dind:base-$DOCKER_VERSION" || docker build -f Dockerfile-base --build-arg DOCKER_VERSION=$DOCKER_VERSION -t "$DOCKER_REGISTRY/k8s-in-dind:base-$DOCKER_VERSION" .
docker build -f AutoDockerfile_${DOCKER_VERSION}_${K8S_VERSION} --no-cache --build-arg DOCKER_VERSION=$DOCKER_VERSION --build-arg DOCKER_REGISTRY=$DOCKER_REGISTRY -t "$DOCKER_REGISTRY/k8s-in-dind:$DOCKER_VERSION-$K8S_VERSION" .

# ============ 清理构建产物 ============
# 清理所有生成的 AutoDockerfile 文件
rm -f "$self_path"/AutoDockerfile_*
echo "Cleaned up all AutoDockerfile_* files"

# 清理预下载的 crictl 文件
rm -f "$self_path"/crictl-*.tar.gz
rm -f "$self_path"/crictl
echo "Cleaned up crictl files"

# 清理 K8s 二进制文件
rm -rf "$self_path/kubelet" "$self_path/kubectl" "$self_path/kubeadm"
if [ "$K8S_VERSION" = "v1.12.0" ]; then
    rm -rf "$self_path/ld-2.24.so" "$self_path/libc-2.24.so" "$self_path/libdl-2.24.so" "$self_path/libpthread-2.24.so"
elif [ "$K8S_VERSION" = "v1.16.15" ]; then
    rm -rf "$self_path/ld-2.28.so" "$self_path/libc-2.28.so" "$self_path/libdl-2.28.so" "$self_path/libpthread-2.28.so"
fi
cd -
