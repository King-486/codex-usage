# Codex 额度中转

让 GitHub 的服务器每 10 分钟替你去问一次 Codex 剩余额度，把结果写进这个仓库的
`usage.json`。手机、电脑、ESP32 随时都能读，**不用开电脑，也不用开 VPN**。

---

## 它现在在干什么

```
GitHub Actions（每 10 分钟）
   └─ 带着 CODEX_TOKEN 请求 chatgpt.com/backend-api/wham/usage
   └─ 把结果写进 usage.json 并提交

你的设备
   └─ 读下面这个地址
```

**读取地址（返回明文 JSON，不需要任何令牌）：**

```
https://api.github.com/repos/King-486/codex-usage/contents/usage.json
```

⚠️ 请求时必须带这个请求头，否则拿到的是 base64 编码：

```
Accept: application/vnd.github.raw
```

浏览器直接打开会显示 Base64，这是正常的；用上面的请求头或用 `curl` 才是明文。

---

## 数据长什么样

```json
{
  "ok": true,
  "plan": "plus",
  "h5": { "used": 35, "left": 65.0, "reset": 1793692217, "win": 18000 },
  "d7": { "used": 100, "left": 0.0, "reset": 1793774194, "win": 604800 },
  "ts": 1793679368
}
```

| 字段 | 含义 |
|---|---|
| `h5` | 5 小时窗口。`left` 是剩余百分比，`reset` 是重置时间（Unix 秒） |
| `d7` | 7 天窗口，字段同上 |
| `win` | 窗口长度（秒）。18000 秒 = 5 小时，604800 秒 = 7 天 |
| `ts` | 这份数据是什么时候抓的 |

**剩余额度 = `left`**，倒计时 = `reset` 减去当前时间。

> 只有当额度真的变化时才会更新文件，所以 `ts` 可能比分针"旧"——
> 那说明额度一直没变，不是脚本挂了。

---

## 日常维护：大约 10 天一次

GitHub 上存的 token 有效期 **10 天**，到期后脚本会失败，GitHub 会给你发一封
"workflow failed" 的邮件——那封邮件就是提醒。

更新办法：重新跑一次部署脚本，或者在仓库
**Settings → Secrets and variables → Actions** 里把 `CODEX_TOKEN` 换成新的。

这个操作**不会影响你电脑上的 Codex**，两边各用各的。

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `fetch_usage.py` | 查询额度并写入 `usage.json` |
| `.github/workflows/usage.yml` | 定时任务配置 |
| `usage.json` | 查询结果（脚本自动生成） |

## 安全

- 仓库是公开的，但代码里**没有任何密码**；`CODEX_TOKEN` 存在 GitHub Secrets 里，加密保存。
- `usage.json` 只包含百分比和时间戳，不含任何凭据。
- 想撤销授权：<https://github.com/settings/applications>
