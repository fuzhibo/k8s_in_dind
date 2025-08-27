FROM golang:1.24

ENV GO111MODULE="on"
ENV GOPROXY="https://goproxy.cn,direct"

# kubernetes source path
VOLUME [ "/root/workplace" ]
# GOPATH path
VOLUME [ "/go" ]

# install needed packages
RUN apt-get update && \
    apt-get install -y \
    rsync
