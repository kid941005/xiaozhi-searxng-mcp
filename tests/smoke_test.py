#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
冒烟测试 —— 不需要真实 SearXNG 即可运行。

覆盖：
  1. 模块可导入、MCP 工具正确注册
  2. 结果格式化：URL 去重、多引擎置信标记、直答提取、引擎健康提示
  3. 错误降级：SearXNG 不可达时返回中文错误串，而非抛异常

用法：python tests/smoke_test.py
"""

import asyncio
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MODULE_PATH = os.path.join(ROOT, "search_mcp", "search_mcp.py")


def load_module():
    """按文件路径加载模块 —— 不依赖 sys.path 与包结构，跨平台稳定。"""
    spec = importlib.util.spec_from_file_location("search_mcp_service", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    assert os.path.exists(MODULE_PATH), f"找不到模块: {MODULE_PATH}"
    s = load_module()
    print("[1/3] 模块导入成功")

    # ---- 工具注册 ----
    tools = asyncio.run(s.mcp.list_tools())
    names = sorted(t.name for t in tools)
    print("     已注册工具:", names)
    assert "web_search" in names, f"缺少 web_search，实际: {names}"
    assert "search_news" in names, f"缺少 search_news，实际: {names}"
    print("[2/3] 工具注册正确")

    # ---- 结果格式化 ----
    sample = {
        "results": [
            {"url": "https://a.com/1", "title": "T1", "content": "C1",
             "engine": "baidu", "engines": ["baidu", "bing"],
             "publishedDate": "2026-10-11T09:00:00"},
            {"url": "https://a.com/1", "title": "重复URL", "content": "C2",
             "engine": "ddg"},
            {"url": "https://a.com/2", "title": "T2", "content": "C3",
             "engine": "bing"},
        ],
        "answers": [{"answer": "直答内容 42"}],
        "unresponsive_engines": [["google", "timeout"]],
    }
    out = s._fmt_results(sample, limit=5)
    assert out.count("https://a.com/1") == 1, "URL 去重失败"
    assert "直接答案" in out, "instant answer 未提取"
    assert "baidu/bing" in out, "多引擎置信标记缺失"
    assert "无响应" in out, "引擎健康提示缺失"
    print("[3/3] 结果格式化正确（去重 / 直答 / 置信标记 / 健康提示）")

    # ---- 错误降级 ----
    r = s.web_search("test", limit=1)
    assert "搜索失败" in r, f"错误未优雅降级，实际返回: {r[:120]}"
    print("     错误降级正常:", r[:60].replace("\n", " "))

    print("\n全部冒烟测试通过 ✅")


if __name__ == "__main__":
    main()
