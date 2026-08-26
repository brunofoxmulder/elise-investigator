#!/usr/bin/with-contenv bashio
set -e
cd /app
exec python3 main_mcp_compat.py
