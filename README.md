# xiaozhi-searxng-mcp

> 把你的**自建 [SearXNG](https://github.com/searxng/searxng)** 变成**小智（xiaozhi-esp32）**可以调用的**联网搜索**能力。

[![Build](https://github.com/kid941005/xiaozhi-searxng-mcp/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/kid941005/xiaozhi-searxng-mcp/actions/workflows/docker-publish.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GHCR](https://img.shields.io/badge/ghcr.io-xiaozhi--searxng--mcp-blue)](https://github.com/kid941005/xiaozhi-searxng-mcp/pkgs/container/xiaozhi-searxng-mcp)

**零 API Key、零费用、无限额度** —— 搜索走你自己的 SearXNG，数据不出内网。

---

## 特性

- 🔍 **联网搜索** —— `web_search` 工具，支持时间过滤 / 分类（新闻、技术等）
- 📰 **新闻搜索** —— `search_news` 工具，专为时效性话题优化
- 🔌 **三种传输** —— `stdio`（给小智 bridge）/ `http`（给远程客户端直连）/ `sse`
- 🐳 **开箱即用镜像** —— 多架构（amd64 + arm64），`docker pull` 即可
- 🎙️ **为语音场景优化** —— 结果去重、多引擎置信标记、提取直答、控制长度省 token
- 🛡️ **优雅降级** —— SearXNG 挂了返回「搜索失败」而非抛异常，避免 AI 幻觉
- 🔗 **可复用** —— 同一份服务既能接小智，也能接 Claude Desktop / Cursor / Cline
- 🧩 **兼容 mcp SDK 1.x / 2.x** —— 自动适配 `FastMCP` 与 `MCPServer` 的接口差异

---

## 快速开始

### 方式 A：Docker 镜像（推荐）

```bash
# 1. 拉镜像
docker pull ghcr.io/kid941005/xiaozhi-searxng-mcp:latest

# 2. 拿小智 MCP 接入点：
#    xiaozhi.me 控制台 → 智能体 → 配置 → 扩展能力 → MCP接入点

# 3. 起服务（桥接模式，直连小智）
docker run -d --name xiaozhi-search \
  -e MODE=bridge \
  -e MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=你的token" \
  -e SEARXNG_URL="http://你的SearXNG:8080" \
  ghcr.io/kid941005/xiaozhi-searxng-mcp:latest
```

> 桥接模式会自动拉起内部的搜索 MCP 服务并接到小智云端。

### 方式 B：docker compose（推荐，配置更清晰）

```bash
cp .env.example .env
# 编辑 .env，至少填 SEARXNG_URL 和 MCP_ENDPOINT

docker compose --profile bridge up -d     # 只跑桥接（SearXNG 你已有）
docker compose --profile all up -d        # SearXNG 也一起起
docker compose --profile http up -d       # 只暴露 HTTP，给 Claude/Cursor 直连
```

### 方式 C：本地源码

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt

# 自测搜索链路
SEARXNG_URL=http://你的地址 .venv/Scripts/python search_mcp/search_mcp.py --test "今天上证指数"

# stdio 模式
SEARXNG_URL=http://你的地址 .venv/Scripts/python search_mcp/search_mcp.py

# HTTP 模式
SEARXNG_URL=http://你的地址 .venv/Scripts/python search_mcp/search_mcp.py --transport http --port 8765
```

---

## ⚠️ 前置条件：SearXNG 必须开启 JSON 输出

这是**最常见的坑**。SearXNG 默认只输出 HTML，API 请求 `format=json` 会返回 **403 Forbidden**。

编辑 SearXNG 的 `settings.yml`：

```yaml
search:
  formats:
    - html
    - json        # ← 必须有这行
```

改完重启，验证：

```bash
curl "http://你的SearXNG/search?q=test&format=json"
# JSON = 成功；403 = 没配好
```

本仓库 `searxng/settings.yml` 已配好（还顺手关掉了 limiter，避免容器内客户端被 bot 检测拦截）。

---

## 让小智「愿意」搜索

挂上工具 ≠ 模型会调用。在小智后台智能体的**人物介绍**里加上：

```
【联网搜索规则】
1. 凡涉及实时/最新信息（新闻、天气、股价、汇率、赛事、新发布产品、
   当前时间之后发生的事），必须先调用 web_search 工具查询后再回答，
   禁止凭记忆编造。
2. 调用前先告知用户「好的，我帮你查一下」，避免长时间静默。
3. 把搜索结果概括成简短口语播报，不要念 URL 或原始 JSON。
4. 搜索失败时如实说「暂时查不到」，不要编造。
```

---

## 架构

```
   小智音箱 (ESP32-S3)
        │  Wi-Fi / 语音
        ▼
   xiaozhi.me 云端  ←→  大模型（判断要不要搜索）
        ▲                      │ 决定调用 web_search
        │  wss:// MCP 接入点     ▼
        │            ┌────────────────────────┐
        └────────────│  bridge（MODE=bridge）  │
                     │  xiaozhi_mcp 桥接层     │
                     └───────────┬────────────┘
                                 │ stdio MCP
                     ┌───────────▼────────────┐
                     │  search_mcp.py          │
                     │  web_search / search_news│
                     └───────────┬────────────┘
                                 │ GET /search?format=json
                     ┌───────────▼────────────┐
                     │  你的 SearXNG           │
                     └────────────────────────┘
```

设备侧**无需改动**。搜索能力全在服务端。

---

## 镜像标签

| 标签 | 说明 |
|---|---|
| `latest` | main 分支最新构建 |
| `1.0.0` / `1.0` / `1` | 语义化版本（推送 `v1.0.0` tag 自动生成） |

支持 `linux/amd64` 与 `linux/arm64`（树莓派 / ARM NAS 可直接用）。

---

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `MODE` | `mcp` | `mcp`=只跑搜索服务；`bridge`=同时接到小智云端 |
| `MCP_ENDPOINT` | — | **MODE=bridge 必填**，小智 MCP 接入点 |
| `MCP_TRANSPORT` | `stdio` | `stdio` / `http` / `sse` |
| `MCP_HOST` | `0.0.0.0` | http/sse 监听地址 |
| `MCP_PORT` | `8765` | http/sse 监听端口 |
| `SEARXNG_URL` | — | **必填**，SearXNG 地址（容器内不能用 localhost） |
| `SEARXNG_FORMAT` | `json` | 与 SearXNG `search.formats` 一致 |
| `SEARXNG_ENGINES` | 空 | 指定引擎，如 `baidu,bing` |
| `SEARXNG_LANGUAGE` | 空 | 如 `zh-CN` |
| `SEARXNG_TIMEOUT` | `12` | 超时秒数 |
| `SEARXNG_MAX_RESULTS` | `8` | 单次返回上限（省 token） |
| `SEARXNG_TOKEN` | 空 | SearXNG 前置鉴权时的 Bearer token |

---

## MCP 工具

### `web_search`
| 参数 | 类型 | 说明 |
|---|---|---|
| `query` | string | 搜索关键词，自然语言即可 |
| `limit` | int | 返回条数 1–8，默认 5 |
| `time_range` | string | `day` / `week` / `month` / `year`，时效性问题必填 |
| `categories` | string | `general` / `news` / `it` / `science` |

### `search_news`
| 参数 | 类型 | 说明 |
|---|---|---|
| `topic` | string | 新闻主题 |
| `limit` | int | 条数 1–8，默认 5 |

---

## 接入其他 MCP 客户端

HTTP 模式下，任何支持 MCP 的客户端都能直连（Claude Desktop / Cursor / Cline / Cherry Studio 等）：

```json
{
  "mcpServers": {
    "searxng": {
      "type": "http",
      "url": "http://你的IP:8765/mcp"
    }
  }
}
```

stdio 模式（由客户端拉起容器）：

```json
{
  "mcpServers": {
    "searxng": {
      "command": "docker",
      "args": ["run", "--rm", "-i",
               "-e", "SEARXNG_URL",
               "ghcr.io/kid941005/xiaozhi-searxng-mcp:latest"],
      "env": { "SEARXNG_URL": "http://你的SearXNG:8080" }
    }
  }
}
```

---

## 常见坑

| 现象 | 原因 | 解决 |
|---|---|---|
| **403 Forbidden** | SearXNG 没开 `formats: json` | 改 settings.yml，重启 |
| **502 / 连接被拒** | 容器内用 `localhost` 指自己 | 用服务名或宿主机 IP |
| **bridge 连不上接入点** | token 不全 / 网络不通 | 完整复制 token；测试 `api.xiaozhi.me` 连通性 |
| **工具挂上但不调用** | 提示词没强制 | 见「让小智愿意搜索」 |
| **搜索很慢** | 某些引擎超时 | 关掉连不上的引擎（国内建议关 google） |
| **HTTP 端口不是 8765** | 忘记映射端口 | `-p 8765:8765` |
| **播报念出 URL** | 提示词缺约束 | 加「不要念 URL」 |

### 国内引擎建议

`searxng/settings.yml` 已按国内环境配置：开 **百度、必应、DuckDuckGo**，关 **Google**。
有代理可打开 Google，中文时效性更好。

---

## 开发

```bash
# 语法检查
python -m compileall -q search_mcp bridge.py

# 冒烟测试（无需 SearXNG）
SEARXNG_URL=http://127.0.0.1:9 python -c "
import sys, asyncio; sys.path.insert(0,'search_mcp')
import search_mcp as s
print(sorted(t.name for t in asyncio.run(s.mcp.list_tools())))
print(s.web_search('test', limit=1))  # 应输出「搜索失败：...」
"

# 构建镜像
docker build -t xiaozhi-searxng-mcp:dev .
```

---

## 致谢与相关项目

本项目是**独立实现**，以下项目提供了参考或依赖：

- [SearXNG](https://github.com/searxng/searxng) —— 元搜索引擎本体
- [dairoot/mcp-calculator](https://github.com/dairoot/mcp-calculator) —— 小智官方 MCP 桥接 SDK
- [ihor-sokoliuk/mcp-searxng](https://github.com/ihor-sokoliuk/mcp-searxng) —— 功能更全的通用 SearXNG MCP 实现
- [78/xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) —— 小智官方固件

## License

[MIT](LICENSE)
