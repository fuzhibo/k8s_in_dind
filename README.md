# k8s_in_dind

Kubernetes in `docker in docker`. Maybe useful for test (not for production!).

## Environment

```bash
# make sure you have configured /etc/sysctl.conf
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
net.ipv4.ip_forward = 1
```

## How to build a image

```bash
# make sure you have kubeadm kubectl and kubelet binaries, you can compile them by yourself.
# please refer to https://github.com/kubernetes/kubernetes/blob/master/docs/devel/building.md to get more information.
# make sure this project and kubernetes source project in the same directory, then we can use build.sh
# the following environment variables can be set to customize the image
export DOCKER_REGISTRY="ccr.ccs.tencentyun.com/fuzhibo"
export DOCKER_VERSION="23.0.5"
export K8S_VERSION="1.31.7"
bash -x ./common/build.sh
```

## How to use

```bash
##### Create cluster 1.31.7 (with cgroup v2)
# create a master
docker run --privileged -d --name test-master -it -e CONTAINERD_INDIVIDUALLY_START="true" -e KUBEADM_INIT_WORKFLOW="enable" -e KUBEADM_K8S_VERSION="v1.31.7" -v /lib/modules:/lib/modules ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:23.0.5-1.31.7

# we can get kubeadm join information from the master container logs output,
# then we can use it to create a node, also the master container ip
docker run --privileged -d --name test-node -it -e CONTAINERD_INDIVIDUALLY_START="true" -e KUBEADM_JOIN_WORKFLOW="enable" -e ADVERTISE_ADDRESS="<master ip address>" -e API_SERVER_ENDPOINT="<master ip address>:<master port>" -e CA_CERT_HASHES="<kubeadm join ca cert hash>" -v /lib/modules:/lib/modules ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:23.0.5-1.31.7

#### Create cluster 1.16.15 (with cgroup v1)
# create a master
docker run --privileged -d --name test-master -e KUBEADM_K8S_VERSION="v1.16.15" -e KUBEADM_INIT_WORKFLOW="enable" -e CNI_VERSION="calico_v3.14" -v $PWD/storage_docker:/var/lib/docker -v /lib/modules:/lib/modules ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:18.09.0-v1.16.15

# create a node
docker run --privileged -d --name test-node -it -e KUBEADM_JOIN_WORKFLOW="enable" -e KUBEADM_K8S_VERSION="v1.16.15" -e ADVERTISE_ADDRESS="<master ip address>" -e API_SERVER_ENDPOINT="<master ip address>:<master port>" -e BOOTSTRAP_TOKEN="<bootstrap token>" -e CA_CERT_HASHES="<kubeadm join ca cert hash>" -v $PWD/storage_docker_node:/var/lib/docker -v /lib/modules:/lib/modules ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:18.09.0-v1.16.15

#### Create cluster 1.12.0 (with cgroup v1)
# create a master
docker run --privileged -d --name test-master -e KUBEADM_K8S_VERSION="v1.12.0" -e KUBEADM_INIT_WORKFLOW="enable" -v $PWD/storage_docker:/var/lib/docker -v /lib/modules:/lib/modules ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:18.09.0-1.12.0

# create a node
docker run --privileged -d --name test-node -it -e KUBEADM_JOIN_WORKFLOW="enable" -e KUBEADM_K8S_VERSION="v1.12.0" -e ADVERTISE_ADDRESS="<master ip address>" -e API_SERVER_ENDPOINT="<master ip address>:<master port>" -e BOOTSTRAP_TOKEN="<bootstrap token>" -e CA_CERT_HASHES="<kubeadm join ca cert hash>" -v $PWD/storage_docker_node:/var/lib/docker -v /lib/modules:/lib/modules ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:18.09.0-1.12.0

# login to master and label node to schedule cni pods
kubectl get node | awk '$1!~/NAME/{print $1}' | xargs -i -t kubectl label node {} kubernetes.io/os=linux


# we can run k8s_in_dind in kata-containers
```

## The difference between kind and k8s_in_dind

1. kind need cgroup namespace support in kernel, but k8s_in_dind does not.  
2. kind create kubernetes cluster on containerd only, but k8s_in_dind create kubernetes cluster on docker and containerd.  
