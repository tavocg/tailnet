#!/bin/sh
set -e

SECRET="${PB_SECRET:-$(head -c 32 /dev/urandom | sha256sum | cut -d' ' -f1)}"

exec clink -d /clink-data -p 8081 -s "$SECRET" -k
