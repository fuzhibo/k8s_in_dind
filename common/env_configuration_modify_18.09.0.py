#!/usr/bin/python3
# -*- coding: utf-8 -*-
import os
import logging
import yaml

logger = logging.getLogger(__name__)
console_handler = logging.StreamHandler()

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.setLevel(logging.DEBUG)

# 修改 kubeadmin init 或者 join 的配置文件
KUBEADM_INIT_CONFIG_FILE = "/kubeadm_install/kubeadm_init.yaml"
KUBEADM_JOIN_CONFIG_FILE = "/kubeadm_install/kubeadm_join.yaml"


def modify_kubeadm_init_config_InitConfiguration(kubeadm_init_config):
    k8sver = os.environ.get("KUBEADM_K8S_VERSION", "v1.12.0")
    hostname = os.environ.get("HOSTNAME", "k8s-master")
    if k8sver == "v1.12.0":
        kubeadm_init_config["apiEndpoint"]["advertiseAddress"] = "0.0.0.0"
        # 这里我们使用默认的 docker 作为底层引擎
        # 这里我们直接用 hostname 作为 node name
        if hostname == "k8s-master":
            logger.warning(
                f"Will use default node name {hostname} as this node name.")
        kubeadm_init_config["nodeRegistration"]["name"] = hostname
    elif k8sver == "v1.16.15":
        kubeadm_init_config["localAPIEndpoint"]["advertiseAddress"] = "0.0.0.0"
        # kubeadm_init_config["nodeRegistration"]["criSocket"] = "/var/run/docker.sock"
        # 这里我们直接用 hostname 作为 node name
        if hostname == "k8s-master":
            logger.warning(
                f"Will use default node name {hostname} as this node name.")
        kubeadm_init_config["nodeRegistration"]["name"] = hostname


def modify_kubeadm_init_config_ClusterConfiguration(kubeadm_init_config):
    certSANs = os.environ.get(
        "KUBEADM_CERT_SANS", "k8stest.dev.safedog.site")
    if ',' in certSANs:
        certSANs = certSANs.split(",")
    else:
        certSANs = [certSANs]
    hostname = os.environ.get("HOSTNAME", "k8s-master")
    certSANs.append(hostname)
    k8sver = os.environ.get("KUBEADM_K8S_VERSION", "v1.12.0")
    imgregistry = os.environ.get(
        "KUBEADM_IMG_REGISTRY", "registry.aliyuncs.com/google_containers")
    svcsubnet = os.environ.get(
        "KUBEADM_SVC_SUBNET", "10.97.0.0/16")
    podsubnet = os.environ.get(
        "KUBEADM_POD_SUBNET", "10.245.0.0/16")
    if k8sver == "v1.12.0":
        # 这个 api server 的 cert sans 在 1.12 版本需要单独填写
        kubeadm_init_config["apiServerCertSANs"] = certSANs
        # 在 1.12 版本下，这个 apiserver 的扩展参数是单独使用 apiServerExtraArgs 来存放
        kubeadm_init_config["apiServerExtraArgs"] = {
            "authorization-mode": "Node,RBAC",
            "enable-aggregator-routing": "true"
        }
        # 这个 enable-hostpath-provisioner 在 1.12 版本中只能通过 controller-manager 启动参数的形式使能
        kubeadm_init_config["imageRepository"] = imgregistry
        kubeadm_init_config["kubernetesVersion"] = k8sver
        kubeadm_init_config["networking"]["serviceSubnet"] = svcsubnet
        kubeadm_init_config["networking"]["podSubnet"] = podsubnet
    elif k8sver == "v1.16.15":
        kubeadm_init_config["apiServer"]["certSANs"] = certSANs
        # 1.16.15 在部分配置还是和最新的有所区别
        if "extraArgs" not in kubeadm_init_config["apiServer"]:
            kubeadm_init_config["apiServer"]["extraArgs"] = {}
            # kubeadm_init_config["apiServer"]["extraArgs"] = []
        # kubeadm_init_config["apiServer"]["extraArgs"].append(
        #     {"name": "authorization-mode", "value": "Node,RBAC"})
        # kubeadm_init_config["apiServer"]["extraArgs"].append(
        #     {"name": "enable-aggregator-routing", "value": "true"})
        kubeadm_init_config["apiServer"]["extraArgs"]["authorization-mode"] = "Node,RBAC"
        kubeadm_init_config["apiServer"]["extraArgs"]["enable-aggregator-routing"] = "true"
        kubeadm_init_config["controllerManager"]["enable-hostpath-provisioner"] = "true"
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
    k8sver = os.environ.get("KUBEADM_K8S_VERSION", "v1.12.0")
    apiserver_endpoint = os.environ.get(
        "API_SERVER_ENDPOINT", "127.0.0.1:6443")
    bootstrap_token = os.environ.get("BOOTSTRAP_TOKEN", "")
    if k8sver == "v1.12.0":
        advertiseAddress = os.environ.get("ADVERTISE_ADDRESS", "127.0.0.1")
        # 1.12 的配置和后期的不一样，所以这里要区分版本
        kubeadm_join_config["apiEndpoint"]["advertiseAddress"] = advertiseAddress
        if bootstrap_token:
            kubeadm_join_config["discoveryToken"] = bootstrap_token
            kubeadm_join_config["discoveryTokenAPIServers"] = [
                apiserver_endpoint]
            # 在 1.12 的 kubeadm join 配置中 discoveryToken、tlsBootstrapToken、token 这三个字段虽然都可以填写 token
            # 但是使用场景会有区别，所以为了避免问题，可以将这三个字段都设置为同一个 token，保证兼容性和自动化脚本的健壮性。
            kubeadm_join_config["tlsBootstrapToken"] = bootstrap_token
            kubeadm_join_config["token"] = bootstrap_token
        hostname = os.environ.get("HOSTNAME", "k8s-node")
        kubeadm_join_config["nodeRegistration"] = {
            "name": hostname,
        }
    elif k8sver == "v1.16.15":
        kubeadm_join_config["discovery"]["bootstrapToken"]["apiServerEndpoint"] = apiserver_endpoint
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
        # kubeadm_join_config["nodeRegistration"] = {
        #     "criSocket": "/var/run/docker.sock"
        # }

    # 获取环境变量
if os.environ.get("KUBEADM_INIT_WORKFLOW", "disable").lower() == "enable":
    logger.info(
        f"Begin to config kubeadm init config file {KUBEADM_INIT_CONFIG_FILE}")
    kubeadm_init_configs = None
    with open(KUBEADM_INIT_CONFIG_FILE, "r") as fp:
        # 这里需要给一个默认需要配置的列表
        init_needed_configs = ["InitConfiguration", "ClusterConfiguration",
                               "KubeletConfiguration", "KubeProxyConfiguration"]
        init_unneeded_configs = ["JoinConfiguration"]
        # 考虑到有分段，这里使用 safe_load_all 的方法
        kubeadm_init_configs = list(yaml.safe_load_all(fp))
        # 对缺失的配置进行补全
        for inx, kubeadm_init_config in enumerate(kubeadm_init_configs):
            if kubeadm_init_config.get("kind") in init_needed_configs:
                init_needed_configs.remove(kubeadm_init_config.get("kind"))
        kubeadm_init_configs = [
            cfg for cfg in kubeadm_init_configs
            if cfg.get("kind") not in init_unneeded_configs
        ]
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
        new_join_configs = []
        for inx, kubeadm_join_config in enumerate(kubeadm_join_configs):
            logger.debug(
                f"Will modify kubeadm join config {kubeadm_join_config}")
            if kubeadm_join_config.get("kind") == "JoinConfiguration":
                modify_kubeadm_join_config_JoinConfiguration(
                    kubeadm_join_config)
                new_join_configs.append(kubeadm_join_config)
            else:
                logger.warning(
                    f"Unsupported kubeadm join config kind {kubeadm_join_config.get('kind')}")
        kubeadm_join_configs = new_join_configs

    if kubeadm_join_configs is not None:
        logger.debug(
            f"Will dump {kubeadm_join_configs} to {KUBEADM_JOIN_CONFIG_FILE}")
        with open(KUBEADM_JOIN_CONFIG_FILE, "w") as fp:
            yaml.dump_all(kubeadm_join_configs, fp)
            fp.flush()
            # 强制同步数据到磁盘
            os.fsync(fp.fileno())
