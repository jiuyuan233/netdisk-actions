# 网盘下载机(OpenList + GitHub Actions + 飞书通知)

用 GitHub Actions 当下载机:**网页上点几下按钮**,文件就从你的网盘下载到 GitHub,飞书收到完成通知,你随时把文件取回本地。全程不需要电脑开机,本地不需要装任何东西。

- 所有凭证只存 GitHub Secrets,仓库可公开也可私有
- 支持:百度、阿里云盘、夸克、UC、天翼、迅雷、123 盘、115、蓝奏云等(见 `storages.json`,配了哪个 Secret 用哪个)
- 百度/阿里的一次性刷新令牌**每次运行自动轮换回写**,授权一次永久可用
- 大文件**分段下载 + 跨任务断点续传**,超时自动接力,下载完成自动拼合

## 路径对照表(权威版本,三处保持一致)

表单里的「网盘」下拉 = `storages.json` 里的 `mount_path` = OpenList 里看到的挂载名。**子路径 = 挂载名之后的部分**。

| 网盘 | 需要的 Secret | 表单「网盘」选 | 完整路径示例 |
|---|---|---|---|
| 百度网盘 | `BAIDU_REFRESH_TOKEN` | `baidu` | `/baidu/学习资料/xx.pdf` |
| 夸克 | `QUARK_COOKIE` | `quark` | `/quark/资源/xx.mkv` |
| UC 网盘 | `UC_COOKIE` | `uc` | `/uc/...` |
| 阿里云盘 | `ALIYUN_REFRESH_TOKEN` | `aliyun` | `/aliyun/...` |
| 天翼云盘 | `CLOUD189_USER` + `CLOUD189_PASS` | `cloud189` | `/cloud189/...` |
| 迅雷云盘 | `XUNLEI_USER` + `XUNLEI_PASS` | `xunlei` | `/xunlei/...` |
| 123 云盘 | `PAN123_USER` + `PAN123_PASS` | `123pan` | `/123pan/...` |
| 115 网盘 | `PAN115_COOKIE` | `115` | `/115/...` |
| 蓝奏云 | `LANZOU_USER` + `LANZOU_PASS` | `lanzou` | `/lanzou/...` |

> 🤝 **接手维护/想了解全部机制**:看 [docs/HANDOVER.md](docs/HANDOVER.md)(现状、坑清单、验证手册、AI 维护指南)。

> 📖 **每个网盘的详细配置教程(驱动名、字段、cookie 获取步骤、常见报错)见 [docs/网盘配置教程.md](docs/网盘配置教程.md)**——驱动名与字段已逐个对照 OpenList v4.2.9 源码核实(迅雷=`Thunder`、天翼=`189Cloud`、115=`115 Cloud`,别用想当然的名字)。

> 以后在别处(本地/NAS)跑 OpenList,也请用同一套挂载名,路径即可通用。新增网盘:在 `storages.json` 加一行 + 配一个 Secret(驱动字段名见 [doc.oplist.org](https://doc.oplist.org),**所有字段显式写全,不要依赖默认值**)。

## 怎么用(全程图形界面)

### ① 看网盘里有什么

打开仓库 → **Actions** 标签 → 左侧选 **「网盘下载」** → 右侧 **Run workflow ▼** 绿色按钮,表单这样填:

```
┌────────────────────────────────────────────┐
│ 操作模式   [ list    ▼ ]    ← 下拉选 list   │
│ 网盘      [ baidu ▼ ]      ← 下拉选挂载名   │
│ 子路径    [ /学习资料       ]  ← 留空=根目录 │
│ 目录深度   [ 2 ▼ ]                          │
│        [ 绿色 Run workflow 按钮 ]           │
└────────────────────────────────────────────┘
```

半分钟后**飞书**收到这个路径下的文件清单(带大小、日期)。想看更深的目录,把子路径填具体些再跑一次 list。

### 🧪 一键自检(selftest 模式)

模式选 `selftest`、网盘选一个已配置的、子路径留空 → 约 2 分钟跑完「上传探针→列表→直链回源下载→字节比对→清理」全链路,飞书收 🧪 通过或 ❌ 定位。**改完任何配置先跑一次自检。**

### 🤖 AI 维护(让 Actions 里的 AI 改这个仓库)

Actions → **AI 维护** → Run workflow → `task` 里用中文写任务(如「升级 OpenList 版本号」「修复某网盘配置」)→ AI 修改文件并**自动开 PR** → 飞书收审核链接 → 人工审核合并。安全设计:文件白名单、密钥泄漏拦截、YAML 顶格断裂拦截、只开 PR 不直改 main。详见 [docs/HANDOVER.md](docs/HANDOVER.md) 第 6-7 节。

### ② 下载

同样的表单:

```
│ 操作模式   [ download ▼ ]                   │
│ 网盘      [ baidu ▼ ]                       │
│ 子路径    [ /宋浩精选【高数、线代、概率论】.zip ] │  ← 单文件或文件夹都可以
│ 文件名过滤 [ *.pdf          ]  ← 可选,只对文件夹有效 │
```

跑完**飞书**收到 ✅ + Release 链接。单文件上限 2G(Release 上限),超出部分靠断点续传多轮接力。

### ③ 取回文件

- 网页:点飞书里的 Release 链接(私有仓库会要求先登录 GitHub)→ Assets 里点文件下载
- 命令:`gh release download --repo 你的用户名/netdisk-actions --dir D:\下载`(自动选最新)
- **手机**:装 GitHub 官方 App,一样能触发 workflow、一样能下载附件
- 含中文的文件名会被 GitHub 换成安全名(如 `dl-a1b2c3d4.zip`),**原始文件名在 Release 说明里**

## 搭建步骤(新机器部署,约 10 分钟)

1. 把本仓库文件推到一个新仓库(公开/私有均可;私有有 2000 分钟/月的 Actions 配额,**大文件下载一轮就要 1~3 小时,建议公开**)
2. 配 Secrets(Settings → Secrets and variables → Actions):

| Secret 名 | 说明 |
|---|---|
| `OPENLIST_ADMIN_PASS` | 随机强密码即可,内部通信用 |
| `FEISHU_WEBHOOK` | 飞书自定义机器人 webhook 地址 |
| `REPO_PAT` | 一个对本仓库有管理权限的 PAT(用于回写轮换令牌和自动接力) |
| `BAIDU_REFRESH_TOKEN` | 百度,用 [OpenList Token 工具](https://api.oplist.org) 授权获取"刷新令牌" |
| `QUARK_COOKIE` 等 | 各网盘凭证,**名字和取法见 [docs/网盘配置教程.md](docs/网盘配置教程.md)** |

3. 各驱动字段名以 [doc.oplist.org](https://doc.oplist.org) 为准;挂载失败时 Actions 日志会列出可用驱动名和报错原因

## 令牌轮换机制(百度/阿里用户必读)

百度、阿里的 `refresh_token` 是**一次性**的:每次用它换取 access_token 后就作废,新令牌由 OpenList 写进数据库。本项目的处理:

1. 每次运行挂载完成后,`bootstrap_storages.py` 立即比对数据库里的最新令牌与 Secret 原值
2. 有变化 → 加密(PyNaCl sealed box)回写到对应 Secret(靠 `REPO_PAT`)
3. 任务结束还有一次兜底回写;`concurrency` 锁保证不会有两个运行同时消耗令牌

所以:**授权一次,之后全自动**。cookie 类网盘(夸克/天翼/迅雷等)令牌不轮换,过期才需要手动换 Secret。

## 大文件分段下载与断点续传

- 单文件用 aria2 **16 线程分段**下载(拿到直链后多连接并行),完成后自动拼合;aria2 失败自动回退 rclone 单线程
- 每轮任务有 **190 分钟软超时**:到点主动收尾,把半成品 + aria2 断点控制文件存进 Actions Cache(独立 10GB 配额)
- 飞书收到 `⏳ 已下载 X%` 后**自动排队下一轮**从断点继续(最多自动接力 10 轮),全部完成自动拼合、清缓存、发 ✅
- 下载完成前不会产生 Release;只有完整文件才会上传

## 维护

- 某网盘 ❌ 且日志显示 `expired_token`/`refresh token has been used` → 回写失败了(比如 REPO_PAT 失效),重新授权拿新令牌更新对应 Secret 即可
- cookie 类网盘失败 → 浏览器重新取 cookie → 更新对应 Secret
- 修改要下载行为(线程数/软超时/接力上限)→ 改 `.github/workflows/download.yml`

## 已知限制与风险

- Release 单文件上限 2GiB;runner 磁盘约 14G
- 速度看账号:百度非会员被**全局限速**(实测 ~80-250KB/s,多线程无效);阿里/夸克/123/天翼一般快一个数量级。本方案不破解任何限速
- 公开仓库的运行日志人人可见:目录明细只发飞书不进日志;自检用的探针文件名是固定 `selftest`,无隐私
- 公开仓库的 Release 资产任何人可下载,别把隐私/版权敏感文件留在里面
- 每次运行都是全新 OpenList 实例 + 动态挂载,`OPENLIST_ADMIN_PASSWORD` 环境变量完成初始化(v4 机制)

## 后续可扩展

- 分享链接自动转存:夸克可接 [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save)
- `repository_dispatch` webhook 触发,配合其他自动化
