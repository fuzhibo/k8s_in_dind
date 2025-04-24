#!/bin/sh
set -eu

# 初始化 VERSION 变量，默认值为 v1.31.0
: ${VERSION:=v1.31.0}

# 下载 crictl 压缩包
echo "Downloading crictl-$VERSION-linux-amd64.tar.gz..."
curl -v -L -o crictl-$VERSION-linux-amd64.tar.gz https://github.com/kubernetes-sigs/cri-tools/releases/download/$VERSION/crictl-$VERSION-linux-amd64.tar.gz

# 检查文件是否下载成功
if [ ! -f "crictl-$VERSION-linux-amd64.tar.gz" ]; then
    echo "Error: Failed to download crictl-$VERSION-linux-amd64.tar.gz"
    exit 1
fi

# 解压并移动文件
echo "Extracting and installing crictl..."
tar -zxvf crictl-$VERSION-linux-amd64.tar.gz
mv crictl /usr/local/bin/
rm -rf crictl-$VERSION-linux-amd64.tar.gz

echo "crictl installation completed successfully."
