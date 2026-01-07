#!/bin/sh
set -eu
# Kubernetes 集群创建脚本
# 支持 CNI 插件自动安装和版本选择

# ============================================
# 环境变量配置
# ============================================
KUBEADM_INIT_WORKFLOW=${KUBEADM_INIT_WORKFLOW:-"disable"}
KUBEADM_JOIN_WORKFLOW=${KUBEADM_JOIN_WORKFLOW:-"disable"}
KUBEADM_K8S_VERSION=${KUBEADM_K8S_VERSION:-""}

# CNI 插件配置
CNI_CATEGORY=${CNI_CATEGORY:-"calico"}
CNI_VERSION=${CNI_VERSION:-"auto"}

# ============================================
# CNI 版本自动选择
# ============================================
select_cni_version() {
    local k8s_version="${KUBEADM_K8S_VERSION}"
    local cni_category="${CNI_CATEGORY}"
    local cni_version="${CNI_VERSION}"

    echo "=== CNI 插件选择 ===" >&2
    echo "K8s 版本: ${k8s_version}" >&2
    echo "CNI 类型: ${cni_category}" >&2

    # 用户明确指定版本
    if [ "$cni_version" != "auto" ]; then
        echo "用户指定的 CNI 版本: ${cni_version}" >&2
        echo "${cni_version}"
        return
    fi

    # 自动选择逻辑
    if [ "$cni_category" = "calico" ]; then
        if echo "$k8s_version" | grep -qE "^v1\.(1[0-9]|20)$"; then
            # v1.10 - v1.20: Calico v3.14
            echo "自动选择 CNI: calico_v3.14 (v1.10-v1.20)" >&2
            echo "calico_v3.14"
        elif echo "$k8s_version" | grep -qE "^v1\.(2[1-4])$"; then
            # v1.21 - v1.24: Calico v3.18
            echo "自动选择 CNI: calico_v3.18 (v1.21-v1.24)" >&2
            echo "calico_v3.18"
        else
            # v1.25+: Calico v3.29
            echo "自动选择 CNI: calico_v3.29 (v1.25+)" >&2
            echo "calico_v3.29"
        fi
    elif [ "$cni_category" = "flannel" ]; then
        # Flannel 版本选择
        if echo "$k8s_version" | grep -qE "^v1\.23$"; then
            # v1.23: Flannel v0.22.1
            echo "自动选择 CNI: flannel_v0.22.1 (v1.23)" >&2
            echo "flannel_v0.22.1"
        elif echo "$k8s_version" | grep -qE "^v1\.(1[0-9]|2[0-2])$"; then
            # v1.10 - v1.22: Flannel v0.22.0
            echo "自动选择 CNI: flannel_v0.22.0 (v1.10-v1.22)" >&2
            echo "flannel_v0.22.0"
        else
            # v1.24+: Flannel v0.22.0 (当前集成版本)
            echo "自动选择 CNI: flannel_v0.22.0 (默认)" >&2
            echo "flannel_v0.22.0"
        fi
    else
        echo "❌ 错误: 不支持的 CNI 类型 '${cni_category}'" >&2
        exit 1
    fi
}

# ============================================
# CNI 版本验证
# ============================================
validate_cni_version() {
    local cni_category="${CNI_CATEGORY}"
    local cni_version="${1}"
    local k8s_version="${KUBEADM_K8S_VERSION}"

    echo "=== CNI 版本验证 ==="

    # 检查 CNI YAML 文件是否存在
    local cni_file="/cni_repo/${cni_category}/${cni_version}.yaml"
    if [ ! -f "$cni_file" ]; then
        echo "❌ 错误: CNI 配置文件不存在: ${cni_file}"
        echo "   请检查 CNI_CATEGORY 和 CNI_VERSION 配置"
        echo "   当前目录内容:"
        ls -la /cni_repo/ 2>/dev/null || echo "   /cni_repo 目录不存在"
        [ -d "/cni_repo/${cni_category}" ] && ls -la "/cni_repo/${cni_category}/" 2>/dev/null
        exit 1
    fi

    echo "✅ CNI 配置文件存在: ${cni_file}"

    # 版本兼容性验证（警告）
    case "$cni_category" in
        calico)
            case "$cni_version" in
                calico_v3.14)
                    if ! echo "$k8s_version" | grep -qE "^v1\.(1[0-9]|20)$"; then
                        echo "⚠️  警告: Calico v3.14 推荐用于 K8s v1.10-v1.20"
                    fi
                    ;;
                calico_v3.18)
                    if ! echo "$k8s_version" | grep -qE "^v1\.(1[9-9]|2[0-4])$"; then
                        echo "⚠️  警告: Calico v3.18 推荐用于 K8s v1.19-v1.24"
                    fi
                    ;;
                calico_v3.29)
                    if ! echo "$k8s_version" | grep -qE "^v1\.(2[5-9]|[3-9][0-9])$"; then
                        echo "⚠️  警告: Calico v3.29 推荐用于 K8s v1.25+"
                    fi
                    ;;
                *)
                    echo "❌ 错误: 不支持的 Calico 版本 '${cni_version}'"
                    exit 1
                    ;;
            esac
            ;;
        flannel)
            case "$cni_version" in
                flannel_v0.22.1)
                    if ! echo "$k8s_version" | grep -qE "^v1\.23$"; then
                        echo "⚠️  警告: Flannel v0.22.1 推荐用于 K8s v1.23"
                    fi
                    ;;
                flannel_v0.22.0)
                    if ! echo "$k8s_version" | grep -qE "^v1\.(1[0-9]|2[0-5])$"; then
                        echo "⚠️  警告: Flannel v0.22.0 推荐用于 K8s v1.10-v1.25"
                    fi
                    ;;
                *)
                    echo "❌ 错误: 不支持的 Flannel 版本 '${cni_version}'"
                    echo "   当前支持的版本: flannel_v0.22.0, flannel_v0.22.1"
                    exit 1
                    ;;
            esac
            ;;
        *)
            echo "❌ 错误: 不支持的 CNI 类型 '${cni_category}'"
            exit 1
            ;;
    esac

    echo "✅ CNI 版本验证通过"
}

# ============================================
# 等待集群就绪
# ============================================
wait_for_cluster_ready() {
    local max_wait=300
    local waited=0
    local interval=5

    echo "=== 等待集群就绪 ==="

    while [ $waited -lt $max_wait ]; do
        if kubectl get nodes &>/dev/null; then
            echo "✅ 集群已就绪"
            return 0
        fi

        echo "等待集群就绪... (${waited}/${max_wait}s)"
        sleep $interval
        waited=$((waited + interval))
    done

    echo "❌ 错误: 集群就绪超时 (${max_wait}s)"
    return 1
}

# ============================================
# 等待 CNI Pod 就绪
# ============================================
wait_for_cni_pods() {
    local cni_category="${1}"
    local max_wait=300
    local waited=0
    local interval=5

    echo "=== 等待 CNI Pod 就绪 ==="

    # 根据 CNI 类型确定命名空间
    local namespace="kube-system"
    if [ "$cni_category" = "flannel" ]; then
        namespace="kube-flannel"
    fi

    while [ $waited -lt $max_wait ]; do
        # 检查 Pod 状态
        local not_ready=$(kubectl get pods -n "$namespace" -o json 2>/dev/null | \
            jq -r '.items[] | select(.metadata.namespace=="'"$namespace"'") | select(.status.phase!="Running" or (.status.containerStatuses // [] | any(.ready != true))) | .metadata.name' 2>/dev/null || echo "")

        if [ -z "$not_ready" ]; then
            echo "✅ 所有 CNI Pod 已就绪"
            kubectl get pods -n "$namespace"
            return 0
        fi

        echo "等待以下 Pod 就绪: $not_ready (${waited}/${max_wait}s)"
        sleep $interval
        waited=$((waited + interval))
    done

    echo "⚠️  警告: CNI Pod 就绪超时，但集群可能仍然可用"
    kubectl get pods -n "$namespace"
    return 0
}

# ============================================
# 安装 CNI 插件
# ============================================
install_cni_plugin() {
    local cni_category="${1}"
    local cni_version="${2}"

    echo "=== 安装 CNI 插件 ==="
    echo "CNI 类型: ${cni_category}"
    echo "CNI 版本: ${cni_version}"

    local cni_file="/cni_repo/${cni_category}/${cni_version}.yaml"

    # 应用 CNI 配置
    echo "正在应用 CNI 配置: ${cni_file}"
    if kubectl apply -f "$cni_file"; then
        echo "✅ CNI 配置应用成功"
    else
        echo "❌ 错误: CNI 配置应用失败"
        return 1
    fi

    # 等待 CNI Pod 就绪
    wait_for_cni_pods "$cni_category"

    # 显示 CNI 状态
    echo "=== CNI 安装完成 ==="
    kubectl get pods -A | grep -E "${cni_category}|calico|flannel" || true

    return 0
}

# ============================================
# Master 节点初始化流程
# ============================================
master_init_workflow() {
    echo "=== 开始 Master 节点初始化 ==="

    # 根据版本使用不同的启动流程
    if [ "$KUBEADM_K8S_VERSION" = 'v1.12.0' ] || [ "$KUBEADM_K8S_VERSION" = 'v1.16.15' ]; then
        kubeadm -v=5 init --config /kubeadm_install/kubeadm_init.yaml \
            --ignore-preflight-errors=Swap,SystemVerification,FileContent--proc-sys-net-bridge-bridge-nf-call-iptables
    else
        # v1.23.17+ 从源码编译时需要忽略 KubeletVersion 检查（版本字符串为 v0.0.0-master）
        kubeadm -v=5 init --config /kubeadm_install/kubeadm_init.yaml \
            --ignore-preflight-errors=Swap,SystemVerification,KubeletVersion
    fi

    if [ $? -ne 0 ]; then
        echo "❌ 错误: Kubernetes 集群创建失败"
        return 1
    fi

    echo "✅ Kubernetes 集群创建成功"

    # 配置 kubectl
    mkdir -p $HOME/.kube
    cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
    chown $(id -u):$(id -g) $HOME/.kube/config

    # 显示集群信息
    kubectl cluster-info
    echo ""

    # 等待集群就绪
    wait_for_cluster_ready

    # 自动选择和验证 CNI 版本
    CNI_VERSION=$(select_cni_version)
    export CNI_VERSION

    validate_cni_version "$CNI_VERSION"

    # 安装 CNI 插件
    install_cni_plugin "$CNI_CATEGORY" "$CNI_VERSION"

    echo ""
    echo "=== Master 节点初始化完成 ==="
    echo "可以使用以下命令查看集群状态:"
    echo "  kubectl get nodes"
    echo "  kubectl get pods -A"
}

# ============================================
# Node 节点加入流程
# ============================================
node_join_workflow() {
    echo "=== 开始 Node 节点加入 ==="

    # 根据版本使用不同的启动流程
    if [ "$KUBEADM_K8S_VERSION" = 'v1.12.0' ] || [ "$KUBEADM_K8S_VERSION" = 'v1.16.15' ]; then
        kubeadm -v=5 join --config /kubeadm_install/kubeadm_join.yaml \
            --ignore-preflight-errors=Swap,SystemVerification,FileContent--proc-sys-net-bridge-bridge-nf-call-iptables
    else
        kubeadm -v=5 join --config /kubeadm_install/kubeadm_join.yaml \
            --ignore-preflight-errors=Swap,SystemVerification
    fi

    if [ $? -eq 0 ]; then
        echo "✅ Node 节点加入成功"
    else
        echo "❌ 错误: Node 节点加入失败"
        return 1
    fi
}

# ============================================
# 主流程
# ============================================
main() {
    echo "=========================================="
    echo "  Kubernetes 集群创建脚本"
    echo "=========================================="
    echo "K8s 版本: ${KUBEADM_K8S_VERSION}"
    echo "工作流: INIT=${KUBEADM_INIT_WORKFLOW}, JOIN=${KUBEADM_JOIN_WORKFLOW}"
    echo ""

    if [ "$KUBEADM_INIT_WORKFLOW" = 'enable' ]; then
        master_init_workflow
    elif [ "$KUBEADM_JOIN_WORKFLOW" = 'enable' ]; then
        node_join_workflow
    else
        echo "未启用任何工作流，脚本退出"
        echo "请设置 KUBEADM_INIT_WORKFLOW=enable 或 KUBEADM_JOIN_WORKFLOW=enable"
    fi
}

# 执行主流程
main "$@"
