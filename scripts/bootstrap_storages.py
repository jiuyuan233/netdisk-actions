#!/usr/bin/env python3
"""按 storages.json 通过 OpenList 管理 API 动态挂载网盘。

敏感值(cookie/token/密码)一律不进仓库,写法: "env:SECRET名" —— 运行时从
环境变量读取(即 GitHub Secrets)。某个环境变量没配置时,自动跳过该条挂载,
所以这份清单可以直接放在公开仓库里,你实际只用其中几个网盘也互不影响。
仅使用 Python 标准库,无需 pip 安装。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("OPENLIST_URL", "http://127.0.0.1:5244")


def request_api(path, data=None, token=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode() if data is not None else None,
        method="POST" if data is not None else "GET",
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
    if resp.get("code") != 200:
        raise RuntimeError(resp.get("message", str(resp)))
    return resp.get("data")


def resolve(value):
    """env:NAME → 从环境变量读;没配置返回 None;其他值原样返回。"""
    if isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:]) or None
    return value


def main():
    user = os.environ.get("OPENLIST_ADMIN_USER") or "admin"
    password = os.environ.get("OPENLIST_ADMIN_PASS")
    if not password:
        sys.exit("::error::未配置 Secret OPENLIST_ADMIN_PASS")
    time.sleep(1)

    token = request_api("/api/auth/login", {"username": user, "password": password})["token"]

    with open("storages.json", encoding="utf-8") as f:
        entries = json.load(f)

    created = 0
    for ent in entries:
        mount, driver = ent["mount_path"], ent["driver"]
        fields, missing = {}, None
        for key, val in ent.get("fields", {}).items():
            got = resolve(val)
            if got is None:
                missing = val[4:] if isinstance(val, str) and val.startswith("env:") else "?"
                break
            fields[key] = got
        if missing:
            print(f"⏭ 跳过 {mount}({driver}):未配置 Secret {missing}")
            continue

        # 拉取该驱动的字段模板,把默认值和用户填写的值合并(模拟网页表单的完整提交)
        try:
            info = request_api(f"/api/admin/driver/info?driver={urllib.parse.quote(driver)}", token=token)
            template = info.get("template") if isinstance(info, dict) else None
            if template:
                defs = json.loads(template) if isinstance(template, str) else template
                for field in defs:
                    default = field.get("default")
                    if field.get("name") not in fields and default not in (None, ""):
                        fields[field["name"]] = default
        except Exception as e:
            print(f"⚠ {mount}: 读取驱动模板失败({e}),仅用你填写的字段继续")

        body = {
            "mount_path": mount,
            "driver": driver,
            "addition": json.dumps(fields, ensure_ascii=False),
            "cache_expiration": 30,
        }
        try:
            request_api("/api/admin/storage/create", body, token=token)
            created += 1
            print(f"✅ 已挂载 {mount} → {driver}")
        except RuntimeError as e:
            names = []
            try:
                names = request_api("/api/admin/driver/list", token=token) or []
            except Exception:
                pass
            sys.exit(
                f"::error::挂载 {mount}({driver}) 失败: {e}\n"
                f"检查驱动名/字段名(参考 doc.oplist.org)。可用驱动名: {', '.join(map(str, names))}"
            )

    if created == 0:
        sys.exit("::error::一个网盘都没挂载——请检查 storages.json 和对应 Secrets")
    print(f"共挂载 {created} 个网盘,就绪")


if __name__ == "__main__":
    main()
