# Codex 额度中转（GitHub 版）

让 GitHub 的服务器每 10 分钟替你查一次 Codex 剩余额度，写进一个 Gist。
你的 ESP32 只要读那个 Gist 就行 —— 不用开电脑、不用开 VPN。

```
GitHub 服务器（在美国）
   └─ 带着你的 token 问 OpenAI：我还剩多少额度？
   └─ 把答案写进 Gist

你的 ESP32
   └─ 读 https://api.github.com/gists/xxxxx
   └─ 显示在屏幕上
```

---

## 开始前你需要

- 一个 GitHub 账号（免费的）
- 电脑上已经登录过 Codex（`C:\Users\你的用户名\.codex\auth.json` 存在）
- 大约 20 分钟

---

## 第 1 步：取出凭据

在本文件夹里，**右键 `get-credentials.ps1` → 使用 PowerShell 运行**。

如果系统提示"禁止运行脚本"，打开 PowerShell，输入：

```powershell
cd "这个文件夹的路径"
powershell -ExecutionPolicy Bypass -File .\get-credentials.ps1
```

跑完会生成 `credentials.txt`，里面两行：

```
CODEX_TOKEN=eyJhbGciOi...
CODEX_ACCOUNT_ID=8e4c....
```

同时它会告诉你 **token 什么时候过期**（一般是 10 天后）。

> ⚠️ 这个文件等于你家钥匙，别截图、别上传到 GitHub。

---

## 第 2 步：建一个仓库

1. 打开 <https://github.com/new>
2. **Repository name** 随便写，比如 `codex-usage`
3. 选 **Public**（公开仓库跑 Actions 不消耗免费额度；代码里没有密码，公开没关系）
4. 点 **Create repository**

然后把本文件夹里的东西传上去：

- 点 **uploading an existing file**
- 把这个文件夹里的 `fetch_usage.py`、`.github` 文件夹、`.gitignore` 一起拖进去
- 点 **Commit changes**

> ⚠️ **不要上传 `credentials.txt`**。
> `.github` 必须保持在根目录，路径要正好是 `.github/workflows/usage.yml`，不然 GitHub 找不到。

---

## 第 3 步：建一个 Gist（就是那个"公告栏"）

1. 打开 <https://gist.github.com>
2. **Filename** 填写：`usage.json`
3. 内容随便先写个 `{}`
4. 点 **Create public gist**
5. 看浏览器地址栏，长这样：

```
https://gist.github.com/你的用户名/a1b2c3d4e5f6a7b8c9d0
                              └──── 这串就是 GIST_ID ────┘
```

把它抄下来。

---

## 第 4 步：建一个访问令牌（给脚本写 Gist 用）

1. 打开 <https://github.com/settings/tokens>
2. 点 **Generate new token** → **Generate new token (classic)**
   - ⚠️ 必须是 **(classic)**，新的 fine-grained 令牌不支持 Gist
3. **Note** 写 `codex-usage`
4. **Expiration** 选 `No expiration`（否则过期又得重来）
5. **Select scopes** 只勾一个：**`gist`**
6. 拉到底点 **Generate token**
7. 复制那串 `ghp_...`（**只显示这一次**，关掉页面就没了）

---

## 第 5 步：把 4 个值放进保险箱

回到你的仓库页面：

**Settings → Secrets and variables → Actions → New repository secret**

一个一个加，名字必须一模一样：

| Name | Secret 填什么 |
|---|---|
| `CODEX_TOKEN` | `credentials.txt` 里 `CODEX_TOKEN=` 后面那一整串 |
| `CODEX_ACCOUNT_ID` | `credentials.txt` 里 `CODEX_ACCOUNT_ID=` 后面那一串 |
| `GIST_ID` | 第 3 步地址栏里那串 |
| `GIST_TOKEN` | 第 4 步生成的 `ghp_...` |

---

## 第 6 步：跑一次（生死关）

1. 点仓库顶部的 **Actions**
2. 左边选 **codex-usage**
3. 右边点 **Run workflow** → 绿色按钮
4. 等 20 秒，刷新，点进这次运行

**看结果：**

- ✅ **绿色对勾** → 成功！去你的 Gist 网址看一眼，`usage.json` 里应该已经有真实的百分比了
- ❌ **红色叉** → 点进去看日志，对照下面的表格

---

## 第 7 步：确认成功

直接浏览器打开你的 Gist 网址，应该看到类似：

```json
{
  "ok": true,
  "plan": "plus",
  "h5": { "used": 28, "left": 72.0, "reset": 1781276043, "win": 18000 },
  "d7": { "used": 16, "left": 84.0, "reset": 1781622947, "win": 604800 },
  "ts": 1781270000
}
```

- `h5` = 5 小时窗口，`left` 就是剩余百分比
- `d7` = 7 天窗口
- `reset` = 重置时间（Unix 时间戳，秒）

看到这个，**云端这一半就完工了**。之后它每 10 分钟自己跑，不用你管。

---

## 出错了怎么对照

| 日志里的关键字 | 原因 | 怎么办 |
|---|---|---|
| `401 Unauthorized` | token 过期或复制错了 | 重跑 `get-credentials.ps1`，更新 `CODEX_TOKEN` |
| `403 被拒绝` | GitHub 的 IP 被 Cloudflare 拦了 | 这条路走不通，得换海外 VPS 方案 |
| `写 Gist 出错 404` | `GIST_ID` 错了 | 回第 3 步重抄 |
| `写 Gist 出错 401` | `GIST_TOKEN` 错了或没勾 gist | 回第 4 步重做，确认勾了 `gist` |
| Actions 里看不到 workflow | 文件路径不对 | 必须是 `.github/workflows/usage.yml` |
| 一小时才跑一次 | GitHub 免费版定时不准 | 正常现象，额度是慢变量，不影响 |

---

## 日常维护：10 天一次

token **10 天**过期。过期那天：

1. 重跑 `get-credentials.ps1`
2. 到仓库 Settings → Secrets 更新 `CODEX_TOKEN`

**而且你不用自己记** —— 脚本失败时 GitHub 会自动发邮件给你，那封"workflow failed"的邮件就是提醒。

> 如果你电脑上的 Codex 自己换了新 token（一般它每 8 天刷一次），
> 旧 token 会立刻作废，GitHub 这边会报 401，同样按上面两步更新即可。
> 这个过程**不会影响你电脑上的 Codex**，两边互不干扰。

---

## 下一步：ESP32

云端通了之后，ESP32 要做的事只有一件：

```
GET https://api.github.com/gists/你的GIST_ID
```

返回的 JSON 里，`files["usage.json"].content` 是一段**字符串形式的 JSON**，需要再解析一次。

代码我还没写，等你告诉我板子型号（有没有屏、什么屏）再给。
