#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
: "${ADMIN_PORT:=8787}"
export ADMIN_PORT
python3 admin_server.py
