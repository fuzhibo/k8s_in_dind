#!/bin/sh
set -eu

# crictl 安装脚本
# 注意: crictl 版本需要与 K8s 版本和 containerd 版本兼容
# - containerd v1.4.x (Docker 20.10.x) 使用 CRI v1alpha2，需要 crictl v1.23.x
# - containerd v1.6+ (Docker 23.0.x) 使用 CRI v1，可以使用 crictl v1.26+

# 版本由环境变量或预下载的文件决定
: ${VERSION:=v1.23.0}

# 查找预下载的 crictl tar 文件
CRICTL_TAR=""
for tar_file in /tmp/crictl-*.tar.gz /build/crictl-*.tar.gz ./*.tar.gz; do
    if [ -f "$tar_file" ] && echo "$tar_file" | grep -q "crictl-.*-linux-amd64.tar.gz"; then
        CRICTL_TAR="$tar_file"
        echo "INFO: Found pre-downloaded crictl tar: $CRICTL_TAR"
        break
    fi
done

if [ -n "$CRICTL_TAR" ] && [ -f "$CRICTL_TAR" ]; then
    # 使用预下载的文件
    echo "INFO: Installing crictl from pre-downloaded file: $CRICTL_TAR"

    # 验证文件是否有效
    if ! tar -tzf "$CRICTL_TAR" >/dev/null 2>&1; then
        echo "ERROR: Pre-downloaded crictl tar file is corrupted"
        exit 1
    fi

    # 解压并安装
    echo "Extracting and installing crictl..."
    tar -zxvf "$CRICTL_TAR" -C /tmp/
    mv /tmp/crictl /usr/local/bin/

    # 清理 tar 文件
    rm -f "$CRICTL_TAR"

    echo "INFO: crictl installation completed successfully from pre-downloaded file"
else
    # 如果没有预下载的文件，则从网络下载
    echo "WARN: No pre-downloaded crictl tar found, downloading from network..."
    echo "INFO: Downloading crictl-$VERSION-linux-amd64.tar.gz..."

    MAX_RETRIES=5
    RETRY_COUNT=0
    DOWNLOAD_SUCCESS=false

    while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "Attempt $RETRY_COUNT of $MAX_RETRIES..."

        # 使用 --http1.1 避免 HTTP/2 连接问题，添加重试和超时
        if curl --http1.1 -L --connect-timeout 30 --max-time 300 --retry 3 --retry-delay 5 \
            -o /tmp/crictl-$VERSION-linux-amd64.tar.gz \
            https://github.com/kubernetes-sigs/cri-tools/releases/download/$VERSION/crictl-$VERSION-linux-amd64.tar.gz; then
            # 验证文件是否有效
            if [ -f "/tmp/crictl-$VERSION-linux-amd64.tar.gz" ] && tar -tzf /tmp/crictl-$VERSION-linux-amd64.tar.gz >/dev/null 2>&1; then
                DOWNLOAD_SUCCESS=true
                echo "Download successful!"
                break
            fi
        fi

        echo "Download failed or corrupted, retrying..."
        rm -f /tmp/crictl-$VERSION-linux-amd64.tar.gz
        sleep 5
    done

    if [ "$DOWNLOAD_SUCCESS" = "false" ]; then
        echo "Error: Failed to download crictl after $MAX_RETRIES attempts"
        exit 1
    fi

    # 解压并移动文件
    echo "Extracting and installing crictl..."
    tar -zxvf /tmp/crictl-$VERSION-linux-amd64.tar.gz -C /tmp/
    mv /tmp/crictl /usr/local/bin/
    rm -f /tmp/crictl-$VERSION-linux-amd64.tar.gz

    echo "INFO: crictl installation completed successfully from network download"
fi

# 验证安装
if ! command -v crictl >/dev/null 2>&1; then
    echo "ERROR: crictl not found in /usr/local/bin"
    exit 1
fi

echo "INFO: crictl version: $(crictl --version)"
