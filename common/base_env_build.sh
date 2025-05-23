#!/bin/sh
set -eu

# Initialize USE_TSINGHUA_APK_SRC with a default value to avoid undefined errors.
USE_TSINGHUA_APK_SRC="${USE_TSINGHUA_APK_SRC:-true}"

# Change APK mirror to Tsinghua University source if enabled.
# If USE_TSINGHUA_APK_SRC is set to 'true', update the APK repository to use Tsinghua University mirror.
if [ "$USE_TSINGHUA_APK_SRC" = "true" ]; then
    sed -i 's#https\?://dl-cdn.alpinelinux.org/alpine#https://mirrors.tuna.tsinghua.edu.cn/alpine#g' /etc/apk/repositories
fi

# Update APK package list and install required packages.
apk update
apk add --no-cache \
    curl \
    socat \
    conntrack-tools \
    python3

# Initialize USE_ALIYUN_PIP_SRC with a default value to avoid undefined errors.
USE_ALIYUN_PIP_SRC="${USE_ALIYUN_PIP_SRC:-true}"

# If USE_ALIYUN_PIP_SRC is set to 'true', update the pip source to use Aliyun mirror.
if [ "$USE_ALIYUN_PIP_SRC" = "true" ]; then
    mkdir -p ~/.pip
    cat >~/.pip/pip.conf <<EOF
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
[install]
trusted-host = mirrors.aliyun.com
EOF
fi

# Upgrade pip to the latest version and install required Python packages.
python3 -m ensurepip --upgrade
python3 -m pip install --upgrade pip
python3 -m pip install pyyaml tomli tomli_w
