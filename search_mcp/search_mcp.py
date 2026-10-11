#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SearXNG -> 小智（xiaozhi）MCP 搜索服务
============================================================
把你的自建 SearXNG 变成 AI 助手可调用的联网搜索工具。

支持三种传输方式：
    stdio   —— 由 MCP 客户端（或小智 bridge）拉起子进程，最常用
    http    —— Streamable HTTP，监听端口，可被远程客户端直连
    sse     —— 旧版 SSE 传输（部分老客户端仍需要）

用法：
    python search_mcp.py                      # 默认 stdio
    python search_mcp.py --transport http --port 8765
    python search_mcp.py --transport sse  --port 8765
    python search_mcp.py --test "关键词"       # 自测：直接搜一次并打印

对外暴露 MCP 工具：
    web_search(query, limit, time_range, categories)  联网搜索
    search_news(topic, limit)                          新闻搜索

依赖环境变量：
    SEARXNG_URL        你的 SearXNG 地址，如 http://192.168.1.10:8080
    SEARXNG_FORMAT     json（默认）| csv | rss —— 必须与 SearXNG 侧 formats 开启项一致
    SEARXNG_ENGINES    可选，逗号分隔，如 google,bing,duckduckgo；留空用实例默认
    SEARXNG_LANGUAGE   可选，如 zh-CN / all
    SEARXNG_TIMEOUT    请求超时秒，默认 12
    SEARXNG_MAX_RESULTS 单次最多返回条数上限，默认 8（省 token）
    SEARXNG_TOKEN      可选，若 SearXNG 前面挂了鉴权网关，填 Bearer token
    MCP_TRANSPORT      可选，stdio（默认）| http | sse，等价于 --transport
    MCP_HOST           可选，http/sse 监听地址，默认 0.0.0.0
    MCP_PORT           可选，http/sse 监听端口，默认 8765
"""

import os
import sys
import json
import argparse
import urllib.parse
import urllib.request
import urllib.error

# ---- 兼容 mcp 1.x / 2.x ----
# 1.x: from mcp.server.fastmcp import FastMCP
# 2.x: FastMCP 改名为 MCPServer（from mcp.server.mcpserver import MCPServer）
try:
    from mcp.server.fastmcp import FastMCP as _FastMCP  # type: ignore
except ImportError:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _FastMCP  # type: ignore

# ---------------- 配置 ----------------
SEARXNG_URL = os.environ.get("SEARXNG_URL", "").rstrip("/")
SEARXNG_FORMAT = os.environ.get("SEARXNG_FORMAT", "json").lower()
SEARXNG_ENGINES = os.environ.get("SEARXNG_ENGINES", "").strip()
SEARXNG_LANGUAGE = os.environ.get("SEARXNG_LANGUAGE", "").strip()
SEARXNG_TIMEOUT = float(os.environ.get("SEARXNG_TIMEOUT", "12"))
SEARXNG_MAX_RESULTS = int(os.environ.get("SEARXNG_MAX_RESULTS", "8"))
SEARXNG_TOKEN = os.environ.get("SEARXNG_TOKEN", "").strip()

if not SEARXNG_URL:
    # 不直接退出，方便 --help / 导入时不崩；真正调用时才报错
    print("[warn] SEARXNG_URL 未设置，调用搜索时会失败", file=sys.stderr)

mcp = _FastMCP("searxng-search")


def _log(msg: str):
    print(f"[searxng-mcp] {msg}", file=sys.stderr, flush=True)


# ---------------- 核心：调用 SearXNG ----------------
def searxng_query(query: str, limit: int, time_range: str = "",
                  categories: str = "", engines: str = "") -> dict:
    """请求 SearXNG，返回解析后的 JSON（或对 rss/csv 做降级处理）。"""
    if not SEARXNG_URL:
        raise RuntimeError("SEARXNG_URL 未配置")

    params = {
        "q": query,
        "format": SEARXNG_FORMAT,
        "safesearch": "0",
    }
    if limit:
        # SearXNG 的 limit 只对部分引擎生效；真正的截断由我们自己再做一次
        params["limit"] = str(limit)
    if time_range:
        params["time_range"] = time_range          # day / week / month / year
    if categories:
        params["categories"] = categories          # general, news, it, science...
    eng = engines or SEARXNG_ENGINES
    if eng:
        params["engines"] = eng
    if SEARXNG_LANGUAGE:
        params["language"] = SEARXNG_LANGUAGE

    url = f"{SEARXNG_URL}/search?{urllib.parse.urlencode(params)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; xiaozhi-searxng-mcp/1.0)",
        "Accept": "application/json, text/plain, */*",
    }
    if SEARXNG_TOKEN:
        headers["Authorization"] = f"Bearer {SEARXNG_TOKEN}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=SEARXNG_TIMEOUT) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            pass
        if e.code == 403:
            raise RuntimeError(
                "SearXNG 返回 403 —— 实例未开启 JSON 输出。"
                "请在 settings.yml 的 search.formats 里加入 json 后重启 SearXNG。"
            ) from e
        raise RuntimeError(f"SearXNG HTTP {e.code}: {body}") from e
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"无法连接 SearXNG({SEARXNG_URL}): {e!r}") from e

    if SEARXNG_FORMAT == "json":
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError("SearXNG 返回内容不是合法 JSON，请确认 format=json 已开启") from e
    # csv / rss 降级：直接原样返回，由上层包裹
    return {"results": [], "_raw": raw}


def _fmt_results(data: dict, limit: int) -> str:
    """把 SearXNG 结果整理成给 LLM 的紧凑文本（越短越省 token、越快）。"""
    out_lines = []

    # 1) instant answers / infobox：高价值，放最前
    for ans in (data.get("answers") or [])[:2]:
        if isinstance(ans, dict):
            out_lines.append(f"【直接答案】{ans.get('answer') or ans.get('content') or ans}")
        else:
            out_lines.append(f"【直接答案】{ans}")
    for box in (data.get("infoboxes") or [])[:1]:
        content = box.get("content") or ""
        if content:
            out_lines.append(f"【资料】{box.get('infobox', '')} {content}".strip())

    # 2) 常规结果
    results = data.get("results") or []
    if not results:
        if data.get("_raw"):
            return data["_raw"][:1500]
        return "没有找到相关结果。"

    seen = set()
    count = 0
    for r in results:
        url = r.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        title = (r.get("title") or "").strip()
        snippet = (r.get("content") or r.get("snippet") or "").strip()
        date = r.get("publishedDate") or ""
        engines = r.get("engines") or ([r["engine"]] if r.get("engine") else [])
        # 多引擎命中 = 可信度信号
        conf = f" [{'/'.join(engines)}]" if len(engines) > 1 else ""
        if date:
            snippet = f"({date[:10]}) {snippet}"
        out_lines.append(f"{count + 1}. {title}{conf}\n   {snippet}\n   {url}")
        count += 1
        if count >= limit:
            break

    # 3) 引擎健康提示（哪些引擎没返回，便于排查）
    unresponsive = data.get("unresponsive_engines") or []
    if unresponsive:
        names = ",".join(str(x[0]) for x in unresponsive if x)[:120]
        out_lines.append(f"\n[注意：以下引擎无响应 {names}]")

    return "\n".join(out_lines) if out_lines else "没有找到相关结果。"


# ---------------- MCP 工具 ----------------
@mcp.tool()
def web_search(query: str, limit: int = 5,
               time_range: str = "", categories: str = "") -> str:
    """联网搜索互联网上的实时信息。

    当用户询问以下类型问题时**必须调用本工具**后再回答，禁止凭记忆编造：
    - 新闻、时事、热点事件
    - 天气、气温
    - 股价、汇率、加密货币价格
    - 比赛结果、赛事比分
    - 最新发布的产品、版本、政策
    - 任何你知识截止日期之后发生的事
    - 用户明确说「搜一下 / 查一下 / 帮我找」的内容

    Args:
        query: 搜索关键词。用简洁自然语言，例如「今天上证指数」「小米SU7 上市时间」。
        limit: 返回结果条数，1-8，默认 5。问题简单就 3，需要多方对比就 8。
        time_range: 时间范围过滤，可选值：day（一天内）、week、month、year。
                    问「今天的新闻」「最近」时填 day 或 week，可显著提升时效性。
        categories: 搜索分类，可选值：general、news、it、science、images。
                    问新闻类填 news，技术类填 it。
    """
    limit = max(1, min(int(limit or 5), SEARXNG_MAX_RESULTS))
    _log(f"search: q={query!r} limit={limit} time_range={time_range!r} cat={categories!r}")
    try:
        data = searxng_query(query, limit=limit, time_range=time_range,
                             categories=categories)
        text = _fmt_results(data, limit)
        _log(f"  -> {len(text)} chars, {len(data.get('results') or [])} raw results")
        return text
    except Exception as e:  # noqa: BLE001
        _log(f"  !! error: {e!r}")
        # 返回明确错误，让模型如实告知用户「暂时查不到」，而不是幻觉
        return f"搜索失败：{e}"


@mcp.tool()
def search_news(topic: str, limit: int = 5) -> str:
    """搜索最新新闻。适合「今天有什么新闻」「XX 最近怎么样了」这类问题。

    Args:
        topic: 新闻主题关键词。
        limit: 返回条数，1-8，默认 5。
    """
    limit = max(1, min(int(limit or 5), SEARXNG_MAX_RESULTS))
    _log(f"news: topic={topic!r} limit={limit}")
    try:
        data = searxng_query(topic, limit=limit, categories="news", time_range="week")
        return _fmt_results(data, limit)
    except Exception as e:  # noqa: BLE001
        _log(f"  !! error: {e!r}")
        return f"新闻搜索失败：{e}"


def _run_server(transport: str, host: str, port: int):
    """按传输方式启动 MCP 服务，兼容 mcp SDK 1.x / 2.x。

    关键差异（实测）：
      - 1.x FastMCP：监听地址通过 mcp.settings.host / mcp.settings.port 设置
      - 2.x MCPServer：settings 里【没有】host/port，
                      而是 mcp.run(transport, host=..., port=...) 透传下去
    这里统一用「优先给 run() 传参、失败再退回 settings」的方式，两边都能跑。
    """
    import inspect

    transport = (transport or "stdio").lower()
    if transport not in ("stdio", "http", "sse"):
        _log(f"未知传输方式 {transport!r}，回退到 stdio")
        transport = "stdio"

    if transport == "stdio":
        _log("以 stdio 传输启动（等待客户端连接）")
        mcp.run(transport="stdio")
        return

    # 统一映射到 SDK 认识的名字
    sdk_transport = "streamable-http" if transport == "http" else "sse"
    path = "/mcp" if transport == "http" else "/sse"
    _log(f"以 {transport} 传输启动：http://{host}:{port}{path}")

    # ① 先试：给 run() 传 host/port（2.x 走这条）
    try:
        sig = inspect.signature(mcp.run)
        params = sig.parameters
        # run(transport, **kwargs) —— kwargs 会透传给底层实现
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD
                             for p in params.values())
        if accepts_kwargs or "host" in params:
            mcp.run(transport=sdk_transport, host=host, port=port)
            return
    except (TypeError, ValueError) as e:
        _log(f"run(host=,port=) 不适用（{type(e).__name__}），改用 settings 方式")

    # ② 退回：1.x 的 mcp.settings
    try:
        st = getattr(mcp, "settings", None)
        if st is not None and hasattr(st, "host"):
            st.host = host
            st.port = port
    except Exception as e:  # noqa: BLE001
        _log(f"设置 settings 失败：{e!r}")

    mcp.run(transport=sdk_transport)


def _selftest(q):
    try:
        data = searxng_query(q, limit=5)
        return _fmt_results(data, 5)
    except Exception as e:  # noqa: BLE001
        return f"失败: {e}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="SearXNG MCP 搜索服务")
    ap.add_argument("--transport", choices=["stdio", "http", "sse"],
                    default=os.environ.get("MCP_TRANSPORT", "stdio"),
                    help="传输方式，默认 stdio（也可用环境变量 MCP_TRANSPORT）")
    ap.add_argument("--host", default=os.environ.get("MCP_HOST", "0.0.0.0"),
                    help="http/sse 监听地址，默认 0.0.0.0")
    ap.add_argument("--port", type=int, default=int(os.environ.get("MCP_PORT", "8765")),
                    help="http/sse 监听端口，默认 8765")
    ap.add_argument("--test", metavar="QUERY", help="自测：直接搜一次并打印结果")
    ap.add_argument("--news", metavar="TOPIC", help="自测：新闻搜索")
    args = ap.parse_args()

    if args.test:
        print(_selftest(args.test))
    elif args.news:
        print(search_news(args.news))
    else:
        _run_server(args.transport, args.host, args.port)
