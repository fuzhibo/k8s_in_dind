#!/bin/sh
set -eu
# 这里主要就是检测相关的配置是否存在，如果不存在就进行创建
[ ! -e /etc/kubernetes/admin.conf ] && [ ! -d /var/lib/kubelet ] && k8s-cluster-create.sh
