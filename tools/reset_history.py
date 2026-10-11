#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把远端 main 重写为单次干净提交（Git Data API: blobs -> tree -> commit -> 强制更新 ref）。
用于清理「逐文件 API 上传」产生的 18 个碎片提交。
用法：python tools/reset_history.py <token>
"""

import os
import sys
import json
import base64
import urllib.request
import urllib.error

TOKEN = sys.argv[1]
REPO = "kid941005/xiaozhi-searxng-mcp"
BRANCH = "main"
API = "https://api.github.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def api(method, path, payload=None):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {TOKEN}")
    req.add_header("User-Agent", "wb-reset")
    req.add_header("Accept", "application/vnd.github+json")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"message": body[:400]}


def collect():
    """收集工作区文件（跳过 .git 等），返回相对路径列表。"""
    skip = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    out = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in skip]
        for fn in fns:
            rel = os.path.relpath(os.path.join(dp, fn), ROOT).replace("\\", "/")
            out.append(rel)
    return sorted(out)


# ① 为每个文件建 blob
entries = []
for rel in collect():
    with open(os.path.join(ROOT, rel), "rb") as f:
        content = base64.b64encode(f.read()).decode()
    st, blob = api("POST", f"/repos/{REPO}/git/blobs",
                   {"content": content, "encoding": "base64"})
    if st not in (200, 201):
        print(f"  ✗ blob {rel}: {st} {blob.get('message')}")
        sys.exit(1)
    entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    print(f"  ✓ blob {rel}")

# entrypoint.sh 需要可执行位
for e in entries:
    if e["path"] == "entrypoint.sh":
        e["mode"] = "100755"

# ② 建 tree
st, tree = api("POST", f"/repos/{REPO}/git/trees",
               {"tree": entries})
if st not in (200, 201):
    print("tree 失败:", st, tree.get("message"))
    sys.exit(1)
print(f"tree: {tree['sha']}")

# ③ 建 commit（无父提交 = 全新历史）
msg = """feat: 小智 x SearXNG 联网搜索 MCP 服务

把自建 SearXNG 变成小智（xiaozhi-esp32）可调用的联网搜索能力。

- search_mcp: MCP 搜索服务，暴露 web_search / search_news 两个工具
- 支持 stdio / http / sse 三种传输，兼容 mcp SDK 1.x 与 2.x
- MODE=mcp 只跑搜索服务；MODE=bridge 同时桥接到小智云端
- 多阶段 Docker 构建，非 root 运行，amd64 + arm64
- GitHub Actions 自动构建推送到 ghcr.io
- 结果针对语音场景优化：去重、多引擎置信标记、直答提取、长度控制
- 错误优雅降级，避免 AI 幻觉
- 附 SearXNG settings.yml 模板（已开启 JSON 输出、关闭 limiter）

已知：SearXNG 必须开启 search.formats: json，否则 API 返回 403。"""

st, commit = api("POST", f"/repos/{REPO}/git/commits",
                 {"message": msg, "tree": tree["sha"], "parents": []})
if st not in (200, 201):
    print("commit 失败:", st, commit.get("message"))
    sys.exit(1)
print(f"commit: {commit['sha']}")

# ④ 强制更新分支引用（force=True）
st, ref = api("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}",
              {"sha": commit["sha"], "force": True})
if st not in (200, 201):
    print("更新 ref 失败:", st, ref.get("message"))
    sys.exit(1)
print(f"\n✅ {BRANCH} 已重置为单次提交: {commit['sha'][:8]}")
