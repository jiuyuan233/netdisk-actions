#!/usr/bin/env python3
"""按 storages.json 通过 OpenList 管理 API 动态挂载网盘。

敏感值(cookie/token/密码)一律不进仓库,写法: "env:SECRET名" —— 运行时从
环境变量读取(即 GitHub Secrets)。某个环境变量没配置时,自动跳过该条挂载,
所以这份清单可以直接放在公开仓库里,你实际只用其中几个网盘也互不影响。
仅使用 Python 标准库,无需 pip 安装。

令牌轮换回写:百度/阿里等网盘的 refresh_token 每次刷新都会轮换,OpenList
把新值写进了本次运行的临时数据库。挂载完成后,本脚本会把数据库里的最新
refresh_token 与 Secret 原值比对,若发生变化则加密回写 GitHub Secret
(需要环境变量 REPO_PAT,即具有仓库管理权限的 PAT),保证下一次运行可用。
"""
import base64
import json
import os
import subprocess
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
        with urllib.request.urlopen(req, timeout=60) as r:
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


def gh_api(path, pat, data=None, method=None):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=json.dumps(data).encode() if data is not None else None,
        method=method or ("POST" if data is not None else "GET"),
    )
    req.add_header("Authorization", f"token {pat}")
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode()
    return json.loads(body) if body else None


def update_gh_secret(pat, repo, name, value):
    """用 PyNaCl sealed box 加密后更新 GitHub Actions Secret。"""
    try:
        from nacl import encoding, public
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pynacl"], check=False)
        try:
            from nacl import encoding, public
        except ImportError:
            print("⚠ pynacl 安装失败,跳过 refresh_token 回写")
            return
    key_info = gh_api(f"/repos/{repo}/actions/secrets/public-key", pat)
    pk = public.PublicKey(key_info["key"].encode(), encoding.Base64Encoder())
    sealed = public.SealedBox(pk).encrypt(value.encode())
    gh_api(f"/repos/{repo}/actions/secrets/{name}", pat,
           data={"encrypted_value": base64.b64encode(sealed).decode(), "key_id": key_info["key_id"]},
           method="PUT")


def sync_rotated_tokens(token, mounted_records):
    """比对 OpenList 数据库中的最新凭证与 Secret 原值,变化则回写。"""
    pat = os.environ.get("REPO_PAT")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not pat or not repo:
        print("⏭ 未配置 REPO_PAT,跳过 refresh_token 回写")
        return
    data = request_api("/api/admin/storage/list", token=token)
    storages = data.get("content", []) if isinstance(data, dict) else (data or [])
    by_mount = {s.get("mount_path"): s for s in storages}
    rotated = 0
    for rec in mounted_records:
        s = by_mount.get(rec["mount_path"])
        if not s:
            continue
        try:
            addition = json.loads(s.get("addition") or "{}")
        except Exception:
            continue
        for field, (secret_name, orig) in rec["secret_fields"].items():
            latest = addition.get(field)
            if latest and latest != orig:
                try:
                    update_gh_secret(pat, repo, secret_name, latest)
                    rotated += 1
                    print(f"🔄 {rec['mount_path']} 的 {secret_name} 已轮换,新值已回写 Secret")
                except Exception as e:
                    print(f"⚠ {secret_name} 回写失败:{e} —— 该网盘下次运行可能需要重新授权!")
    if rotated == 0:
        print("凭证无轮换,无需回写")


def build_records(entries):
    """根据 storages.json + 环境变量,重建"挂载记录"(哪些 token 字段来自哪个 Secret)。"""
    records = []
    for ent in entries:
        secret_fields = {}
        for key, val in ent.get("fields", {}).items():
            if isinstance(val, str) and val.startswith("env:") and key.endswith("token"):
                v = os.environ.get(val[4:])
                if v:
                    secret_fields[key] = (val[4:], v)
        if secret_fields:
            records.append({"mount_path": ent["mount_path"], "secret_fields": secret_fields})
    return records


def main():
    user = os.environ.get("OPENLIST_ADMIN_USER") or "admin"
    password = os.environ.get("OPENLIST_ADMIN_PASS")
    if not password:
        sys.exit("::error::未配置 Secret OPENLIST_ADMIN_PASS")
    time.sleep(1)

    token = request_api("/api/auth/login", {"username": user, "password": password})["token"]

    with open("storages.json", encoding="utf-8") as f:
        entries = json.load(f)

    if "--sync-only" in sys.argv:
        sync_rotated_tokens(token, build_records(entries))
        return

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

    sync_rotated_tokens(token, build_records(entries))


if __name__ == "__main__":
    main()
