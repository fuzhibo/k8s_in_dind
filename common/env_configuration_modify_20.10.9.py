#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import logging
import yaml

logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)

# 配置文件路径
KUBEADM_INIT_CONFIG_FILE = "/kubeadm_install/kubeadm_init.yaml"
KUBEADM_JOIN_CONFIG_FILE = "/kubeadm_install/kubeadm_join.yaml"


def modify_kubeadm_init_config_InitConfiguration(kubeadm_init_config):
    """修改 InitConfiguration 部分"""
    k8sver = os.environ.get("KUBEADM_K8S_VERSION", "v1.23.17")
    hostname = os.environ.get("HOSTNAME", "k8s-master")

    # 配置 API 地址
    kubeadm_init_config["localAPIEndpoint"]["advertiseAddress"] = "0.0.0.0"

    # 不配置 criSocket，使用默认的 dockershim
    # kubeadm_init_config["nodeRegistration"]["criSocket"] = "/var/run/dockershim.sock"

    # 配置节点名称
    if hostname == "k8s-master":
        logger.warning(f"Will use default node name {hostname} as this node name.")
    kubeadm_init_config["nodeRegistration"]["name"] = hostname

    # 添加 provider-id (v1.23+)
    if "kubeletExtraArgs" not in kubeadm_init_config["nodeRegistration"]:
        kubeadm_init_config["nodeRegistration"]["kubeletExtraArgs"] = {}

    kubeadm_init_config["nodeRegistration"]["kubeletExtraArgs"]["provider-id"] = \
        f"k8s-in-dind://docker/k8s-{k8sver}-cluster/k8s-{k8sver}-cluster-control-plane"


def modify_kubeadm_init_config_ClusterConfiguration(kubeadm_init_config):
    """修改 ClusterConfiguration 部分"""
    certSANs = os.environ.get("KUBEADM_CERT_SANS", "k8stest.dev.safedog.site")
    if ',' in certSANs:
        certSANs = certSANs.split(",")
    else:
        certSANs = [certSANs]

    hostname = os.environ.get("HOSTNAME", "k8s-master")
    certSANs.append(hostname)

    k8sver = os.environ.get("KUBEADM_K8S_VERSION", "v1.23.17")
    imgregistry = os.environ.get("KUBEADM_IMG_REGISTRY", "registry.aliyuncs.com/google_containers")
    svcsubnet = os.environ.get("KUBEADM_SVC_SUBNET", "10.97.0.0/16")
    podsubnet = os.environ.get("KUBEADM_POD_SUBNET", "10.245.0.0/16")

    # API Server 配置
    kubeadm_init_config["apiServer"]["certSANs"] = certSANs
    if "extraArgs" not in kubeadm_init_config["apiServer"]:
        kubeadm_init_config["apiServer"]["extraArgs"] = {}

    kubeadm_init_config["apiServer"]["extraArgs"]["authorization-mode"] = "Node,RBAC"
    kubeadm_init_config["apiServer"]["extraArgs"]["enable-aggregator-routing"] = "true"

    # 集群配置
    kubeadm_init_config["imageRepository"] = imgregistry
    kubeadm_init_config["kubernetesVersion"] = k8sver
    kubeadm_init_config["networking"]["serviceSubnet"] = svcsubnet
    kubeadm_init_config["networking"]["podSubnet"] = podsubnet


def modify_kubeadm_init_config_KubeletConfiguration(kubeadm_init_config):
    """修改 KubeletConfiguration 部分"""
    imgregistry = os.environ.get("KUBEADM_IMG_REGISTRY", "registry.aliyuncs.com/google_containers")

    kubeadm_init_config["address"] = "0.0.0.0"
    kubeadm_init_config["apiVersion"] = "kubelet.config.k8s.io/v1beta1"
    kubeadm_init_config["failSwapOn"] = False
    kubeadm_init_config["cgroupDriver"] = "cgroupfs"  # Docker 使用 cgroupfs
    kubeadm_init_config["imageGCHighThresholdPercent"] = 95
    kubeadm_init_config["imageGCLowThresholdPercent"] = 60
    # 配置 pause 镜像使用阿里云 registry
    kubeadm_init_config["pauseImage"] = f"{imgregistry}/pause:3.6"
    kubeadm_init_config["evictionHard"] = {
        "imagefs.available": "10%",
        "memory.available": "200Mi",
        "nodefs.available": "10%",
        "nodefs.inodesFree": "5%",
    }
    kubeadm_init_config["evictionPressureTransitionPeriod"] = "5m0s"
    kubeadm_init_config["maxPods"] = int(os.environ.get("KUBELET_MAXPODS", "110"))


def modify_kubeadm_init_config_KubeProxyConfiguration(kubeadm_init_config):
    """修改 KubeProxyConfiguration 部分 - 关键：iptables 模式"""
    kubeadm_init_config["apiVersion"] = "kubeproxy.config.k8s.io/v1alpha1"

    # 配置 conntrack
    kubeadm_init_config["conntrack"] = {
        "maxPerCore": 0,
        "min": 0,
        "tcpCloseWaitTimeout": "1h0m0s",
        "tcpEstablishedTimeout": "24h0m0s"
    }

    # 配置 iptables
    kubeadm_init_config["iptables"] = {
        "minSyncPeriod": "1s",
        "syncPeriod": "30s"
    }

    # 关键：设置代理模式为 iptables
    kubeadm_init_config["mode"] = "iptables"

    logger.info("kube-proxy mode set to: iptables")


def modify_kubeadm_join_config_JoinConfiguration(kubeadm_join_config):
    """修改 JoinConfiguration 部分"""
    kubeadm_join_config["discovery"]["bootstrapToken"]["apiServerEndpoint"] = \
        os.environ.get("API_SERVER_ENDPOINT", "127.0.0.1:6443")

    bootstrap_token = os.environ.get("BOOTSTRAP_TOKEN", "")
    if bootstrap_token:
        kubeadm_join_config["discovery"]["bootstrapToken"]["token"] = bootstrap_token

    kubeadm_join_config["discovery"]["bootstrapToken"]["unsafeSkipCAVerification"] = True

    caCertHashes = os.environ.get("CA_CERT_HASHES", "")
    kubeadm_join_config["discovery"]["bootstrapToken"]["caCertHashes"] = []
    if caCertHashes:
        if "," in caCertHashes:
            for hash in caCertHashes.split(","):
                kubeadm_join_config["discovery"]["bootstrapToken"]["caCertHashes"].append(hash)
        else:
            kubeadm_join_config["discovery"]["bootstrapToken"]["caCertHashes"].append(caCertHashes)

    # 不配置 criSocket，使用默认的 dockershim
    # kubeadm_join_config["nodeRegistration"]["criSocket"] = "/var/run/dockershim.sock"

    # 配置节点名称
    hostname = os.environ.get("HOSTNAME", "k8s-node")
    kubeadm_join_config["nodeRegistration"]["name"] = hostname


# 主流程
if os.environ.get("KUBEADM_INIT_WORKFLOW", "disable").lower() == "enable":
    logger.info(f"Begin to config kubeadm init config file {KUBEADM_INIT_CONFIG_FILE}")

    with open(KUBEADM_INIT_CONFIG_FILE, "r") as fp:
        init_needed_configs = [
            "InitConfiguration",
            "ClusterConfiguration",
            "KubeletConfiguration",
            "KubeProxyConfiguration"  # v1.23+ 支持
        ]

        kubeadm_init_configs = list(yaml.safe_load_all(fp))

        # 补全缺失的配置
        for kubeadm_init_config in kubeadm_init_configs:
            if kubeadm_init_config and kubeadm_init_config.get("kind") in init_needed_configs:
                init_needed_configs.remove(kubeadm_init_config.get("kind"))

        for init_needed_config in init_needed_configs:
            kubeadm_init_configs.append({"kind": init_needed_config})

        # 修改配置
        for kubeadm_init_config in kubeadm_init_configs:
            if not kubeadm_init_config:
                continue
            kind = kubeadm_init_config.get("kind")
            logger.debug(f"Will modify kubeadm init config {kind}")

            if kind == "InitConfiguration":
                modify_kubeadm_init_config_InitConfiguration(kubeadm_init_config)
            elif kind == "ClusterConfiguration":
                modify_kubeadm_init_config_ClusterConfiguration(kubeadm_init_config)
            elif kind == "KubeletConfiguration":
                modify_kubeadm_init_config_KubeletConfiguration(kubeadm_init_config)
            elif kind == "KubeProxyConfiguration":
                modify_kubeadm_init_config_KubeProxyConfiguration(kubeadm_init_config)
            else:
                logger.warning(f"Unsupported kubeadm init config kind {kind}")

    # 保存配置
    with open(KUBEADM_INIT_CONFIG_FILE, "w") as fp:
        yaml.dump_all(kubeadm_init_configs, fp)
        fp.flush()
        os.fsync(fp.fileno())

elif os.environ.get("KUBEADM_JOIN_WORKFLOW", "disable").lower() == "enable":
    logger.info(f"Begin to config kubeadm join config file {KUBEADM_JOIN_CONFIG_FILE}")

    with open(KUBEADM_JOIN_CONFIG_FILE, "r") as fp:
        kubeadm_join_configs = list(yaml.safe_load_all(fp))

        for kubeadm_join_config in kubeadm_join_configs:
            if not kubeadm_join_config:
                continue
            kind = kubeadm_join_config.get("kind")
            logger.debug(f"Will modify kubeadm join config {kind}")

            if kind == "JoinConfiguration":
                modify_kubeadm_join_config_JoinConfiguration(kubeadm_join_config)
            else:
                logger.warning(f"Unsupported kubeadm join config kind {kind}")

    with open(KUBEADM_JOIN_CONFIG_FILE, "w") as fp:
        yaml.dump_all(kubeadm_join_configs, fp)
        fp.flush()
        os.fsync(fp.fileno())
