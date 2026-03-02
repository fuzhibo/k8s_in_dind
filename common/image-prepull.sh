#!/bin/sh -x
set -eu
# 镜像预拉取脚本
# 在集群启动前预拉取所有必需的镜像，确保第一次部署即可成功
# 环境变量: CNI_CATEGORY, CNI_VERSION, KUBEADM_IMG_REGISTRY, KUBEADM_K8S_VERSION

# ============================================
# 环境变量配置
# ============================================
: ${CNI_CATEGORY:="calico"}
: ${CNI_VERSION:="auto"}
: ${CNI_IMG_REGISTRY:="ccr.ccs.tencentyun.com/fuzhibo"}
: ${KUBEADM_IMG_REGISTRY:="registry.aliyuncs.com/google_containers"}
: ${KUBEADM_K8S_VERSION:=""}
: ${MAX_RETRIES:=3}
: ${RETRY_INTERVAL:=5}

# ============================================
# 带重试的镜像拉取函数
# ============================================
pull_image_with_retry() {
    local image="$1"
    local retries=0

    while [ $retries -lt $MAX_RETRIES ]; do
        echo "Pulling image: $image (attempt $((retries+1))/$MAX_RETRIES)"
        if docker pull "$image"; then
            echo "Successfully pulled: $image"
            return 0
        fi
        retries=$((retries+1))
        [ $retries -lt $MAX_RETRIES ] && sleep $RETRY_INTERVAL
    done

    echo "ERROR: Failed to pull image after $MAX_RETRIES attempts: $image"
    return 1
}

# ============================================
# 预拉取 pause 镜像
# ============================================
prepull_pause() {
    echo "=== Pre-pulling pause image ==="
    local pause_image="${KUBEADM_IMG_REGISTRY}/pause:3.6"
    local target_image="registry.k8s.io/pause:3.6"

    if pull_image_with_retry "$pause_image"; then
        echo "Tagging pause image: $pause_image -> $target_image"
        docker tag "$pause_image" "$target_image" || echo "Warning: Failed to tag pause image"
        echo "Pause image ready"
        return 0
    fi

    echo "ERROR: Failed to prepare pause image"
    return 1
}

# ============================================
# CNI 版本自动选择
# ============================================
select_cni_version() {
    local k8s_version="${KUBEADM_K8S_VERSION}"
    local cni_category="${CNI_CATEGORY}"
    local cni_version="${CNI_VERSION}"

    # 用户明确指定版本
    if [ "$cni_version" != "auto" ]; then
        echo "$cni_version"
        return
    fi

    # 自动选择逻辑
    if [ "$cni_category" = "calico" ]; then
        if echo "$k8s_version" | grep -qE "^v1\.(1[0-9]|20)$"; then
            echo "calico_v3.14"
        elif echo "$k8s_version" | grep -qE "^v1\.(2[1-4])$"; then
            echo "calico_v3.18"
        else
            echo "calico_v3.29"
        fi
    elif [ "$cni_category" = "flannel" ]; then
        if echo "$k8s_version" | grep -qE "^v1\.23$"; then
            echo "flannel_v0.22.1"
        else
            echo "flannel_v0.22.0"
        fi
    else
        echo "ERROR: Unsupported CNI type '${cni_category}'" >&2
        return 1
    fi
}

# ============================================
# 预拉取 Calico CNI 镜像
# ============================================
prepull_calico() {
    local cni_version="${1}"
    echo "=== Pre-pulling Calico CNI images ==="
    echo "Calico version: ${cni_version}"

    local calico_version=""
    case "$cni_version" in
        calico_v3.14)
            calico_version="v3.14.2"
            ;;
        calico_v3.18)
            calico_version="v3.18.6"
            ;;
        calico_v3.29)
            calico_version="v3.29.3"
            ;;
        *)
            echo "ERROR: Unsupported Calico version '${cni_version}'"
            return 1
            ;;
    esac

    local images="
${CNI_IMG_REGISTRY}/calico-cni:${calico_version}
${CNI_IMG_REGISTRY}/calico-node:${calico_version}
${CNI_IMG_REGISTRY}/calico-kube-controllers:${calico_version}
"

    for image in $images; do
        [ -z "$image" ] && continue
        pull_image_with_retry "$image" || return 1
    done

    # calico-pod2daemon-flexvol may not be available in private registry, try official source
    local flexvol_image="${CNI_IMG_REGISTRY}/calico-pod2daemon-flexvol:${calico_version}"
    local official_flexvol="docker.io/calico/pod2daemon-flexvol:${calico_version}"
    if ! pull_image_with_retry "$flexvol_image"; then
        echo "Warning: Failed to pull $flexvol_image, trying official source..."
        if pull_image_with_retry "$official_flexvol"; then
            docker tag "$official_flexvol" "$flexvol_image" || true
            echo "Successfully tagged $official_flexvol as $flexvol_image"
        else
            echo "Warning: Could not pull calico-pod2daemon-flexvol, continuing anyway (non-critical)"
        fi
    fi

    echo "Calico CNI images ready"
    return 0
}

# ============================================
# 预拉取 Flannel CNI 镜像
# ============================================
prepull_flannel() {
    local cni_version="${1}"
    echo "=== Pre-pulling Flannel CNI images ==="
    echo "Flannel version: ${cni_version}"

    local flannel_version=""
    local cni_plugin_version=""
    case "$cni_version" in
        flannel_v0.22.1)
            flannel_version="v0.22.1"
            cni_plugin_version="v1.2.0"
            ;;
        flannel_v0.22.0)
            flannel_version="v0.22.0"
            cni_plugin_version="v1.2.0"
            ;;
        *)
            echo "ERROR: Unsupported Flannel version '${cni_version}'"
            return 1
            ;;
    esac

    local images="
${CNI_IMG_REGISTRY}/flannel:${flannel_version}
${CNI_IMG_REGISTRY}/flannel-cni-plugin:${cni_plugin_version}
"

    for image in $images; do
        [ -z "$image" ] && continue
        pull_image_with_retry "$image" || return 1
    done

    echo "Flannel CNI images ready"
    return 0
}

# ============================================
# 预拉取 CNI 镜像
# ============================================
prepull_cni() {
    echo "=== Pre-pulling CNI images ==="
    echo "CNI category: ${CNI_CATEGORY}"

    local cni_version
    cni_version=$(select_cni_version) || return 1
    echo "CNI version: ${cni_version}"

    case "$CNI_CATEGORY" in
        calico)
            prepull_calico "$cni_version" || return 1
            ;;
        flannel)
            prepull_flannel "$cni_version" || return 1
            ;;
        *)
            echo "ERROR: Unsupported CNI category '${CNI_CATEGORY}'"
            return 1
            ;;
    esac

    return 0
}

# ============================================
# 主函数
# ============================================
main() {
    echo "=========================================="
    echo "  Starting image pre-pull process"
    echo "=========================================="
    echo "CNI Category: ${CNI_CATEGORY}"
    echo "CNI Version: ${CNI_VERSION}"
    echo "K8s Version: ${KUBEADM_K8S_VERSION}"
    echo "Max Retries: ${MAX_RETRIES}"
    echo ""

    # 预拉取 pause 镜像
    prepull_pause || exit 1

    # 预拉取 CNI 镜像
    prepull_cni || exit 1

    echo ""
    echo "=========================================="
    echo "  All images pre-pulled successfully"
    echo "=========================================="
}

main "$@"
