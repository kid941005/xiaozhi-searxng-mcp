# ============================================================
# xiaozhi-searxng-mcp —— 多阶段构建
# ============================================================
# 构建：
#   docker build -t xiaozhi-searxng-mcp .
#
# 运行（stdio 模式，给小智 bridge 用）：
#   docker run --rm -i -e SEARXNG_URL=http://your-searxng:8080 xiaozhi-searxng-mcp
#
# 运行（http 模式，给远程客户端直连）：
#   docker run --rm -p 8765:8765 -e MCP_TRANSPORT=http \
#     -e SEARXNG_URL=http://your-searxng:8080 xiaozhi-searxng-mcp
# ============================================================

# ---------- Stage 1: 构建依赖 ----------
FROM python:3.12-slim AS builder

WORKDIR /build

# 编译期依赖（如某些包需要 C 扩展，装完在最终镜像丢弃）
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 装进独立前缀，便于整目录复制到最终镜像
# 注意：MCP_BRIDGE_SDK=1 时才会安装小智桥接 SDK（体积大、依赖 git）
ARG MCP_BRIDGE_SDK=0
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt \
    && if [ "$MCP_BRIDGE_SDK" = "1" ]; then \
         pip install --no-cache-dir --prefix=/install \
           "git+https://github.com/dairoot/mcp-calculator"; \
       fi


# ---------- Stage 2: 运行镜像 ----------
FROM python:3.12-slim AS runtime

# 元数据（可被 GitHub 构建覆盖）
LABEL org.opencontainers.image.title="xiaozhi-searxng-mcp" \
      org.opencontainers.image.description="把自建 SearXNG 变成小智（xiaozhi-esp32）可调用的联网搜索 MCP 服务" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/kid941005/xiaozhi-searxng-mcp"

# 从构建阶段复制已装好的依赖（含可选的 bridge SDK）
COPY --from=builder /install /usr/local

WORKDIR /app

# 以非 root 运行（安全）
RUN useradd -m -u 10001 mcp

# 只拷源码，避免带入本地 __pycache__ / .venv 等（.dockerignore 亦已排除）
COPY --chown=mcp:mcp search_mcp/search_mcp.py /app/search_mcp/search_mcp.py
COPY --chown=mcp:mcp bridge.py       /app/bridge.py
COPY --chown=mcp:mcp entrypoint.sh   /app/entrypoint.sh
COPY --chown=mcp:mcp mcp_config.json /app/mcp_config.json

RUN chmod +x /app/entrypoint.sh

USER mcp

# 默认：stdio 模式占本容器主进程（MCP 客户端通过 stdin/stdout 通信）
# 若 MCP_TRANSPORT=http / sse，则对外暴露 8765
ENV MCP_TRANSPORT=stdio \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8765 \
    MCP_CONFIG=/app/mcp_config.json \
    PYTHONUNBUFFERED=1

EXPOSE 8765

# 健康检查只在 http/sse 模式下有意义；stdio 模式会直接跳过
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD if [ "$MCP_TRANSPORT" = "stdio" ]; then exit 0; \
        else python -c "import urllib.request,sys; \
        sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+'${MCP_PORT}'+'/mcp',timeout=3) else 1)" \
        || exit 1; fi

ENTRYPOINT ["/app/entrypoint.sh"]
