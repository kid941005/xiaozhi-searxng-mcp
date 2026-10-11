# 上传到 GitHub + 发布 Docker 镜像 —— 操作指引

> 仓库已发布：<https://github.com/kid941005/xiaozhi-searxng-mcp>
> 本文档记录初始发布流程，后续更新用 `git push` 即可。

---

## 一、仓库结构

```
xiaozhi-searxng-mcp/
├── .github/workflows/
│   ├── docker-publish.yml   # 自动构建并推送 ghcr.io（tag + main + 手动）
│   └── ci.yml               # 语法检查 + 冒烟测试
├── search_mcp/search_mcp.py # MCP 服务主体（stdio/http/sse）
├── tests/smoke_test.py      # 冒烟测试（无 SearXNG 也能跑）
├── bridge.py                # 小智桥接入口（MODE=bridge 时使用）
├── mcp_config.json          # 子服务声明
├── searxng/settings.yml     # SearXNG 配置模板
├── Dockerfile               # 多阶段构建 + 非 root
├── docker-compose.yml       # 三种 profile：bridge / all / http
├── entrypoint.sh            # 按 MODE 分发 mcp / bridge
├── requirements.txt
├── .env.example / .gitignore / .gitattributes / .dockerignore
├── LICENSE                  # MIT
├── README.md
└── PUBLISHING.md            # 本文件
```

- 共 **18** 个受版本控制的文件
- `.venv` / `.env` / `__pycache__` 已被正确忽略
- `entrypoint.sh` 为 **LF 行尾**（`.gitattributes` 锁定，容器内可执行）
- 所有 JSON / YAML 语法校验通过

---

## 二、发布到 GitHub

已完成的步骤（保留记录）：

```bash
git remote add origin https://github.com/kid941005/xiaozhi-searxng-mcp.git
git push -u origin main
```

> 首次推送需登录。推荐用 **Personal Access Token**（Settings → Developer settings
> → Personal access tokens → Tokens (classic) → 勾 `repo` + `write:packages`），
> 密码处粘贴 token。

---

## 三、镜像自动发布

推送到 main 后，Actions 会**自动**构建多架构镜像并推到 ghcr.io。

### 触发方式

| 操作 | 结果 |
|---|---|
| push 到 `main` | 生成 `latest` 标签 |
| 推 `v1.0.0` tag | 生成 `1.0.0`、`1.0`、`1` 标签 |
| Actions 页面手动触发 | 可自定义标签 |

打 tag 发版本：

```bash
git tag v1.0.0
git push origin v1.0.0
```

### ⚠️ 桥接 SDK 不在默认镜像里

官方镜像**默认不含**小智桥接 SDK（`MCP_BRIDGE_SDK=0`）。
`MODE=bridge` 需要自行构建：

```bash
docker build --build-arg MCP_BRIDGE_SDK=1 -t xiaozhi-searxng-mcp:bridge .
```

若希望 CI 也产出带 bridge 的镜像，可在 `docker-publish.yml` 的
`build-push-action` 步骤加：

```yaml
build-args: |
  MCP_BRIDGE_SDK=1
```

（会显著增大镜像体积，按需开启。）

### 让镜像可被公开拉取（重要）

ghcr.io 的包**默认私有**，别人 `docker pull` 会 401。发布后需手动开放：

1. 打开 `https://github.com/users/kid941005/packages/container/xiaozhi-searxng-mcp`
2. 右下角 **Package settings** → **Danger Zone** → **Change visibility**
3. 选 **Public** → 确认

### 无需额外密钥

workflow 用的是内置 `GITHUB_TOKEN`，**不需要**你配置任何 secret。

---

## 四、发布后用户怎么用

```bash
# HTTP 模式（用官方镜像即可）
docker run -d --name xiaozhi-search -p 8765:8765 \
  -e MCP_TRANSPORT=http \
  -e SEARXNG_URL="http://192.168.1.10:8080" \
  ghcr.io/kid941005/xiaozhi-searxng-mcp:latest

# 桥接模式（需先自行构建带 SDK 的镜像）
docker run -d --name xiaozhi-search \
  -e MODE=bridge \
  -e MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=..." \
  -e SEARXNG_URL="http://192.168.1.10:8080" \
  xiaozhi-searxng-mcp:bridge
```

---

## 五、验证清单

Push 后依次确认：

- [ ] GitHub 仓库页面能看到全部 18 个文件
- [ ] Actions 里 `docker-publish` 跑绿
- [ ] Packages 页面出现镜像
- [ ] 镜像可见性已改为 Public
- [ ] 本地能 `docker pull ghcr.io/kid941005/xiaozhi-searxng-mcp:latest`

---

## 六、可选增强

| 想要 | 怎么做 |
|---|---|
| 加 Docker Hub 同步发布 | 在仓库 Secrets 加 `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`，workflow 加一段 login + 多推送一个 registry |
| 加 issue 模板 | 建 `.github/ISSUE_TEMPLATE/bug_report.md` |
| 版本号管理 | 用 tag 驱动，已配置 semver 标签规则 |
| 收录到 MCP Registry | 参考 GitHub MCP Registry 提交规范 |
