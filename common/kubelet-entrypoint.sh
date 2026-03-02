# !/bin/sh
set -eu
# 这里要做一些初始化的等待，比如等待一些特定的文件存在后，再进行提动

# 等待 kubelet 配置文件存在
while [ ! -d /var/lib/kubelet ] || [ ! -e /var/lib/kubelet/config.yaml ]; do
    echo "Waiting for kubernetes config files..."
    sleep 3
done

# 如果集群已存在，等待 API server 就绪
if [ -e /etc/kubernetes/admin.conf ]; then
    echo "检测到现有集群配置，等待 API server 就绪..."
    for i in $(seq 20); do
        if kubectl get nodes --kubeconfig=/etc/kubernetes/admin.conf &>/dev/null; then
            echo "✅ API server 就绪"
            break
        fi
        echo "等待 API server 就绪... (${i}/20)"
        sleep 3
    done
fi

# 检测 CRI 类型和版本
detect_cri_type() {
    CRI_TYPE="${CRI_TYPE:-auto}"
    K8S_VERSION="${KUBEADM_K8S_VERSION:-v1.31.7}"
    MAJOR=$(echo "$K8S_VERSION" | sed 's/v//' | cut -d. -f1)
    MINOR=$(echo "$K8S_VERSION" | sed 's/v//' | cut -d. -f2)

    if [ "$MAJOR" -gt 1 ] || ([ "$MAJOR" -eq 1 ] && [ "$MINOR" -ge 24 ]); then
        # K8s v1.24+ 不再支持 dockershim，必须使用 containerd
        if [ "$CRI_TYPE" = "auto" ]; then
            CRI_TYPE="containerd"
        elif [ "$CRI_TYPE" = "docker" ]; then
            echo "ERROR: K8s $K8S_VERSION does not support docker CRI (dockershim removed)"
            exit 1
        fi
    else
        # K8s v1.23 及以下版本默认使用 docker
        if [ "$CRI_TYPE" = "auto" ]; then
            CRI_TYPE="docker"
        fi
    fi
    export CRI_TYPE
    echo "检测到 CRI 类型: $CRI_TYPE (K8s $K8S_VERSION)"
}

# 等待 CRI socket 就绪
wait_for_cri_socket() {
    if [ "$CRI_TYPE" = "containerd" ]; then
        echo "等待 containerd socket..."
        for i in $(seq 30); do
            if [ -e /run/containerd/containerd.sock ]; then
                echo "✅ containerd socket 就绪"
                return 0
            fi
            sleep 2
        done
        echo "ERROR: containerd socket 超时"
        exit 1
    fi
}

detect_cri_type
wait_for_cri_socket

# 在一些负载超大的环境下，如果不使用这个超时，很容易一次启动失败，所以统一加上，牺牲点启动速度
sleep 5
# 根据不同的版本和 CRI 类型选择不同的启动命令
# 由于 kubelet 启动可能会超时失败，所以这里加一个循环
for i in $(seq 10)
do
    if [ "$KUBEADM_K8S_VERSION" = 'v1.12.0' ] || [ "$KUBEADM_K8S_VERSION" = 'v1.16.15' ]
    then
        # 旧版本：添加 --network-plugin=cni 以使用 CNI 网络插件
        # 如果不配置此参数，kubelet 会使用默认的 cbr0（Docker 网桥）
        /usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf --config=/var/lib/kubelet/config.yaml --runtime-cgroups=/k8s/system.slice --pod-infra-container-image registry.aliyuncs.com/google_containers/pause:3.1 --network-plugin=cni
    elif [ "$CRI_TYPE" = "containerd" ]; then
        # v1.24+ 版本使用 containerd CRI
        /usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf --config=/var/lib/kubelet/config.yaml --runtime-cgroups=/k8s/system.slice --container-runtime-endpoint=unix:///run/containerd/containerd.sock
    else
        # v1.23 及以下版本使用 docker CRI (dockershim)
        /usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf --config=/var/lib/kubelet/config.yaml --runtime-cgroups=/k8s/system.slice --network-plugin=cni
    fi
    sleep 3
done
