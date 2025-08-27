#!/bin/bash
self_path=$(cd $(dirname $0);pwd)
[ -e "$self_path/zlib-1.3.1.tar.gz" ] || wget https://www.zlib.net/zlib-1.3.1.tar.gz
[ -e "$self_path/openssl-3.0.15.tar.gz" ] || wget https://www.openssl.org/source/openssl-3.0.15.tar.gz
[ -e "$self_path/lz4-1.10.0.tar.gz" ] || wget https://github.com/lz4/lz4/archive/refs/tags/v1.10.0.tar.gz -O lz4-1.10.0.tar.gz
[ -e "$self_path/zstd-1.5.6.tar.gz" ] || wget https://github.com/facebook/zstd/releases/download/v1.5.6/zstd-1.5.6.tar.gz
[ -e "$self_path/acl-2.3.2.tar.gz" ] || wget https://download.savannah.nongnu.org/releases/acl/acl-2.3.2.tar.gz
[ -e "$self_path/attr-2.5.2.tar.gz" ] || wget https://download.savannah.nongnu.org/releases/attr/attr-2.5.2.tar.gz
[ -e "$self_path/xxhash-0.8.2.tar.gz" ] || wget https://github.com/Cyan4973/xxHash/archive/refs/tags/v0.8.2.tar.gz -O xxhash-0.8.2.tar.gz
