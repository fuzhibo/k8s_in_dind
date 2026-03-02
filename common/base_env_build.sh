#!/bin/sh
set -eu

# Initialize USE_TSINGHUA_APK_SRC with a default value to avoid undefined errors.
USE_TSINGHUA_APK_SRC="${USE_TSINGHUA_APK_SRC:-false}"

# Initialize USE_ALIYUN_APK_SRC with a default value.
USE_ALIYUN_APK_SRC="${USE_ALIYUN_APK_SRC:-false}"

# 支持通过 USE_TSINGHUA_SRC 环境变量来控制（兼容 Dockerfile-base）
if [ "${USE_TSINGHUA_SRC:-false}" = "false" ]; then
    USE_TSINGHUA_APK_SRC="false"
fi

# Change APK mirror to Aliyun source if enabled.
if [ "$USE_ALIYUN_APK_SRC" = "true" ]; then
    sed -i 's#https\?://dl-cdn.alpinelinux.org/alpine#https://mirrors.aliyun.com/alpine#g' /etc/apk/repositories
# Change APK mirror to Tsinghua University source if enabled.
elif [ "$USE_TSINGHUA_APK_SRC" = "true" ]; then
    sed -i 's#https\?://dl-cdn.alpinelinux.org/alpine#https://mirrors.tuna.tsinghua.edu.cn/alpine#g' /etc/apk/repositories
fi

# Update APK package list and install required packages.
apk update
apk add --no-cache \
    curl \
    socat \
    conntrack-tools \
    python3 \
    findutils

# Install CNI plugins (required for Kubernetes networking)
CNI_PLUGINS_VERSION="v1.1.1"
CNI_PLUGINS_FILE="cni-plugins-linux-amd64-${CNI_PLUGINS_VERSION}.tgz"
CNI_PLUGINS_GH_PATH="containernetworking/plugins/releases/download/${CNI_PLUGINS_VERSION}/${CNI_PLUGINS_FILE}"

# Try multiple mirrors with timeout for better reliability in China
# List of mirrors to try (ordered by reliability)
CNI_DOWNLOADED=false
for mirror in \
    "https://gh-proxy.com/https://github.com/${CNI_PLUGINS_GH_PATH}" \
    "https://gh.api.99988866.xyz/https://github.com/${CNI_PLUGINS_GH_PATH}" \
    "https://github.moeyy.xyz/https://github.com/${CNI_PLUGINS_GH_PATH}" \
    "https://gh-proxy.net/https://github.com/${CNI_PLUGINS_GH_PATH}" \
    "https://github.com/${CNI_PLUGINS_GH_PATH}"; do
    echo "Trying to download CNI plugins from: ${mirror}"
    if curl -sSL --connect-timeout 30 --max-time 300 -o "${CNI_PLUGINS_FILE}" "${mirror}"; then
        if [ -f "${CNI_PLUGINS_FILE}" ] && [ -s "${CNI_PLUGINS_FILE}" ]; then
            CNI_DOWNLOADED=true
            echo "Successfully downloaded CNI plugins from: ${mirror}"
            break
        fi
    fi
    echo "Failed to download from: ${mirror}"
    rm -f "${CNI_PLUGINS_FILE}"
done

if [ "$CNI_DOWNLOADED" = "false" ]; then
    echo "ERROR: Failed to download CNI plugins from all mirrors"
    exit 1
fi

mkdir -p /opt/cni/bin
tar -xzf "${CNI_PLUGINS_FILE}" -C /opt/cni/bin
rm -f "${CNI_PLUGINS_FILE}"

# Initialize USE_ALIYUN_PIP_SRC with a default value to avoid undefined errors.
USE_ALIYUN_PIP_SRC="${USE_ALIYUN_PIP_SRC:-true}"
USE_TENCENT_PIP_SRC="${USE_TENCENT_PIP_SRC:-false}"

# If USE_TENCENT_PIP_SRC is set to 'true', update the pip source to use Tencent Cloud mirror.
if [ "$USE_TENCENT_PIP_SRC" = "true" ]; then
    mkdir -p ~/.pip
    cat >~/.pip/pip.conf <<EOF
[global]
index-url = https://mirrors.cloud.tencent.com/pypi/simple/
[install]
trusted-host = mirrors.cloud.tencent.com
EOF
# If USE_ALIYUN_PIP_SRC is set to 'true', update the pip source to use Aliyun mirror.
elif [ "$USE_ALIYUN_PIP_SRC" = "true" ]; then
    mkdir -p ~/.pip
    cat >~/.pip/pip.conf <<EOF
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
[install]
trusted-host = mirrors.aliyun.com
EOF
else
    # Use USTC mirror as default
    mkdir -p ~/.pip
    cat >~/.pip/pip.conf <<EOF
[global]
index-url = https://pypi.mirrors.ustc.edu.cn/simple/
[install]
trusted-host = pypi.mirrors.ustc.edu.cn
EOF
fi

# Upgrade pip to the latest version and install required Python packages.
if [ $DOCKER_VERSION != "18.09.0" ]
then
    # 有些版本的 python 并不支持后续添加的一些特性，这里就通过分支来筛选不支持功能的版本
    python3 -m ensurepip --upgrade
fi
python3 -m pip install --upgrade pip
python3 -m pip install pyyaml tomli tomli_w
