ARG DOCKER_REGISTRY=ccr.ccs.tencentyun.com/fuzhibo
ARG DOCKER_VERSION=23.0.5
FROM ${DOCKER_REGISTRY}/k8s-in-dind:base-${DOCKER_VERSION}

COPY docker-entrypoint.sh /usr/local/bin
COPY containerd-entrypoint.sh /usr/local/bin
COPY dockerd-entrypoint.sh /usr/local/bin
COPY k8s-cluster-check.sh /usr/local/bin
COPY k8s-cluster-create.sh /usr/local/bin
COPY kubelet-entrypoint.sh /usr/local/bin
COPY env_configuration_modify.py /usr/local/bin
COPY preconfig.sh /usr/local/bin
COPY start.sh /usr/local/bin
ADD cni_repo /cni_repo
COPY crictl.yaml /etc/crictl.yaml
COPY crictl-install.sh /usr/local/bin
COPY kubelet /usr/bin
COPY kubeadm /usr/bin
COPY kubectl /usr/bin
# integrate crictl to system
RUN chmod +x /usr/local/bin/crictl-install.sh && \
    /usr/local/bin/crictl-install.sh

VOLUME [ "/var/lib/containerd" ]
ENTRYPOINT []
CMD ["start.sh"]
