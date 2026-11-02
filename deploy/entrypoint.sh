#!/bin/sh
# 首次启动建种子库；之后每次只做健康检查后拉起服务
set -e

DB="${MEDPAL_DB:-/app/mcp-server/data/medpal.db}"

if [ ! -f "$DB" ]; then
  echo "[entrypoint] 种子库不存在，先建库：$DB"
  python mcp-server/seed.py --reset
fi

echo "[entrypoint] transport=${MCP_TRANSPORT:-stdio} port=${MCP_PORT:-8090} db=$DB"
exec python mcp-server/server.py
