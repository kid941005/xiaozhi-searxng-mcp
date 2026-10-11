#!/bin/sh
# ============================================================
# 容器入口：按 MODE 决定跑「搜索 MCP 服务」还是「小智桥接」
# ============================================================
# MODE=mcp     （默认）只跑 MCP 搜索服务本身
#              - MCP_TRANSPORT=stdio → 占 stdin/stdout
#              - MCP_TRANSPORT=http  → 暴露 8765
# MODE=bridge  跑小智桥接，把子 MCP 服务接到 MCP_ENDPOINT
#              （桥接会自己按 mcp_config.json 拉起 search_mcp.py）
# ============================================================
set -e

MODE="${MODE:-mcp}"

echo "============================================================"
echo "xiaozhi-searxng-mcp"
echo "MODE          : $MODE"
echo "MCP_TRANSPORT : ${MCP_TRANSPORT:-stdio}"
echo "SEARXNG_URL   : ${SEARXNG_URL:-(未设置)}"
if [ "$MODE" = "bridge" ]; then
    # 只打印 token 前 30 字符，避免日志泄露
    echo "MCP_ENDPOINT  : $(echo "$MCP_ENDPOINT" | cut -c1-30)..."
fi
echo "============================================================"

if [ -z "$SEARXNG_URL" ]; then
    echo "[warn] SEARXNG_URL 未设置，搜索调用会失败" >&2
fi

if [ "$MODE" = "bridge" ]; then
    if [ -z "$MCP_ENDPOINT" ]; then
        echo "[error] MODE=bridge 但未设置 MCP_ENDPOINT" >&2
        echo "        从 xiaozhi.me 控制台 → 智能体 → 配置 → 扩展能力 → MCP接入点 获取" >&2
        exit 1
    fi
    exec python -u -m xiaozhi_mcp
else
    exec python -u /app/search_mcp/search_mcp.py \
        --transport "${MCP_TRANSPORT:-stdio}" \
        --host "${MCP_HOST:-0.0.0.0}" \
        --port "${MCP_PORT:-8765}"
fi
