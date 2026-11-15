# 网盘下载机(OpenList + GitHub Actions + 飞书通知)

用 GitHub Actions 当下载机:手机/网页上触发一次 workflow,文件从你的网盘下载到 GitHub,飞书收到完成通知,你随时把文件取回本地。**全程不需要电脑开机,本地不需要装任何东西。**

本仓库可以**公开**:所有 cookie/token 只存在于仓库 Secrets 里,仓库中只有占位名(`storages.json` 里是 secret 变量名,不是真实值)。

## 架构

```
你(手机/网页)手动触发 workflow,填网盘路径
        │
        ▼
runner 里启动全新 OpenList 实例(管理密码来自 Secret)
        │
        ▼
bootstrap_storages.py 调用管理 API,把 Secrets 里的 cookie/token 动态挂载成网盘
        │
        ▼
rclone 经 WebDAV 拉文件(单文件上限 1G)
        │
        ▼
文件上传到 Release(每文件上限 2GiB,不占配额,自动保留最近 5 个)
        │
        ▼
飞书机器人推送结果 + Release 下载链接
```

- **引擎**: [OpenList](https://github.com/OpenListTeam/OpenList)(Alist 社区延续版),支持百度、阿里云盘、夸克、UC、天翼、迅雷、移动、123 盘、115、蓝奏云、OneDrive、Google Drive 等,驱动文档见 [doc.oplist.org](https://doc.oplist.org)。
- **为什么用 Release 而不是 Artifacts**:私有/免费账号的 Artifacts 配额只有 500MB,1GB 文件必挂;Release 附件单文件 2GiB、总量不限、不计配额。

## 搭建步骤(10 分钟,全程浏览器操作)

### 1. 建仓库

把本仓库文件推到你的 GitHub **公开**仓库(或 fork 后改)。必须包含:`.github/workflows/download.yml`、`scripts/bootstrap_storages.py`、`storages.json`。

### 2. 挑网盘,取凭证,配 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret。
**必配**:

| Secret 名 | 说明 |
|---|---|
| `OPENLIST_ADMIN_PASS` | 随便一个强密码,内部通信用,不外泄 |
| `FEISHU_WEBHOOK` | 飞书自定义机器人 webhook 地址 |

**网盘(配哪几个就能用哪几个,没配的自动跳过)**:

| Secret 名 | 去哪拿 | 对应挂载名 |
|---|---|---|
| `QUARK_COOKIE` | 夸克网页版 pan.quark.cn → F12 → 应用 → Cookies,复制 `__pus` 等整段 cookie 值 | `/quark` |
| `UC_COOKIE` | UC 网盘网页版,同上 | `/uc` |
| `ALIYUN_REFRESH_TOKEN` | 阿里云盘,用官方文档的获取工具(见 doc.oplist.org 阿里云盘 Open 驱动页) | `/aliyun` |
| `BAIDU_REFRESH_TOKEN` | 百度网盘,文档提供的 refresh_token 获取方式 | `/baidu` |
| `CLOUD189_COOKIE` | 天翼云盘网页版 F12 取 cookie | `/cloud189` |
| `XUNLEI_COOKIE` | 迅雷云盘网页版 F12 取 cookie | `/xunlei` |
| `PAN123_TOKEN` | 123 云盘,见文档 | `/123pan` |
| `PAN115_COOKIE` | 115 网页版 F12 取 cookie | `/115` |
| `LANZOU_USER` / `LANZOU_PASS` | 蓝奏云账号密码 | `/lanzou` |

> cookie 的具体字段名以 [doc.oplist.org](https://doc.oplist.org) 各驱动文档为准;如果某个网盘挂载失败,Actions 日志里会列出所有可用驱动名和报错原因,照着改 `storages.json` 即可。

### 3. 触发

Actions → 网盘下载 → Run workflow:
- `path`:如 `/quark/资源/某文件夹`(挂载名见上表)
- `include`:可选,如 `*.mkv`,留空 = 全部

## 日常使用

1. 看到好的网盘分享 → 用网盘 App **转存到自己账号**(手机上 10 秒)
2. 触发 workflow,填路径
3. 飞书收到 ✅ 通知
4. 什么时候想下载了再取:

```powershell
# 方式一:浏览器登录 GitHub,进仓库 Releases 页点文件
# 方式二:gh 命令(国内通常更快)
gh release download dl-20261115-xxxx --repo 你的用户名/仓库名 --dir D:\下载
```

## 维护:cookie 过期了怎么办

某网盘全部失败(飞书 ❌)→ 大概率 cookie 过期:浏览器重新取一次 cookie → Settings → Secrets 里更新对应值。**不需要跑任何本地程序。**

## 隐私与安全设计

- 仓库内**没有任何真实凭证**:`storages.json` 只有 `env:SECRET名` 占位;密码/cookie 全在 Encrypted Secrets
- 运行日志调低了级别,**不会打印文件名**;文件清单只发到你的飞书(私密)
- Actions 日志在公开仓库人人可看,但里面只有挂载名和统计数字
- 飞书 webhook、OpenList 管理密码均为 Secret

## 已知限制与风险(务必知情)

- **单文件上限 1G**(`--max-size 1G`,可在 workflow 里改);Release 单文件上限 2GiB;runner 磁盘约 14G
- **速度看账号**:百度非会员直链照样限速,夸克非会员有限额;阿里/天翼/123 一般较快。本方案不破解任何限速
- **GitHub ToS 灰色地带**:官方禁止把 Actions 用于与软件开发无关的大流量活动。小体积 + 低频使用风险低,别拿它当常驻下载站,别改成高频定时
- **数据中心 IP 风控**:Actions 的 IP 段偶尔被网盘风控,表现为某次解析失败,重跑通常就好;介意可用小号 cookie
- 每次运行都是全新 OpenList 实例 + 动态挂载,若 OpenList 大版本改了驱动 API,`bootstrap_storages.py` 需要跟进(锁了版本 `v4.2.9`,不受影响)

## 后续可扩展(本期未做)

- 分享链接自动转存:夸克可接 [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save),省掉手动转存一步
- `repository_dispatch` webhook 触发:配合其他自动化,POST 一下就跑
