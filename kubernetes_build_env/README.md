### How to use

```bash
# daily use (manual compilation),need to run git config --global --add safe.directory /root/workplace
docker run --name=k8s-build -it -v <kubernetes source path>:/root/workplace -v <gopath>:/go ccr.ccs.tencentyun.com/cyberbrain/k8s-build-env:1.24 bash
```
