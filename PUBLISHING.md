# 上传到 GitHub + 发布 Docker 镜像 —— 操作指引

> 项目已 `git init` 并完成首次提交，仓库结构、Docker 化、CI 都已就绪。
> 你只需按下面步骤 push，镜像会自动构建。

---

## 一、当前状态

```
xiaozhi-searxng-mcp/
├── .github/workflows/
│   ├── docker-publish.yml   # 自动构建并推送 ghcr.io（tag + main + 手动）
│   └── ci.yml               # 语法检查 + 冒烟测试
├── search_mcp/search_mcp.py # MCP 服务主体（stdio/http/sse）
├── bridge.py                # 小智桥接入口
├── mcp_config.json          # 子服务声明
├── searxng/settings.yml     # SearXNG 配置模板
├── Dockerfile               # 多阶段构建 + 非 root
├── docker-compose.yml       # 三种 profile：bridge / all / http
├── entrypoint.sh            # 按 MODE 分发 mcp / bridge
├── requirements.txt
├── .env.example / .gitignore / .gitattributes / .dockerignore
├── LICENSE                  # MIT
└── README.md
```

- ✅ 已 `git init`，分支 `main`，首次提交已完成（16 个文件）
- ✅ `.venv` / `.env` 已被正确忽略
- ✅ `entrypoint.sh` 已验证为 **LF 行尾**（容器内可执行）
- ✅ 所有 JSON / YAML 语法校验通过

---

## 二、Push 到 GitHub

### 步骤 1：在 GitHub 网页上建空仓库

1. 打开 https://github.com/new
2. Repository name 填 `xiaozhi-searxng-mcp`
3. **不要**勾选 "Add a README / .gitignore / license"（本地已有）
4. 点 Create repository

### 步骤 2：关联并推送

```bash
cd "C:/Users/AIPC/WorkBuddy/123/xiaozhi-searxng-mcp"

# 把 yourname 换成你的 GitHub 用户名
git remote add origin https://github.com/yourname/xiaozhi-searxng-mcp.git

git push -u origin main
```

> 首次推送会要求登录。推荐用 **Personal Access Token**（Settings → Developer settings
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

### 让镜像可被公开拉取（重要）

ghcr.io 的包**默认私有**，别人 `docker pull` 会 401。发布后要手动开放：

1. 打开 `https://github.com/users/yourname/packages/container/xiaozhi-searxng-mcp`
2. 右下角 **Package settings** → **Danger Zone** → **Change visibility**
3. 选 **Public** → 确认

### 无需额外密钥

workflow 用的是内置 `GITHUB_TOKEN`，**不需要**你配置任何 secret。

---

## 四、README 里的占位符要改

README 和 Dockerfile 里有 `yourname`，替换成kid941005：

```bash
# 在项目目录下执行（把 yourname 换成kid941005）
sed -i 's|yourname/YOURNAME|YOURNAME|g' README.md
sed -i 's|ghcr.io/yourname|ghcr.io/kid941005|g' README.md
sed -i 's|github.com/yourname|github.com/kid941005|g' README.md Dockerfile

git add -A && git commit -m "docs: 更新仓库地址" && git push
```

> Windows 上用 Git Bash 执行；或在编辑器里全局替换 `yourname` 为kid941005。

---

## 五、发布后用户怎么用

```bash
# 一行起服务（桥接模式）
docker run -d --name xiaozhi-search \
  -e MODE=bridge \
  -e MCP_ENDPOINT="wss://api.xiaozhi.me/mcp/?token=..." \
  -e SEARXNG_URL="http://192.168.1.10:8080" \
  ghcr.io/kid941005/xiaozhi-searxng-mcp:latest
```

---

## 六、验证清单

Push 后依次确认：

- [ ] GitHub 仓库页面能看到全部 16 个文件
- [ ] Actions 里 `docker-publish` 跑绿
- [ ] Packages 页面出现镜像
- [ ] 镜像可见性已改为 Public
- [ ] 本地能 `docker pull ghcr.io/kid941005/xiaozhi-searxng-mcp:latest`
- [ ] README 里的 `yourname` 已全部替换

---

## 七、可选增强

| 想要 | 怎么做 |
|---|---|
| 加 Docker Hub 同步发布 | 在仓库 Secrets 加 `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`，workflow 加一段 login + 多推送一个 registry |
| 加徽章 | README 顶部已有 badge，替换 `yourname` 即生效 |
| 加 issue 模板 | 建 `.github/ISSUE_TEMPLATE/bug_report.md` |
| 版本号管理 | 用 tag 驱动，已配置 semver 标签规则 |
| 收录到 MCP Registry | 参考 GitHub MCP Registry 提交规范 |
