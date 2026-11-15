#!/usr/bin/env python3
"""AI 仓库维护脚本:在 GitHub Actions 里调用大模型,按任务描述修改指定文件并开 PR 供人工审核。

环境变量:
  AI_API_BASE  OpenAI 兼容接口地址(默认 https://api.chatanywhere.org)
  AI_API_KEY   接口密钥(必需)
  AI_MODEL     模型名(默认 gpt-4o-mini)
  TASK         给 AI 的维护任务描述(必需)

安全设计:
  1. 文件白名单 —— AI 只能改 ALLOWED 里的文件,其余一律拒绝
  2. 密钥泄漏检查 —— AI 输出若疑似包含 API key/令牌,直接拒绝写入
  3. YAML 顶格检查 —— 本项目两次踩坑:workflow 的 run:| 块里出现顶格续行会切断块标量,
     导致整个文件解析失败,这里在写入前做静态拦截
  4. 只开 PR 不直接改 main —— 人工审核后合并
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ALLOWED = [
    "README.md",
    "storages.json",
    "docs/网盘配置教程.md",
    "docs/HANDOVER.md",
    ".github/workflows/download.yml",
    ".github/workflows/test-mount.yml",
    ".github/workflows/ai-maintain.yml",
]
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"hook/[0-9a-f-]{30,}"),
]
TOP_LEVEL_OK = re.compile(r"^(name|on|permissions|concurrency|jobs):")


def http_json(url, key, payload, timeout=120):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Cloudflare 会按签名拦截非浏览器 UA(error 1010),必须带一个正常 UA
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:400]}")


def yaml_col0_check(path, content):
    """workflow 文件里 run:| 块的顶格续行会切断块标量(本项目踩过两次),写入前拦截。"""
    for i, line in enumerate(content.splitlines()):
        if line.strip() == "" or line.startswith("#"):
            continue
        if not line[0].isspace() and not TOP_LEVEL_OK.match(line):
            sys.exit(f"::error::{path} 第 {i + 1} 行顶格内容疑似 YAML 块标量断裂,已拒绝写入:{line[:60]}")


def main():
    base = (os.environ.get("AI_API_BASE") or "https://api.chatanywhere.org").rstrip("/")
    key = os.environ.get("AI_API_KEY")
    model = os.environ.get("AI_MODEL") or "gpt-4o-mini"
    task = os.environ.get("TASK")
    if not key or not task:
        sys.exit("::error::缺少 AI_API_KEY 或 TASK 环境变量")

    context = []
    for p in ALLOWED:
        if os.path.exists(p):
            body = open(p, encoding="utf-8").read()
            context.append(f"### 文件:{p}\n```{'' if not p.endswith(('.yml', '.json')) else ''}\n{body[:14000]}\n```")

    system = (
        "你是 GitHub 仓库 netdisk-actions 的维护 AI。这是一个'网盘下载机'项目:"
        "GitHub Actions 里运行 OpenList 挂载网盘,用 rclone/aria2 下载文件到 Release,飞书通知。\n"
        "维护规则:\n"
        "1. 只允许修改这些文件:" + ", ".join(ALLOWED) + "\n"
        "2. storages.json 的 driver 名必须是 OpenList 真实驱动名(如 BaiduNetdisk/Quark/UC/AliyundriveOpen/"
        "189Cloud/Thunder/123Pan/'115 Cloud'/Lanzou),字段要显式写全,不要依赖默认值\n"
        "3. workflow 文件的 run:| 块内绝对不能出现顶格续行(会切断块标量导致整个文件解析失败)\n"
        "4. 绝对不要把任何密钥/token 写进文件\n"
        "5. 改动要保守:只做任务要求的事,不顺手重构\n"
        "6. 严格只输出一个 JSON 对象,不要 markdown 围栏,不要解释文字:"
        '{"summary":"一句话改动说明","files":[{"path":"文件路径","content":"完整的新文件内容"}]}'
        "\n如果任务不需要修改文件,files 返回空数组,并在 summary 里说明原因。"
    )
    user = "维护任务:" + task + "\n\n以下是当前仓库相关文件:\n\n" + "\n\n".join(context)

    print(f"调用模型 {model} @ {base} ...")
    resp = http_json(base + "/v1/chat/completions", key, {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.1,
    })
    content = resp["choices"][0]["message"]["content"].strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.M).strip()
    try:
        data = json.loads(content)
    except Exception:
        sys.exit("::error::AI 返回的不是合法 JSON,前 300 字:" + content[:300])

    summary = data.get("summary", "AI 维护")
    files = data.get("files", [])
    changed = []
    for f in files:
        path, new = f.get("path", ""), f.get("content")
        if path not in ALLOWED:
            print(f"⏭ 拒绝白名单外文件:{path}")
            continue
        if not isinstance(new, str) or not new.strip():
            continue
        if any(p.search(new) for p in SECRET_PATTERNS):
            sys.exit(f"::error::AI 输出疑似包含密钥,已拒绝写入 {path}")
        if path.endswith(".json"):
            try:
                json.loads(new)
            except Exception as e:
                sys.exit(f"::error::{path} JSON 校验失败:{e}")
        if path.startswith(".github/workflows/"):
            yaml_col0_check(path, new)
            if "workflow_dispatch" not in new:
                sys.exit(f"::error::{path} 丢失了 workflow_dispatch 触发器,已拒绝")
        old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
        if old == new:
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        changed.append(path)
        print(f"✏️ 已修改 {path}")

    if not changed:
        print("AI 认为无需修改文件:" + summary)
        with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
            fh.write("state=none\n")
        return

    branch = "ai/patch-" + time.strftime("%Y%m%d-%H%M%S")
    def git(*a):
        subprocess.run(["git", *a], check=True)
    git("config", "user.name", "ai-maintainer[bot]")
    git("config", "user.email", "ai-maintainer[bot]@users.noreply.github.com")
    git("checkout", "-b", branch)
    git("add", "-A")
    git("commit", "-m", "🤖 " + summary)
    git("push", "origin", branch)
    with open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a") as fh:
        fh.write(f"state=pr\nbranch={branch}\nsummary={summary}\n")
    print("分支已推送:" + branch)


if __name__ == "__main__":
    main()
