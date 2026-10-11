# 全仓库审计报告 —— xiaozhi-searxng-mcp

> 审计触发：用户反馈 compose 里残留 `build` 导致镜像拉取失效，要求「全仓库检查，不要再出现这种低级错误了」。
> 审计范围：全部 18 个受版本控制文件。
> 审计方式：**实际运行验证**（非纸面检查）—— 真下载 bridge SDK 复现导入失败、真实启动 HTTP 服务验证端口、真实执行 bridge 三种路径。
> 审计提交：`059da83c`（单次干净提交）

---

## 一、结论摘要

共发现 **5 类 12 处**「配置与实现不一致」问题，其中 **2 处是致命级**（功能完全不可用）。全部已修复，并新增 2 条防回归断言。

| 级别 | 问题 | 影响 |
|---|---|---|
| 🔴 致命 | `bridge.py` 导入路径错误 | `MODE=bridge` **必然启动失败**（ImportError） |
| 🔴 致命 | `mcp_config.json` 硬编码 SEARXNG_URL | 静默覆盖环境变量，连错地址且无报错 |
| 🟠 严重 | 镜像缺失 `mcp_config.json` | bridge 模式无法找到子服务声明 |
| 🟠 严重 | `entrypoint.sh` 绕过 `bridge.py` | bridge.py 沦为死代码，友好报错全部失效 |
| 🟡 中等 | compose 的 `mcp-stdio` 服务无实际通信 | 误导用户，多起一个无用容器 |
| 🟡 中等 | 文档与实现脱节（多处） | 用户照文档操作会踩坑 |

---

## 二、逐项详述

### 🔴 问题 1：`MODE=bridge` 必然失败（导入路径错误）

**证据链（实测复现）：**

1. 下载官方 SDK：`pip download xiaozhi-mcp` → 解包
2. 包内结构仅三个文件：`xiaozhi_mcp/{__init__.py, pipe.py, __main__.py}`
3. `__init__.py` 全文只有一行赋值：`__version__ = "0.2.0"` —— **不导出 `main`**
4. 实测：

```
>>> from xiaozhi_mcp import main
ImportError: cannot import name 'main' from 'xiaozhi_mcp'
```

而 `bridge.py` 第 65 行正是 `from xiaozhi_mcp import main as xz_main`。

**根因：** `main` 实际定义在 `xiaozhi_mcp/pipe.py`。`pyproject.toml` 的入口点写作
`[project.scripts] xiaozhi-mcp = "xiaozhi_mcp.pipe:main"` —— 注意是 `pipe:main`。
`python -m xiaozhi_mcp` 之所以能跑，是因为 `__main__.py` 里写了 `from .pipe import main`。

**修复：** 改为 `from xiaozhi_mcp.pipe import main as xz_main`。

**附带修复：** 原代码 `asyncio.run(xz_main()) if asyncio.iscoroutinefunction(xz_main) else xz_main()`。
实测 `iscoroutinefunction(main)` 为 `False`，且 `main()` 源码内部**已自己调用 `asyncio.run()`**。
原三元式纯属多余，简化为 `sys.exit(xz_main())`。

---

### 🔴 问题 2：`mcp_config.json` 硬编码 SEARXNG_URL

**原内容：**
```json
"env": { "SEARXNG_URL": "http://192.168.1.10:8080", ... }
```

**证据（读 SDK 源码 `pipe.py` 的 `build_server_command()`）：**
```python
child_env = os.environ.copy()
for k, v in (entry.get("env") or {}).items():
    child_env[str(k)] = str(v)      # ← 配置项覆盖进程环境变量
```

**根因：** compose 里 `SEARXNG_URL: ${SEARXNG_URL:-http://searxng:8080}` 传进来的值，
会被 `mcp_config.json` 里写死的 `192.168.1.10` **静默覆盖**。用户改了 `.env` 却完全不生效，
且没有任何报错——这正是用户抱怨的「配置与现实不符」的典型。

**修复：** 删除整个冗余 `env` 块。SDK 的 `child_env = os.environ.copy()` 保证环境变量
自然透传，无需在配置里重复声明。

---

### 🟠 问题 3：镜像缺失 `mcp_config.json`

**证据：** `grep -n mcp_config Dockerfile` → 无结果。Dockerfile 只 COPY 了
`search_mcp/`、`bridge.py`、`entrypoint.sh`。

**根因：** bridge 模式的子服务声明完全依赖 `mcp_config.json`。官方镜像里没有这个文件，
`bridge.py` / `pipe.load_config()` 返回 `{}`，随后报 "No enabled mcpServers found in config"。
compose 靠 volume 挂载才侥幸能用，`docker run` 裸跑则必挂。

**修复：** `COPY --chown=mcp:mcp mcp_config.json /app/mcp_config.json`，
并设 `ENV MCP_CONFIG=/app/mcp_config.json`。

---

### 🟠 问题 4：`entrypoint.sh` 绕过 `bridge.py`

**证据：** `entrypoint.sh` 第 36 行 `exec python -u -m xiaozhi_mcp` —— 直接调 SDK，
**从未引用 `bridge.py`**。而 `bridge.py` 被 COPY 进镜像、被 PUBLISHING.md 描述为「小智桥接入口」。

**根因：** 两条并存的入口路径互相矛盾。`bridge.py` 提供的价值（MCP_CONFIG 定位、友好中文报错、
SDK 缺失提示）在容器里全部失效，且 `python -m xiaozhi_mcp` 依赖 cwd 找 `mcp_config.json`，
行为随工作目录漂移。

**修复：** `entrypoint.sh` 改为 `exec python -u /app/bridge.py "$@"`，
让 `bridge.py` 成为唯一桥接入口。

---

### 🟡 问题 5：compose 的 `mcp-stdio` 服务无实际通信

**证据：** `bridge` 服务 `depends_on: mcp-stdio`，看似要连它。但对照 SDK 的 `pipe.py`：
`connect_to_server()` 内部用 `subprocess.Popen(build_server_command(target))` **自己拉起子进程**。
两个容器之间**没有任何 MCP 流量**，`depends_on` 只是启动顺序。

**根因：** 架构理解偏差——把「bridge 会 spawn 子进程」误解成「bridge 连接另一个容器」。

**修复：** 删除 `mcp-stdio` 服务，注释说明「bridge 自己拉起子进程，无需单独容器」。

---

### 🟡 问题 6：文档与实现脱节

| 位置 | 原文 | 实际 | 处理 |
|---|---|---|---|
| README 环境变量表 | 缺 `MCP_CONFIG` | 桥接必需 | 补充 |
| README 环境变量表 | `SEARXNG_LANGUAGE` 默认 `zh-CN` | 代码默认**空** | 改为「空；留空用实例默认」 |
| README 开发段 | `sys.path.insert(0,'search_mcp')` | CI 里这会失败 | 改为 `python tests/smoke_test.py` |
| README 快速开始 | 未提示 bridge 需自建镜像 | 官方镜像不含 SDK | 新增前置说明区块 |
| PUBLISHING | 「16 个文件」 | 实为 18 个 | 更正 |
| PUBLISHING | `yourname` 替换 sed 步骤 | 占位符早已替换完 | 删除过期步骤 |
| PUBLISHING | 缺 bridge SDK 说明 | — | 补充构建参数说明 |

---

### 🟡 附带修复（Dockerfile 卫生）

- Stage2 装了 `git` 但桥接 SDK 是注释状态 → 移除无用的 git（减体积）
- `COPY search_mcp/` 会把本地 `__pycache__` 拷进镜像 → 改为精确拷贝 `search_mcp.py` 单文件
- 桥接 SDK 改为 `ARG MCP_BRIDGE_SDK`（默认 0），需要时 `--build-arg MCP_BRIDGE_SDK=1`，
  避免默认镜像装载无用的大体积依赖

---

## 三、防回归机制（新增）

`tests/smoke_test.py` 从 3 项扩展到 5 项，新增两条断言专治本次发现的错误：

```python
# 断言 1：mcp_config.json 不得硬编码 SEARXNG_URL
for name, entry in cfg["mcpServers"].items():
    assert "SEARXNG_URL" not in (entry.get("env") or {}), \
        "会覆盖环境变量，请删除该键"

# 断言 2：bridge.py 的 main 必须从 xiaozhi_mcp.pipe 导入
for mod, names in imports:
    if "main" in names:
        assert mod == "xiaozhi_mcp.pipe", \
            "包根不导出 main，会导致 MODE=bridge 启动即 ImportError"
```

**已用负向测试验证**：故意把 `SEARXNG_URL` 写回、故意改回错误导入路径，
两次都被断言准确捕获并给出中文提示。

CI 同时新增 JSON / YAML / compose 配置解析校验。

---

## 四、验证记录（实测，非纸面）

| 验证项 | 方法 | 结果 |
|---|---|---|
| 语法 | `compileall search_mcp bridge.py tests` | ✅ 通过 |
| JSON/YAML | `json.load` + `yaml.safe_load` 全部配置文件 | ✅ 通过 |
| 冒烟测试 | `python tests/smoke_test.py` | ✅ 5/5 通过 |
| HTTP 端口透传 | 实际启动 `--port 8878` | ✅ `Uvicorn running on http://0.0.0.0:8878` |
| MCP 握手 | curl POST `initialize` | ✅ HTTP 200 + `serverInfo: searxng-search` + `mcp-session-id` |
| bridge 无 token | 子进程执行 `bridge.py` | ✅ 退出码 1 + 中文提示 |
| bridge 无 SDK | 子进程执行 `bridge.py` | ✅ 退出码 2 + 安装指引 |
| bridge 有 SDK | 装真 SDK 后执行 | ✅ 进入 `connect_with_retry`，真实连 `api.xiaozhi.me`（HTTP 401 = 假 token 被拒，链路正确） |
| 负向测试 1 | 注入硬编码 URL | ✅ 断言捕获 |
| 负向测试 2 | 注入错误导入 | ✅ 断言捕获 |
| entrypoint.sh 行尾 | 二进制检查 `\r\n` | ✅ 纯 LF |

---

## 五、遗留事项（需人工操作）

1. **ghcr.io 包改为 Public**（当前 403，别人无法拉取）
   → https://github.com/users/kid941005/packages/container/xiaozhi-searxng-mcp
   → Package settings → Danger Zone → Change visibility → Public

2. **吊销泄露的 PAT**
   对话中出现过的 `ghp_GgsM...cPBm` 应视为已泄露
   → https://github.com/settings/tokens → revoke

3. **（可选）打版本 tag**
   ```bash
   git tag v1.0.0 && git push origin v1.0.0
   ```

4. **（可选）CI 产出带 bridge 的镜像**
   在 `docker-publish.yml` 的 build-push 步骤加 `build-args: MCP_BRIDGE_SDK=1`
   （会显著增大镜像体积，按需开启）
