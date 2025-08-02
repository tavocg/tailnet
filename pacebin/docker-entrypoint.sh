#!/bin/sh
set -e

SECRET="${PB_SECRET:-$(head -c 32 /dev/urandom | sha256sum | cut -d' ' -f1)}"

exec pacebin -d /pacebin-data -p 8081 -s "$SECRET" -k
