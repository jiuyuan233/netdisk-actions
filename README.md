# 网盘下载机(OpenList + GitHub Actions + 飞书通知)

用 GitHub Actions 当下载机:**网页上点几下按钮**,文件就从你的网盘下载到 GitHub,飞书收到完成通知,你随时把文件取回本地。全程不需要电脑开机,本地不需要装任何东西。

- 所有凭证只存 GitHub Secrets,仓库可公开也可私有
- 支持:百度、阿里云盘、夸克、UC、天翼、迅雷、123 盘、115、蓝奏云等(见 `storages.json`,配了哪个 Secret 用哪个)
- 百度/阿里的一次性刷新令牌**每次运行自动轮换回写**,授权一次永久可用

## 怎么用(全程图形界面)

### ① 看网盘里有什么

打开仓库 → **Actions** 标签 → 左侧选 **「网盘下载」** → 右侧 **Run workflow ▼** 绿色按钮,表单这样填:

```
┌────────────────────────────────────────┐
│ 操作模式   [ list  ▼ ]   ← 下拉选 list  │
│ 路径      [ /baidu            ]         │
│ 文件名过滤 [                ]           │
│ 目录深度   [ 2 ▼ ]                      │
│        [ 绿色 Run workflow 按钮 ]       │
└────────────────────────────────────────┘
```

半分钟后**飞书**收到这个路径下的文件清单(带大小、日期)。想看更深的目录,把路径填具体些再跑一次 list。

### ② 下载

同样的表单,这次:

```
│ 操作模式   [ download ▼ ]              │
│ 路径      [ /baidu/学习资料/高数  ]     │   ← 填文件的完整路径,或它所在的文件夹
│ 文件名过滤 [ *.pdf          ]  ← 可选   │
```

跑完**飞书**收到 ✅ + Release 链接。单文件上限 1G,超出会被跳过。

### ③ 取回文件

- 网页:点飞书里的 Release 链接(私有仓库会要求先登录 GitHub)→ Assets 里点文件下载
- 命令:`gh release download --repo 你的用户名/netdisk-actions --dir D:\下载`(会自动选最新)
- **手机**:装 GitHub 官方 App,一样能触发 workflow、一样能下载附件

## 搭建步骤(新机器部署,约 10 分钟)

1. 把本仓库文件推到一个新仓库(公开/私有均可;私有有 2000 分钟/月的 Actions 配额,本用量足够)
2. 配 Secrets(Settings → Secrets and variables → Actions):

| Secret 名 | 说明 |
|---|---|
| `OPENLIST_ADMIN_PASS` | 随机强密码即可,内部通信用 |
| `FEISHU_WEBHOOK` | 飞书自定义机器人 webhook 地址 |
| `REPO_PAT` | 一个对本仓库有管理权限的 PAT(用于回写轮换令牌) |
| `BAIDU_REFRESH_TOKEN` | 百度,用 [OpenList Token 工具](https://api.oplist.org) 授权获取"刷新令牌" |
| `QUARK_COOKIE` 等 | 夸克/UC/天翼/迅雷/123/115 的网页 cookie,蓝奏云账密,字段见 `storages.json` |

3. 各驱动字段名以 [doc.oplist.org](https://doc.oplist.org) 为准;挂载失败时 Actions 日志会列出可用驱动名

## 令牌轮换机制(百度/阿里用户必读)

百度、阿里的 `refresh_token` 是**一次性**的:每次用它换取 access_token 后就作废,新令牌由 OpenList 写进数据库。本项目的处理:

1. 每次运行挂载完成后,`bootstrap_storages.py` 立即比对数据库里的最新令牌与 Secret 原值
2. 有变化 → 加密(PyNaCl sealed box)回写到对应 Secret(靠 `REPO_PAT`)
3. 任务结束还有一次兜底回写;`concurrency` 锁保证不会有两个运行同时消耗令牌

所以:**授权一次,之后全自动**。cookie 类网盘(夸克/天翼/迅雷等)令牌不轮换,过期才需要手动换 Secret。

## 维护

- 某网盘 ❌ 且日志显示 `expired_token`/`refresh token has been used` → 回写失败了(比如 REPO_PAT 失效),重新授权拿新令牌更新对应 Secret 即可
- cookie 类网盘失败 → 浏览器重新取 cookie → 更新对应 Secret
- 修改要下载行为(如 1G 上限)→ 改 `.github/workflows/download.yml`

## 已知限制与风险

- 单文件上限 1G(`--max-size 1G`);Release 单文件上限 2GiB;runner 磁盘约 14G
- 速度看账号:百度非会员直链慢(机房 IP 更明显);阿里/夸克/123/天翼一般较快。不破解任何限速
- 私有仓库注意 Actions 分钟数(2000/月,账号级共享);慢速大文件一次最多吃 120 分钟(超时保护)
- 网盘风控偶尔会拒绝机房 IP,重跑通常就好
- 每次 OpenList 都是全新实例 + 动态挂载,`OPENLIST_ADMIN_PASSWORD` 环境变量完成初始化(v4 机制)

## 后续可扩展

- 分享链接自动转存:夸克可接 [Cp0204/quark-auto-save](https://github.com/Cp0204/quark-auto-save)
- `repository_dispatch` webhook 触发,配合其他自动化
