# 交接文档(给下一个维护者/AI)

> 最后更新:2026-11-15。本仓库是一台**个人网盘下载机**,已完整验证可用。
> 接手前请读完本文;改任何东西之前,先看第 5 节的"坑清单"。

## 1. 项目现状(功能 | 状态 | 证据)

| 功能 | 状态 | 证据/说明 |
|---|---|---|
| OpenList 无头挂载百度网盘 | ✅ 可用 | list 冒烟测试多次成功;`/baidu` 可列全盘 |
| 图形化触发(list/download/selftest 三模式) | ✅ 可用 | 表单:模式 + 网盘下拉 + 子路径 |
| list 模式(目录清单→飞书) | ✅ 可用 | run 43719043574 成功,明细只发飞书不进公开日志 |
| download 模式(aria2 16 线程直链 + rclone 回退) | ✅ 可用 | run 43693130446:868MB 文件 3h10min 下载成功,字节数与原件一致 |
| 大文件断点续传 + 自动接力 | ✅ 已上线(未实测触发) | cache 存半成品+aria2 控制文件,190min 软超时,自动排队下一轮(上限 10 轮) |
| 令牌轮换自动回写(百度/阿里) | ✅ 可用 | 已两次验证自动回写;**重要**:百度/阿里 refresh_token 是一次性的 |
| 飞书通知 | ✅ 可用 | list/download/自检/AI 维护都有通知 |
| 自检模式(一键只读验证) | ✅ 可用 | run 43721397568:列表/取直链/分段拉取 64KB 全通过,不写网盘 |
| AI 维护流程(Actions 里调大模型改仓库开 PR) | ⚠️ 已上线待复测 | 全链路已实现,实测在 Cloudflare 1010(已修 UA),**下一 AI 接手后先复测一次** |
| 已下载样例 | 868MB 高数 zip | Release `dl-20261115-111930`(**已转草稿**,公开不可见,登录后可见) |

**当前唯一挂载的网盘:百度**(`BAIDU_REFRESH_TOKEN`)。其他 8 个网盘的配置已就位,配了 Secret 即用(见 `docs/网盘配置教程.md`)。

## 2. 架构与数据流

```
人(网页/手机)在 Actions 表单触发
  → runner 启动全新 OpenList(OPENLIST_ADMIN_PASSWORD 环境变量完成初始化,v4 机制)
  → scripts/bootstrap_storages.py 调管理 API,把 Secrets 里的凭证动态挂载成存储
  → (download) /api/fs/get 拿直链 → aria2c 16 线程分段下载,失败回退 rclone(WebDAV)
  → 190min 软超时:未完成则进度存 Actions Cache + 自动排队下一轮(断点续传)
  → 完成后 gh release create 上传(中文文件自动改安全名,原名进 notes)
  → 飞书 webhook 通知;bootstrap 的 --sync-only 兜底回写轮换令牌
```

## 3. 文件地图

| 文件 | 作用 |
|---|---|
| `.github/workflows/download.yml` | 主流程:list / download / selftest 三模式 |
| `.github/workflows/test-mount.yml` | 挂载冒烟测试(列根目录发飞书) |
| `.github/workflows/ai-maintain.yml` | AI 维护流程(调大模型改仓库、开 PR) |
| `scripts/bootstrap_storages.py` | 按 storages.json 动态挂载 + 令牌轮换回写(--sync-only 为兜底回写模式) |
| `scripts/ai_maintain.py` | AI 维护脚本(白名单/密钥泄漏/YAML 顶格三重护栏) |
| `storages.json` | **网盘配置的唯一权威**:mount_path、driver 名、字段(env:SECRET 占位) |
| `docs/网盘配置教程.md` | 每个网盘的配置教程(驱动名/字段已对照 OpenList v4.2.9 源码核实) |
| `docs/HANDOVER.md` | 本文 |

## 4. Secrets 清单

| Secret | 用途 | 备注 |
|---|---|---|
| `OPENLIST_ADMIN_PASS` | OpenList 初始化密码 | 随机值,不外泄 |
| `FEISHU_WEBHOOK` | 飞书通知 | |
| `REPO_PAT` | 令牌回写 + 自动接力排队 | **换 PAT 时必须同步更新此值**,否则轮换机制断 |
| `BAIDU_REFRESH_TOKEN` | 百度令牌(自动轮换中) | |
| `AI_API_KEY` / `AI_API_BASE` | AI 维护用的 OpenAI 兼容接口 | 现为 ChatAnywhere,可换 |

其余网盘的 Secret 见教程,配了即用,没配自动跳过。

## 5. 坑清单(全部踩过,改代码前必读)

1. **workflow 的 `run: |` 块内出现顶格续行会切断块标量** → 整个文件解析失败(name 退化为路径、dispatch 报 422)。本项目踩过**两次**。写多行 shell 字符串一律用单行 `printf`,或确认续行缩进在块内。写入前可用脚本里的 `yaml_col0_check` 思路自查。
2. **workflow_dispatch 的 choice options 里数字开头的项必须加引号**(`"115"`),否则 YAML 解析成整数,schema 校验失败。
3. **OpenList v4 首次启动不自动建 admin**:必须设置环境变量 `OPENLIST_ADMIN_PASSWORD`(精确名,`OPENLIST_ADMIN_PASS` 无效)。`openlist admin set` 在无 admin 时静默失败(源码只 Log.Errorf)。
4. **OpenList 日志写 `log/log.log` 文件而不是 stdout**,调试要看文件。
5. **GitHub Secrets 不自动注入环境变量**,步骤必须显式 `${{ secrets.X }}` 映射;未配置的 Secret 是空字符串。
6. **storages.json 所有字段显式写全**,不依赖网页表单默认值(API 创建存储不会补默认值;百度空 `root_folder_path` → errno 2 → 列目录恒空)。
7. **驱动名以 `docs/网盘配置教程.md` 为准**(源码核实):迅雷=`Thunder`、天翼=`189Cloud`、115=`115 Cloud`。
8. **百度/阿里 refresh_token 一次性**:每轮运行轮换,靠 bootstrap 自动回写 Secret 续命;手动取消/硬超时杀掉任务时回写会丢(软超时 190min 的受控退出不受影响)。
9. **GitHub Release 资产名不支持非 ASCII**:中文文件名会被改成 `default.zip`,流程已自动改安全名并把原名写进 notes。
10. **公开仓库的运行日志人人可见**:目录明细只发飞书;若临时调试打印过文件名,跑完删掉该次运行(API: DELETE /actions/runs/{id})。
11. **进行中的 run 拿不到日志**(API 只在结束后给),监控进度靠 jobs 的 step status 轮询。
12. **本地直连 github.com:443 被墙**:git push 用 SSH over 443(ssh.github.com,临时密钥用完即删);api.github.com 直连正常。Actions runner 出海无此问题。
13. **Api 创建的 workflow 文件可能不注册 dispatch 触发器**,真 git push 一次即恢复。
14. **Workflow dispatch 表单回显会泄露 input 值**(如子路径),公开日志里能看到你填的路径——这是 GitHub 行为,属可接受范围,介意就删运行记录。
15. **百度 OpenList 官方应用是只读 scope**:列表/下载正常,但上传、创建目录全部 403(mkParentDir/unchunked update)。所以 selftest 是只读模式,任何"往百度传文件"的功能都不可行。
16. **ChatAnywhere 等 Cloudflare 站点会拦非浏览器 UA**(error 1010):脚本请求必须带正常 User-Agent。
17. **顶格续行坑出现了三次**(两次 hand-write,一次本人),说明靠自觉不行——提交前跑:`grep -nP '^\S' <workflow> | grep -vP '(name|on|permissions|concurrency|jobs):'`,有输出就是断了。

## 6. 验证手册(改完任何东西,按顺序跑)

1. **语法**:推送后看 Actions 里 workflow 名是否正常显示(若显示为文件路径 = YAML 解析失败);dispatch 是否 422。
2. **一键自检**:Run workflow → 模式 `selftest`、网盘选已配置的、子路径填文件夹或留空 → 约 2 分钟 → 飞书收 🧪(只读验证:挂载/列表/直链/分段拉取)。
3. **list 冒烟**:模式 `list`、子路径填个文件夹 → 飞书收目录清单。
4. **下载 e2e**:挑个小文件(≤100MB)跑 `download` → 飞书收 ✅ + Release 链接 → 下载文件核对大小。
5. **AI 维护**:给个无害任务(如"检查两份文档关于大小上限的表述是否一致")→ 应开出 PR。⚠️ **接手后第一件事:复测 AI 维护**——上一轮实测被 Cloudflare 1010 拦截,已修 UA 但未复测。

## 7. AI 维护流程(让 Actions 里的 AI 更新这个仓库)

**原理**:`ai-maintain.yml` 触发后,`scripts/ai_maintain.py` 把任务描述 + 白名单内文件的当前内容发给 OpenAI 兼容接口,要求 AI **只输出 JSON** `{"summary","files":[{"path","content"}]}`;脚本做三重安全检查(白名单/密钥泄漏/YAML 顶格)后写入,提交到 `ai/patch-*` 分支并**开 PR**,飞书推送审核链接。

**怎么用**:Actions → AI 维护 → Run workflow → 在 `task` 里用中文写任务,例如:
- 「把 download.yml 里的 OPENLIST_VERSION 升级到 OpenList 最新稳定版,并检查教程里版本相关描述」
- 「 storages.json 里 123Pan 的用户报错 errno xx,根据 docs/网盘配置教程.md 排查字段」
- 「给 README 增加常见问题 FAQ 章节」

**审核纪律**:AI 的产出**必须人工审核后才合并**(看 diff 是否越权、是否破坏字段显式原则);合并前跑一次 selftest 验证。PR 由 GITHUB_TOKEN 创建,不会递归触发 workflow(天然防死循环)。

**给下一代 AI 维护者的建议**:
- 改 workflow 前先重读第 5 节坑 1/2;改 storages.json 前先读教程和坑 6/7
- 任何改动后必须走第 6 节验证手册,不许跳过
- 保持"现成项目优先"原则:本仓库的自研代码只有两个 python 胶水脚本和 yaml,不要膨胀

## 8. 待办/路线图(按价值排序)

1. **配一个快网盘**(阿里/123/夸克,教程现成)——百度限速 ~80-250KB/s,快网盘是数量级提升
2. **分享链接自动转存**:夸克接 Cp0204/quark-auto-save 思路,省掉手机手动转存
3. **download_api 提速实验**:百度驱动有 `crack`/`crack_video` 通道(storages.json 改一个词),部分账号更快,自担风险
4. **定时自检**(可选):加 schedule 每周跑一次 selftest,cookie 过期早知道(公开仓库分钟免费)
5. **取消/硬超时的进度保存**:当前手动取消不会存断点(软超时会),若在意可探索 post 阶段方案

## 9. 凭证安全备忘

- 2026-11-15 有过多组凭证在对话中明文泄露的事件,相关 key 均应已轮换;`REPO_PAT`/`AI_API_KEY` 当前值来自那次泄露,**换新后记得更新同名 Secret**
- 新 PAT 权限:本仓库 repo/secrets 即可,不要用全权限 token
