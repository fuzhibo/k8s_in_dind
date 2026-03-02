#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import sys
import logging
import json
import re
import tomli
import tomli_w
import yaml

logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)

# 修改相关组件的配置信息
CONTAINERD_CONFIG_FILE = "/etc/containerd/config.toml"
CONTAINERD_SOCKET = "unix:///run/containerd/containerd.sock"
DOCKER_SOCKET = "unix:///var/run/dockershim.sock"

pause_image = "registry.aliyuncs.com/google_containers/pause:3.9"


def get_k8s_version_info():
    """解析 K8s 版本信息，返回 (major, minor) 元组"""
    k8s_version = os.environ.get("KUBEADM_K8S_VERSION", "v1.31.7")
    match = re.match(r"v?(\d+)\.(\d+)", k8s_version)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 1, 31  # 默认值


def get_cri_type():
    """获取并验证 CRI 类型

    Returns:
        str: "containerd" 或 "docker"

    Raises:
        SystemExit: 当 v1.24+ 尝试使用 docker CRI 时
    """
    cri_type = os.environ.get("CRI_TYPE", "auto").lower()
    major, minor = get_k8s_version_info()
    k8s_version = os.environ.get("KUBEADM_K8S_VERSION", "v1.31.7")

    # v1.24+ 移除了 dockershim
    if major > 1 or (major == 1 and minor >= 24):
        if cri_type == "docker":
            logger.error(
                f"K8s {k8s_version} does not support docker CRI "
                f"(dockershim removed in v1.24). Use CRI_TYPE=containerd instead."
            )
            sys.exit(1)

    # auto 模式自动选择
    if cri_type == "auto":
        if major > 1 or (major == 1 and minor >= 24):
            selected = "containerd"
        else:
            selected = "docker"
        logger.info(f"CRI_TYPE=auto, selected {selected} for K8s {k8s_version}")
        return selected

    return cri_type


def get_cri_socket(cri_type):
    """获取 CRI socket 路径

    Args:
        cri_type: "containerd" 或 "docker"

    Returns:
        str: CRI socket 路径
    """
    if cri_type == "docker":
        return DOCKER_SOCKET
    return CONTAINERD_SOCKET


def modify_contaienrd_config_version2(config):
    # 修改 pause 仓库的地址
    # plugins.'plugins."io.containerd.grpc.v1.cri"'.sandbox_image 指定合理的 pause 镜像
    config["plugins"]['io.containerd.grpc.v1.cri']["sandbox_image"] = pause_image
    # 打开 SystemdCgroup 的配置
    # config["plugins"]['io.containerd.grpc.v1.cri']["containerd"]["runtimes"]["runc"]["options"]["SystemdCgroup"] = True


# 获取 CRI 类型（在 containerd 配置之前，用于决定是否配置 containerd）
_cri_type = get_cri_type()
_cri_socket = get_cri_socket(_cri_type)
logger.info(f"CRI_TYPE={_cri_type}, CRI socket={_cri_socket}")

# 仅在使用 containerd 时配置 containerd
if _cri_type == "containerd":
    if not os.path.exists(CONTAINERD_CONFIG_FILE):
        logger.error(f"containerd config file {CONTAINERD_CONFIG_FILE} not found")
        sys.exit(1)

    logger.info(f"Begin to config containerd config file {CONTAINERD_CONFIG_FILE}")
    containerd_config = None
    # 开始进行配置
    with open(CONTAINERD_CONFIG_FILE, "rb") as fp:
        containerd_config = tomli.load(fp)
        logger.debug(json.dumps(containerd_config, indent=4))
        # 根据版本进行修改
        if containerd_config["version"] == 2:
            modify_contaienrd_config_version2(containerd_config)
        else:
            logger.error(
                f"containerd config file {CONTAINERD_CONFIG_FILE} version {containerd_config['version']} not supported")
            sys.exit(1)

    if containerd_config is not None:
        with open(CONTAINERD_CONFIG_FILE, "wb") as fp:
            tomli_w.dump(containerd_config, fp)
            fp.flush()
            # 强制同步数据到磁盘
            os.fsync(fp.fileno())

# 修改 kubeadmin init 或者 join 的配置文件
KUBEADM_INIT_CONFIG_FILE = "/kubeadm_install/kubeadm_init.yaml"
KUBEADM_JOIN_CONFIG_FILE = "/kubeadm_install/kubeadm_join.yaml"


def modify_kubeadm_init_config_InitConfiguration(kubeadm_init_config):
    kubeadm_init_config["localAPIEndpoint"]["advertiseAddress"] = "0.0.0.0"
    # 根据 CRI 类型配置 criSocket
    kubeadm_init_config["nodeRegistration"]["criSocket"] = _cri_socket
    # 这里我们直接用 hostname 作为 node name
    hostname = os.environ.get("HOSTNAME", "k8s-master")
    if hostname == "k8s-master":
        logger.warning(
            f"Will use default node name {hostname} as this node name.")
    kubeadm_init_config["nodeRegistration"]["name"] = hostname
    # provider-id 字段在 K8s v1.31 中已不支持，移除
    # k8sver = os.environ.get("KUBEADM_K8S_VERSION", "v1.31.7")
    # kubeadm_init_config["provider-id"] = f"k8s-in-dind://{_cri_type}/k8s-{k8sver}-cluster/k8s-{k8sver}-cluster-control-plane"
    kubeadm_init_config["skipPhases"] = ["preflight"]


def modify_kubeadm_init_config_ClusterConfiguration(kubeadm_init_config):
    certSANs = os.environ.get(
        "KUBEADM_CERT_SANS", "k8stest.dev.safedog.site")
    if ',' in certSANs:
        certSANs = certSANs.split(",")
    else:
        certSANs = [certSANs]
    hostname = os.environ.get("HOSTNAME", "k8s-master")
    certSANs.append(hostname)
    kubeadm_init_config["apiServer"]["certSANs"] = certSANs
    if "extraArgs" not in kubeadm_init_config["apiServer"]:
        kubeadm_init_config["apiServer"]["extraArgs"] = {}
    kubeadm_init_config["apiServer"]["extraArgs"]["authorization-mode"] = "Node,RBAC"
    kubeadm_init_config["apiServer"]["extraArgs"]["enable-aggregator-routing"] = "true"
    # enable-hostpath-provisioner 字段在 K8s v1.31 中已不支持，移除
    # kubeadm_init_config["controllerManager"]["enable-hostpath-provisioner"] = "true"
    k8sver = os.environ.get("KUBEADM_K8S_VERSION", "v1.31.7")
    imgregistry = os.environ.get(
        "KUBEADM_IMG_REGISTRY", "registry.aliyuncs.com/google_containers")
    svcsubnet = os.environ.get(
        "KUBEADM_SVC_SUBNET", "10.97.0.0/16")
    podsubnet = os.environ.get(
        "KUBEADM_POD_SUBNET", "10.245.0.0/16")
    kubeadm_init_config["imageRepository"] = imgregistry
    kubeadm_init_config["kubernetesVersion"] = k8sver
    kubeadm_init_config["networking"]["serviceSubnet"] = svcsubnet
    kubeadm_init_config["networking"]["podSubnet"] = podsubnet


def modify_kubeadm_init_config_KubeletConfiguration(kubeadm_init_config):
    kubeadm_init_config["address"] = "0.0.0.0"
    kubeadm_init_config["apiVersion"] = "kubelet.config.k8s.io/v1beta1"
    kubeadm_init_config["failSwapOn"] = False
    kubeadm_init_config["cgroupDriver"] = "cgroupfs"
    kubeadm_init_config["imageGCHighThresholdPercent"] = 95
    kubeadm_init_config["imageGCLowThresholdPercent"] = 60
    kubeadm_init_config["evictionHard"] = {
        "imagefs.available": "10%",
        "memory.available": "200Mi",
        "nodefs.available": "10%",
        "nodefs.inodesFree": "5%",
    }
    kubeadm_init_config["evictionPressureTransitionPeriod"] = "5m0s"
    kubeadm_init_config["maxPods"] = int(
        os.environ.get("KUBELET_MAXPODS", "110"))


def modify_kubeadm_init_config_KubeProxyConfiguration(kubeadm_init_config):
    kubeadm_init_config["apiVersion"] = "kubeproxy.config.k8s.io/v1alpha1"
    kubeadm_init_config["conntrack"] = {
        "maxPerCore": 0,
    }
    kubeadm_init_config["iptables"] = {
        "minSyncPeriod": "1s"
    }
    kubeadm_init_config["mode"] = "iptables"


def modify_kubeadm_join_config_JoinConfiguration(kubeadm_join_config):
    kubeadm_join_config["discovery"]["bootstrapToken"]["apiServerEndpoint"] = os.environ.get(
        "API_SERVER_ENDPOINT", "127.0.0.1:6443")
    bootstrap_token = os.environ.get("BOOTSTRAP_TOKEN", "")
    if bootstrap_token:
        kubeadm_join_config["discovery"]["bootstrapToken"]["token"] = bootstrap_token
    kubeadm_join_config["discovery"]["bootstrapToken"]["unsafeSkipCAVerification"] = True
    kubeadm_join_config["discovery"]["bootstrapToken"]["caCertHashes"] = []
    caCertHashes = os.environ.get("CA_CERT_HASHES", "")
    if caCertHashes:
        if "," in caCertHashes:
            for caCertHash in caCertHashes.split(","):
                kubeadm_join_config["discovery"]["bootstrapToken"]["caCertHashes"].append(
                    caCertHash)
        else:
            kubeadm_join_config["discovery"]["bootstrapToken"]["caCertHashes"].append(
                caCertHashes)
    # 根据 CRI 类型配置 criSocket
    kubeadm_join_config["nodeRegistration"] = {
        "criSocket": _cri_socket
    }
    kubeadm_join_config["skipPhases"] = ["preflight"]
    # 设置 tlsBootstrapToken，使用与 discovery token 相同的值
    if bootstrap_token:
        kubeadm_join_config["tlsBootstrapToken"] = bootstrap_token


# 获取环境变量
if os.environ.get("KUBEADM_INIT_WORKFLOW", "disable").lower() == "enable":
    logger.info(
        f"Begin to config kubeadm init config file {KUBEADM_INIT_CONFIG_FILE}")
    kubeadm_init_configs = None
    with open(KUBEADM_INIT_CONFIG_FILE, "r") as fp:
        # 这里需要给一个默认需要配置的列表
        init_needed_configs = ["InitConfiguration", "ClusterConfiguration",
                               "KubeletConfiguration", "KubeProxyConfiguration"]
        # 考虑到有分段，这里使用 safe_load_all 的方法
        kubeadm_init_configs = list(yaml.safe_load_all(fp))
        # 对缺失的配置进行补全
        for kubeadm_init_config in kubeadm_init_configs:
            if kubeadm_init_config.get("kind") in init_needed_configs:
                init_needed_configs.remove(kubeadm_init_config.get("kind"))
        for init_needed_config in init_needed_configs:
            kubeadm_init_configs.append({"kind": init_needed_config})
        for kubeadm_init_config in kubeadm_init_configs:
            logger.debug(
                f"Will modify kubeadm init config {kubeadm_init_config}")
            if kubeadm_init_config.get("kind") == "InitConfiguration":
                modify_kubeadm_init_config_InitConfiguration(
                    kubeadm_init_config)
            elif kubeadm_init_config.get("kind") == "ClusterConfiguration":
                modify_kubeadm_init_config_ClusterConfiguration(
                    kubeadm_init_config)
            elif kubeadm_init_config.get("kind") == "KubeletConfiguration":
                modify_kubeadm_init_config_KubeletConfiguration(
                    kubeadm_init_config)
            elif kubeadm_init_config.get("kind") == "KubeProxyConfiguration":
                modify_kubeadm_init_config_KubeProxyConfiguration(
                    kubeadm_init_config)
            else:
                logger.warning(
                    f"Unsupported kubeadm init config kind {kubeadm_init_config.get('kind')}")
    if kubeadm_init_configs is not None:
        logger.debug(
            f"Will dump {kubeadm_init_configs} to {KUBEADM_INIT_CONFIG_FILE}")
        with open(KUBEADM_INIT_CONFIG_FILE, "w") as fp:
            yaml.dump_all(kubeadm_init_configs, fp)
            fp.flush()
            # 强制同步数据到磁盘
            os.fsync(fp.fileno())
elif os.environ.get("KUBEADM_JOIN_WORKFLOW", "disable").lower() == "enable":
    logger.info(
        f"Begin to config kubeadm join config file {KUBEADM_JOIN_CONFIG_FILE}")
    kubeadm_join_configs = None
    with open(KUBEADM_JOIN_CONFIG_FILE, "r") as fp:
        kubeadm_join_configs = list(yaml.safe_load_all(fp))
        for kubeadm_join_config in kubeadm_join_configs:
            logger.debug(
                f"Will modify kubeadm join config {kubeadm_join_config}")
            if kubeadm_join_config.get("kind") == "JoinConfiguration":
                modify_kubeadm_join_config_JoinConfiguration(
                    kubeadm_join_config)
            else:
                logger.warning(
                    f"Unsupported kubeadm join config kind {kubeadm_join_config.get('kind')}")

    if kubeadm_join_configs is not None:
        logger.debug(
            f"Will dump {kubeadm_join_configs} to {KUBEADM_JOIN_CONFIG_FILE}")
        with open(KUBEADM_JOIN_CONFIG_FILE, "w") as fp:
            yaml.dump_all(kubeadm_join_configs, fp)
            fp.flush()
            # 强制同步数据到磁盘
            os.fsync(fp.fileno())
