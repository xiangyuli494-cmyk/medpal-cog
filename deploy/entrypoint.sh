#!/bin/sh
# 启动流程：首次建库 → 灌样本资产 → 起 MCP 服务
# 设计原则：宁可在启动时就崩，也不要静默降级成一个「端口通但资产为空」的假健康容器。
#
# 入库只做一次：容器重启不许抹掉运行期上传的资产（评审 P1 的根因就是每次启动都重灌）。
#   MEDPAL_INGEST=auto（默认） 仅首次建库那一轮灌样本
#   MEDPAL_INGEST=rebuild      显式重建：覆盖台账，需要在已有库上重灌时手动指定
#   MEDPAL_INGEST=0|skip       完全不灌（自带卷的只读部署）
set -e

DB="${MEDPAL_DB:-/app/mcp-server/data/medpal.db}"
cd /app

FIRST_INIT=0
if [ ! -f "$DB" ]; then
  echo "[entrypoint] 种子库不存在，首次建库：$DB"
  python mcp-server/seed.py --reset
  FIRST_INIT=1
fi

MODE="${MEDPAL_INGEST:-auto}"
case "$MODE" in
  1|always|rebuild)
    echo "[entrypoint] MEDPAL_INGEST=$MODE：重灌 data/samples（会覆盖已有台账）"
    python tools/ingest_all.py || {
      echo "[entrypoint] ingest_all 失败：资产卡没进库，拒绝以「空台账」状态起服务" >&2
      exit 1
    }
    ;;
  auto)
    if [ "$FIRST_INIT" = "1" ]; then
      echo "[entrypoint] 首次建库，灌入 data/samples（70 份样本里 3 份解析不出，实得 70 张卡）"
      python tools/ingest_all.py || {
        echo "[entrypoint] ingest_all 失败：资产卡没进库，拒绝以「空台账」状态起服务" >&2
        exit 1
      }
    else
      echo "[entrypoint] 已有库（$DB），跳过入库以保留运行期上传的资产；要重灌请设 MEDPAL_INGEST=rebuild"
    fi
    ;;
  0|skip|false)
    echo "[entrypoint] MEDPAL_INGEST=$MODE，跳过入库"
    ;;
  *)
    echo "[entrypoint] 不认识的 MEDPAL_INGEST=$MODE（可选 auto / rebuild / skip）" >&2
    exit 1
    ;;
esac

# 兜底：不管走哪条路，起服务前台账不能是 0 行——否则 health() 说资产 0，评委一问就是空库。
ASSETS=$(python -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('select count(*) from asset').fetchone()[0])" "$DB")
if [ "$ASSETS" -le 0 ]; then
  echo "[entrypoint] 台账 0 行（$DB），拒绝启动：空台账不算部署成功" >&2
  exit 1
fi

echo "[entrypoint] 台账 $ASSETS 行 | transport=${MCP_TRANSPORT:-stdio} host=${MCP_HOST:-0.0.0.0} port=${MCP_PORT:-8090} db=$DB"
exec python mcp-server/server.py
