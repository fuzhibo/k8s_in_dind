### RSYNC Static Build Environment

Build Kubernetes need rsync. However not all golang images have rsync install from their own repositories, so we need a rsync which build with static and integrate it to the images.

### How to use

```bash
#!/bin/bash
# Get rsync related source code
bash -x ./get_rsync_src_code.sh
# Use build env image to build rsync
docker run --name=rsync-build -it -v <rsync source path>:/root/workplace ccr.ccs.tencentyun.com/fuzhibo/rsync-build-env:base bash
```
