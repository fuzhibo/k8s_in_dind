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
