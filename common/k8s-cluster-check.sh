#!/bin/sh
set -eu
# 这里主要就是检测相关的配置是否存在，如果不存在就进行创建

# 检查集群健康状态
check_cluster_health() {
    echo "=== 检查集群健康状态 ==="

    # 等待 API server 就绪
    local max_wait=60
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if kubectl get nodes --kubeconfig=/etc/kubernetes/admin.conf &>/dev/null; then
            echo "✅ API server 就绪"
            break
        fi
        echo "等待 API server 就绪... (${waited}/${max_wait}s)"
        sleep 3
        waited=$((waited + 3))
    done

    if [ $waited -ge $max_wait ]; then
        echo "⚠️ API server 未就绪，集群可能需要恢复"
        return 1
    fi

    # 检查节点状态
    local node_status=$(kubectl get nodes --kubeconfig=/etc/kubernetes/admin.conf -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")].status}' 2>/dev/null || echo "")
    if [ "$node_status" = "True" ]; then
        echo "✅ 节点状态正常"
        return 0
    else
        echo "⚠️ 节点状态异常: ${node_status:-Unknown}"
        return 1
    fi
}

# 主逻辑
if [ -e /etc/kubernetes/admin.conf ] && [ -d /var/lib/kubelet ]; then
    echo "检测到现有集群配置，检查健康状态..."
    if check_cluster_health; then
        echo "✅ 集群恢复成功"
    else
        echo "⚠️ 集群状态异常，尝试恢复..."
        # 不删除重建，kubelet 重启后会自动恢复
    fi
else
    echo "未检测到现有集群配置，开始创建集群..."
    k8s-cluster-create.sh
fi
