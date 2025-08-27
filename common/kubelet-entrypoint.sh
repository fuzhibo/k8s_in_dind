# !/bin/sh
set -eu
# 这里要做一些初始化的等待，比如等待一些特定的文件存在后，再进行提动
while [ ! -d /var/lib/kubelet ] || [ ! -e /var/lib/kubelet/config.yaml ]; do
    echo "Waiting for kubernetes config files..."
    sleep 3
done
# 根据不同的版本选择不同的启动命令
# 由于 kubelet 启动可能会超时失败，所以这里加一个循环
for i in $(seq 10)
do
    if [ $KUBEADM_K8S_VERSION = '1.12.0' ]
    then
        /usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf --config=/var/lib/kubelet/config.yaml --runtime-cgroups=/k8s/system.slice --pod-infra-container-image registry.aliyuncs.com/google_containers/pause:3.1
    else
        /usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf --config=/var/lib/kubelet/config.yaml --runtime-cgroups=/k8s/system.slice
    fi
    sleep 3
done
