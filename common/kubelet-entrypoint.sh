# !/bin/sh
set -eu
# 这里要做一些初始化的等待，比如等待一些特定的文件存在后，再进行提动
while [ ! -d /var/lib/kubelet ] || [ ! -e /var/lib/kubelet/config.yaml ]; do
    echo "Waiting for kubernetes config files..."
    sleep 3
done
# 在一些负载超大的环境下，如果不使用这个超时，很容易一次启动失败，所以统一加上，牺牲点启动速度
sleep 5
# 根据不同的版本选择不同的启动命令
# 由于 kubelet 启动可能会超时失败，所以这里加一个循环
for i in $(seq 10)
do
    if [ $KUBEADM_K8S_VERSION = 'v1.12.0' ] || [ $KUBEADM_K8S_VERSION = 'v1.16.15' ]
    then
        # 旧版本：添加 --network-plugin=cni 以使用 CNI 网络插件
        # 如果不配置此参数，kubelet 会使用默认的 cbr0（Docker 网桥）
        /usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf --config=/var/lib/kubelet/config.yaml --runtime-cgroups=/k8s/system.slice --pod-infra-container-image registry.aliyuncs.com/google_containers/pause:3.1 --network-plugin=cni
    else
        # v1.23+ 版本：添加 --network-plugin=cni 以使用 CNI 网络插件
        # 如果不配置此参数，kubelet 会使用默认的容器运行时网络
        /usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf --config=/var/lib/kubelet/config.yaml --runtime-cgroups=/k8s/system.slice --network-plugin=cni
    fi
    sleep 3
done
