#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xiaozhi MCP 桥接进程
============================================================
作用：把本机（或容器内）的 MCP 搜索服务，通过 WebSocket 接到
      小智云端的「MCP 接入点」，让小智的 LLM 能发现并调用搜索工具。

架构：
    search_mcp.py (stdio MCP 服务)
            │  stdio
            ▼
    xiaozhi_mcp (本进程 / 官方 bridge SDK)  ──wss──►  api.xiaozhi.me/mcp/?token=...
            │                                          小智云端 → 设备

用法：
    export MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=你的token"
    python bridge.py               # 读取 mcp_config.json 启动全部子服务
    或
    python bridge.py search_mcp.py # 单服务模式

依赖（MODE=bridge 必需）：
    pip install git+https://github.com/dairoot/mcp-calculator

注意：
    - 同一 MCP_ENDPOINT（同一智能体）只应保留一个 bridge 进程。
    - 新增/删除服务只改 mcp_config.json，不必重启整条链路。
    - 官方 SDK 的配置查找顺序是 $MCP_CONFIG，其次当前工作目录的
      mcp_config.json。因此这里显式设置 MCP_CONFIG，避免受 cwd 影响。
"""

import os
import sys
import json

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "mcp_config.json")
ENV_TEMPLATE = (
    "        SEARXNG_URL         你的 SearXNG 地址\n"
    "        MCP_ENDPOINT        小智 MCP 接入点\n"
)


def load_config():
    if not os.path.exists(CONFIG):
        print(f"[bridge] 未找到 {CONFIG}", file=sys.stderr)
        return None
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[bridge] 解析 {CONFIG} 失败：{e!r}", file=sys.stderr)
        return None


def main():
    endpoint = os.environ.get("MCP_ENDPOINT", "").strip()
    if not endpoint:
        print("[bridge] 错误：未设置 MCP_ENDPOINT 环境变量", file=sys.stderr)
        print("[bridge] 示例：export MCP_ENDPOINT='wss://api.xiaozhi.me/mcp/?token=xxx'",
              file=sys.stderr)
        sys.exit(1)

    # 让 SDK 一定能找到随仓库分发的 mcp_config.json（不依赖 cwd）
    os.environ.setdefault("MCP_CONFIG", CONFIG)

    cfg = load_config()
    print("=" * 60)
    print("xiaozhi MCP 桥接已启动")
    print(f"接入点  : {endpoint[:48]}...{endpoint[-8:]}")
    print(f"配置    : {os.environ.get('MCP_CONFIG')}")
    if cfg:
        servers = cfg.get("mcpServers", {})
        print(f"子服务  : {', '.join(servers.keys()) or '（无）'}")
    print("=" * 60)
    sys.stdout.flush()

    # 官方 SDK：main 位于 xiaozhi_mcp.pipe，而不是包根目录
    #   - `python -m xiaozhi_mcp` 走的是 xiaozhi_mcp/__main__.py → pipe.main()
    #   - 包根 __init__.py 只导出 __version__，所以 `from xiaozhi_mcp import main` 必然失败
    try:
        from xiaozhi_mcp.pipe import main as xz_main  # type: ignore
    except ImportError:
        print("[bridge] 未安装 xiaozhi_mcp SDK。请先执行：", file=sys.stderr)
        print("         pip install git+https://github.com/dairoot/mcp-calculator",
              file=sys.stderr)
        print("         或使用官方镜像：MODE=bridge 时 Dockerfile 需 ARG MCP_BRIDGE_SDK=1",
              file=sys.stderr)
        sys.exit(2)

    # main() 内部已自行调用 asyncio.run()，直接调用即可
    sys.exit(xz_main())


if __name__ == "__main__":
    main()
