# MedPal-Cog MCP Server —— 供 Nexent 以 streamable-http 远程链接
# 构建上下文必须是仓库根：docker build -f deploy/Dockerfile -t medpal-cog/mcp:0.1.0 .
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install -r requirements.txt

COPY mcp-server ./mcp-server
COPY data ./data

COPY deploy/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 与 store.py 的默认路径保持一致，卷挂在这里即可持久化
ENV MEDPAL_DB=/app/mcp-server/data/medpal.db \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8090

EXPOSE 8090

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
  CMD python -c "import socket,sys; s=socket.socket(); s.settimeout(2); sys.exit(0 if s.connect_ex(('127.0.0.1',8090))==0 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
