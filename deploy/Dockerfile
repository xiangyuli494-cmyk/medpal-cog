# MedPal-Cog MCP Server —— 供 Nexent 以 streamable-http 远程链接
# 构建上下文必须是仓库根：docker build -f deploy/Dockerfile -t medpal-cog/mcp:0.1.0 .
#
# 为什么是 3.12 而不是 3.13：requirements.txt 里 pymupdf 的条件是
#   pymupdf>=1.24 ; python_version < "3.13"
# 用 3.13 镜像会静默跳过 PDF 解析依赖，PDF 类资产直接降级为「解析失败」。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt

# 运行期真正会用到的三块：服务本体、样本语料、首次建库用的入库脚本
# tools/ 只拷 ingest_all.py：整个 tools/ 会把 gh-protect.sh 这类运维脚本带进产线镜像。
# 实测口径：73 份样本里 pdf_07_encrypted / pdf_08_scan_image_only / pdf_10_blank 解析不出，
# 入库 70 行、导出 70 张卡、活跃三元组 37 条（不是「62 张」——62 是仓库里旧卡的文件数）。
COPY mcp-server ./mcp-server
COPY data ./data
COPY tools/ingest_all.py ./tools/ingest_all.py

COPY deploy/entrypoint.sh /app/entrypoint.sh
COPY deploy/healthcheck.py /app/healthcheck.py
RUN chmod +x /app/entrypoint.sh

# 与 store.py 的默认路径保持一致，卷挂在这里即可持久化。
# MEDPAL_INGEST=auto：只在首次建库那一轮灌样本；容器重启不重灌，
# 否则运行期上传的资产会被 delete from asset 抹掉（评审 #36 的 P1）。
ENV MEDPAL_DB=/app/mcp-server/data/medpal.db \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8090 \
    MEDPAL_INGEST=auto

EXPOSE 8090

# 原版 healthcheck 只测端口（socket.connect_ex）：端口通但 MCP 没挂上也算健康，判不出来。
# 现在两关：initialize 要回 serverInfo.name=medpal-cog（§10.5 M-2 同口径），
# 再调 health 工具要求 assets>0——空台账不许判健康。
# start-period 给 120s：首次启动要建库 + 灌 70 张卡，20s 在慢机器上不够。
HEALTHCHECK --interval=15s --timeout=6s --start-period=120s --retries=5 \
  CMD ["python", "/app/healthcheck.py"]

ENTRYPOINT ["/app/entrypoint.sh"]
