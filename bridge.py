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
    python -m xiaozhi_mcp          # 读取 mcp_config.json 启动全部子服务
    或
    python -m xiaozhi_mcp search_mcp.py   # 单服务模式

注意：
    - 同一 MCP_ENDPOINT（同一智能体）只应保留一个 bridge 进程。
    - 新增/删除服务只改 mcp_config.json，不必重启整条链路。
"""

import os
import sys
import json
import asyncio
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "mcp_config.json")


def load_config():
    if not os.path.exists(CONFIG):
        print(f"[bridge] 未找到 {CONFIG}", file=sys.stderr)
        return None
    with open(CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    endpoint = os.environ.get("MCP_ENDPOINT", "").strip()
    if not endpoint:
        print("[bridge] 错误：未设置 MCP_ENDPOINT 环境变量", file=sys.stderr)
        print("[bridge] 示例：export MCP_ENDPOINT='wss://api.xiaozhi.me/mcp/?token=xxx'",
              file=sys.stderr)
        sys.exit(1)

    cfg = load_config()
    print("=" * 60)
    print("xiaozhi MCP 桥接已启动")
    print(f"接入点  : {endpoint[:48]}...{endpoint[-8:]}")
    if cfg:
        servers = cfg.get("mcpServers", {})
        print(f"子服务  : {', '.join(servers.keys()) or '（无）'}")
    print("=" * 60)
    sys.stdout.flush()

    # 交给官方 SDK 处理实际协议；不同版本入口略有差异，这里做兼容调用
    try:
        from xiaozhi_mcp import main as xz_main  # type: ignore
    except ImportError:
        print("[bridge] 未安装 xiaozhi_mcp SDK。请先执行：", file=sys.stderr)
        print("         pip install git+https://github.com/dairoot/mcp-calculator",
              file=sys.stderr)
        sys.exit(2)

    # 有 mcp_config.json 且无额外参数 → 多服务模式；否则交给 SDK 自己解析 argv
    if cfg and len(sys.argv) == 1:
        sys.argv = [sys.argv[0]]  # SDK 会读取同目录 mcp_config.json
    asyncio.run(xz_main()) if asyncio.iscoroutinefunction(xz_main) else xz_main()


if __name__ == "__main__":
    main()
