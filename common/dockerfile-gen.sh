#!/bin/sh -x
set -eu
# 根据传入的配置参数生成 Dockerfile 用于不同版本的构建
: ${DOCKER_VERSION:=18.09.0}
: ${K8S_VERSION:=v1.12.0}
: ${DOCKER_REGISTRY:=ccr.ccs.tencentyun.com/fuzhibo}
: ${DOCKERFILE_PREFIX:="AutoDockerfile"}
: ${CONTAINERD_INDIVIDUALLY_START:="false"}
: ${CRI_TYPE:="auto"}
: ${CRICTL_TOOL_NEEDED:="false"}

# 根据 K8s 版本和 CRI 类型自动判断是否需要 crictl
# K8s v1.24+ 默认使用 containerd，需要 crictl
# 如果显式指定 CRI_TYPE=containerd，也需要 crictl
if [ "$CRICTL_TOOL_NEEDED" = 'false' ]; then
    # 检查是否是 K8s v1.24+
    K8S_MAJOR=$(echo "$K8S_VERSION" | sed 's/^v\?\([0-9]*\).*/\1/')
    K8S_MINOR=$(echo "$K8S_VERSION" | sed 's/^v\?[0-9]*\.\([0-9]*\).*/\1/')

    if [ "$K8S_MAJOR" -ge 1 ] && [ "$K8S_MINOR" -ge 24 ]; then
        CRICTL_TOOL_NEEDED='true'
        echo "INFO: K8s v1.24+ detected, enabling crictl installation"
    fi

    # 如果显式指定 containerd CRI，也需要 crictl
    if [ "$CRI_TYPE" = 'containerd' ]; then
        CRICTL_TOOL_NEEDED='true'
        echo "INFO: CRI_TYPE=containerd detected, enabling crictl installation"
    fi
fi

CONTEXTS=""

if [ $CONTAINERD_INDIVIDUALLY_START = 'true' ]
then
CONTAINERD_TOOL_CONTEXTS="
COPY docker-entrypoint.sh /usr/local/bin
COPY containerd-entrypoint.sh /usr/local/bin
COPY dockerd-entrypoint.sh /usr/local/bin
"
CONTEXTS="$CONTEXTS
$CONTAINERD_TOOL_CONTEXTS
"
fi

CRICTL_TOOL_CONTEXTS="
COPY crictl.yaml /etc/crictl.yaml
COPY crictl-install.sh /usr/local/bin
COPY crictl-*.tar.gz /tmp/
RUN chmod +x /usr/local/bin/crictl-install.sh && \
    VERSION=\$(ls /tmp/crictl-*.tar.gz 2>/dev/null | head -1 | sed 's/.*crictl-\\(.*\\)-linux-amd64.tar.gz/\\1/' || echo 'v1.23.0') && \
    /usr/local/bin/crictl-install.sh
"

if [ $CRICTL_TOOL_NEEDED = 'true' ]
then
CONTEXTS="$CONTEXTS
$CRICTL_TOOL_CONTEXTS
"
fi

# k8s 集群配置需要的工具
# 注意：containerd-entrypoint.sh 是必需的，因为 K8s v1.24+ 需要 containerd CRI
K8S_TOOL_CONTEXTS="
COPY k8s-cluster-check.sh /usr/local/bin
COPY k8s-cluster-create.sh /usr/local/bin
COPY kubelet-entrypoint.sh /usr/local/bin
COPY containerd-entrypoint.sh /usr/local/bin
COPY image-prepull.sh /usr/local/bin
"

CONTEXTS="$CONTEXTS
$K8S_TOOL_CONTEXTS
"

# 启动配置工具
BOOTSTRAP_CONTEXTS="
COPY env_configuration_modify_${DOCKER_VERSION}.py /usr/local/bin/env_configuration_modify.py
COPY preconfig_${DOCKER_VERSION}.sh /usr/local/bin/preconfig.sh
COPY start.sh /usr/local/bin
ADD cni_repo /cni_repo
"

CONTEXTS="$CONTEXTS
$BOOTSTRAP_CONTEXTS
"

# k8s 集群运行时需要的工具
K8S_BIN_CONTEXTS="
COPY kubelet /usr/bin
COPY kubeadm /usr/bin
COPY kubectl /usr/bin
"

if [ $K8S_VERSION = 'v1.12.0' ]
then
K8S_BIN_EXT_CONTEXTS="
RUN mkdir -p /lib/x86_64-linux-gnu && mkdir -p /lib64
COPY libc-2.24.so /lib/x86_64-linux-gnu
COPY ld-2.24.so /lib/x86_64-linux-gnu
COPY libdl-2.24.so /lib/x86_64-linux-gnu
COPY libpthread-2.24.so /lib/x86_64-linux-gnu
RUN ln -s /lib/x86_64-linux-gnu/libc-2.24.so /lib/x86_64-linux-gnu/libc.so.6 && ln -s /lib/x86_64-linux-gnu/libdl-2.24.so /lib/x86_64-linux-gnu/libdl.so.2 && ln -s /lib/x86_64-linux-gnu/libpthread-2.24.so /lib/x86_64-linux-gnu/libpthread.so.0 && ln -s /lib/x86_64-linux-gnu/ld-2.24.so /lib64/ld-linux-x86-64.so.2
"
K8S_BIN_CONTEXTS="
$K8S_BIN_CONTEXTS
$K8S_BIN_EXT_CONTEXTS
"
elif [ $K8S_VERSION = 'v1.16.15' ]
then
K8S_BIN_EXT_CONTEXTS="
RUN mkdir -p /lib/x86_64-linux-gnu && mkdir -p /lib64
COPY libc-2.28.so /lib/x86_64-linux-gnu
COPY ld-2.28.so /lib/x86_64-linux-gnu
COPY libdl-2.28.so /lib/x86_64-linux-gnu
COPY libpthread-2.28.so /lib/x86_64-linux-gnu
RUN ln -s /lib/x86_64-linux-gnu/libc-2.28.so /lib/x86_64-linux-gnu/libc.so.6 && ln -s /lib/x86_64-linux-gnu/libdl-2.28.so /lib/x86_64-linux-gnu/libdl.so.2 && ln -s /lib/x86_64-linux-gnu/libpthread-2.28.so /lib/x86_64-linux-gnu/libpthread.so.0 && ln -s /lib/x86_64-linux-gnu/ld-2.28.so /lib64/ld-linux-x86-64.so.2
"
K8S_BIN_CONTEXTS="
$K8S_BIN_CONTEXTS
$K8S_BIN_EXT_CONTEXTS
"
# v1.23.17 及更高版本不需要额外的动态库
fi

CONTEXTS="$CONTEXTS
$K8S_BIN_CONTEXTS
"

# 设置脚本执行权限
# v1.23.17 及更高版本需要设置脚本执行权限
CHMOD_CONTEXTS="
RUN chmod +x /usr/local/bin/k8s-cluster-check.sh && \
    chmod +x /usr/local/bin/k8s-cluster-create.sh && \
    chmod +x /usr/local/bin/kubelet-entrypoint.sh && \
    chmod +x /usr/local/bin/containerd-entrypoint.sh && \
    chmod +x /usr/local/bin/image-prepull.sh && \
    chmod +x /usr/local/bin/env_configuration_modify.py && \
    chmod +x /usr/local/bin/preconfig.sh && \
    chmod +x /usr/local/bin/start.sh
"

if [ "$K8S_VERSION" = 'v1.23.17' ] || echo "$K8S_VERSION" | grep -qE '^v1\.(2[4-9]|[3-9][0-9])'
then
CONTEXTS="$CONTEXTS
$CHMOD_CONTEXTS
"
fi

# 这里根据是否使用 containerd 作为集群运行时进行相应的配置选择

cat << EOF > "${DOCKERFILE_PREFIX}_${DOCKER_VERSION}_${K8S_VERSION}"
ARG DOCKER_REGISTRY=ccr.ccs.tencentyun.com/fuzhibo
ARG DOCKER_VERSION=18.09.0
ARG K8S_VERSION=1.12
FROM ${DOCKER_REGISTRY}/k8s-in-dind:base-${DOCKER_VERSION}

$CONTEXTS

VOLUME [ "/var/lib/docker" ]
ENTRYPOINT []
CMD ["start.sh"]
EOF
