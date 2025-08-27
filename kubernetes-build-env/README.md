### How to use

```bash
# daily use (manual compilation),need to run git config --global --add safe.directory /root/workplace
# for kubernetes 1.18.x - latest
docker run --name=k8s-build -it -v <kubernetes source path>:/root/workplace -v <gopath>:/go ccr.ccs.tencentyun.com/fuzhibo/k8s-build-env:1.24 bash
# for kubernetes 1.12.x
docker run --name=k8s-build -it -v <kubernetes source path>:/root/workplace -v <gopath>:/go ccr.ccs.tencentyun.com/fuzhibo/k8s-build-env:1.10.4 bash
```
