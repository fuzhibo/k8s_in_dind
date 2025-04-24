# k8s_in_dind

Kubernetes in `docker in docker`. Maybe useful for test(not for production!).

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
# create a master
docker run --privileged -d --name test-master -it -e CONTAINERD_INDIVIDUALLY_START="true" -e KUBEADM_INIT_WORKFLOW="enable" -v /lib/modules:/lib/modules ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:23.0.5-1.31.7

# we can get kubeadm join information from the master container logs output,
# then we can use it to create a node, also the master container ip
docker run --privileged -d --name test-node -it -e CONTAINERD_INDIVIDUALLY_START="true" -e KUBEADM_JOIN_WORKFLOW="enable" -e ADVERTISE_ADDRESS="<master ip address>" -e API_SERVER_ENDPOINT="<master ip address>:<master port>" -e CA_CERT_HASHES="<kubeadm join ca cert has>" -v /lib/modules:/lib/modules ccr.ccs.tencentyun.com/fuzhibo/k8s-in-dind:23.0.5-1.31.7
```
