#!/bin/sh -x
set -eu

CONTAINER_LOG_LEVEL="info"

# no arguments passed
# or first arg is `-f` or `--some-option`
if [ "$#" -eq 0 ] || [ "${1#-}" != "$1" ]; then
    # set "containerdSocket" to the default
    containerdConfig='/etc/containerd/config.toml'
    set -- containerd --config $containerdConfig --log-level $CONTAINER_LOG_LEVEL
fi

exec "$@"
