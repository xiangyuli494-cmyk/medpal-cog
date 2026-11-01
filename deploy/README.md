# 部署：把 MCP Server 送到 Nexent 手里

本目录只解决一件事：让 Nexent 里的主智能体**看见**这 10 个工具。三条路按顺序试，第一条通了就别折腾后面的。

## 路 1 远程 MCP 链接（首选，不需要 Docker）

宿主机直接跑：

```bash
export PYTHONIOENCODING=utf-8
export NO_PROXY=127.0.0.1,localhost
export MCP_TRANSPORT=streamable-http
python mcp-server/server.py
```

Nexent 在 Docker 里时，填 `http://host.docker.internal:8090/mcp`；Nexent 也在宿主机时填 `http://127.0.0.1:8090/mcp`。

Linux 宿主机没有 `host.docker.internal`，给 Nexent 容器加：

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

验收：`curl -s -X POST http://127.0.0.1:8090/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'` 能看到 `serverInfo.name = medpal-cog`。

## 路 2 API 转 MCP

把 `mcp-server/server.py` 里 10 个工具的入参/出参抄成 OpenAPI 3.x，在 Nexent 里用「API 接入 → 转 MCP」。适合路 1 被网络策略挡住时兜底；代价是要人工维护两份签名，**只在没路走时用**。

## 路 3 容器化同网（长期跑）

```bash
docker compose -f deploy/docker-compose.yml up --build -d
docker compose -f deploy/docker-compose.yml ps      # 等 healthy
curl -s http://127.0.0.1:8090/mcp -o /dev/null -w "%{http_code}\n"
```

容器内已经设好 `MCP_TRANSPORT=streamable-http`、`MCP_PORT=8090`、`MEDPAL_DB=/app/mcp-server/data/medpal.db`；首次启动自动 `seed.py --reset` 建库，之后靠 `medpal-data` 卷持久化。

要挂进 Nexent 的网络：

```bash
docker network ls | grep -i nexent
docker network connect <nexent网络名> medpal-mcp
```

然后在 Nexent 里填 `http://medpal-mcp:8090/mcp`。

## 常见故障

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 宿主机 `curl` 通，Nexent 连不上 | 容器内 `127.0.0.1` 指自己 | 改 `host.docker.internal` 或走同网 |
| `502 Bad Gateway` / `ConnectError` | 系统代理拦回环 | 设 `NO_PROXY=127.0.0.1,localhost` |
| 工具列表为空 | 连到了 `/sse` 或根路径 | 路径必须是 `/mcp`（`streamable_http_path="/mcp"`） |
| 工具调用报缺表 | 卷里没库 | `docker compose exec medpal-mcp python mcp-server/seed.py --reset` |
| 中文全乱码 | 容器没设编码 | 镜像已设 `PYTHONIOENCODING=utf-8`，别覆盖 |
