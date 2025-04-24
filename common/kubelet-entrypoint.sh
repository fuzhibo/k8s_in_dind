# !/bin/sh
set -eu
# 这里要做一些初始化的等待，比如等待一些特定的文件存在后，再进行提动
while [ ! -d /var/lib/kubelet ] || [ ! -e /var/lib/kubelet/config.yaml ]; do
    echo "Waiting for kubernetes config files..."
    sleep 3
done
/usr/bin/kubelet --bootstrap-kubeconfig=/etc/kubernetes/bootstrap-kubelet.conf --kubeconfig=/etc/kubernetes/kubelet.conf --config=/var/lib/kubelet/config.yaml --runtime-cgroups=/k8s/system.slice
