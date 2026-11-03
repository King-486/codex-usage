#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex 额度中转脚本
------------------
在 GitHub Actions 里运行：向 OpenAI 询问当前 Codex 剩余额度，
把精简后的结果写成同目录的 usage.json，由 workflow 提交回仓库。

ESP32 通过以下地址读取（返回明文）：
    https://api.github.com/repos/<用户名>/<仓库名>/contents/usage.json
    Header: Accept: application/vnd.github.raw

只依赖 Python 标准库，无需 pip install。
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

USAGE_URL = "https://chatgpt.com/backend-api/wham/usage"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage.json")


def need_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"[配置错误] 缺少环境变量 {name}，请检查仓库 Settings -> Secrets", file=sys.stderr)
        sys.exit(2)
    return value


def window(raw):
    """把 OpenAI 返回的窗口对象压成 ESP32 需要的几个数。"""
    if not isinstance(raw, dict):
        return None
    used = raw.get("used_percent")
    reset = raw.get("reset_at")
    secs = raw.get("limit_window_seconds")
    left = None
    if isinstance(used, (int, float)):
        left = round(100 - float(used), 1)
    return {"used": used, "left": left, "reset": reset, "win": secs}


def fetch_usage(token: str, account: str) -> dict:
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "ChatGPT-Account-Id": account,
            "User-Agent": "codex-cli",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 401:
            print(
                "[失败] 401 未授权 —— token 过期或无效。\n"
                "       重新运行 get-credentials.ps1，更新 CODEX_TOKEN。",
                file=sys.stderr,
            )
        elif exc.code == 403:
            print(
                "[失败] 403 被拒绝 —— 出口 IP 被 Cloudflare 拦了，\n"
                "       说明 GitHub 的服务器过不去，需要改用海外 VPS。",
                file=sys.stderr,
            )
        else:
            print(f"[失败] HTTP {exc.code}: {detail}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[失败] 网络错误: {exc}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    token = need_env("CODEX_TOKEN")
    account = need_env("CODEX_ACCOUNT_ID")

    data = fetch_usage(token, account)
    rl = data.get("rate_limit") or {}

    document = {
        "ok": True,
        "plan": data.get("plan_type"),
        "h5": window(rl.get("primary_window")),    # 5 小时窗口
        "d7": window(rl.get("secondary_window")),  # 7 天窗口
        "ts": int(time.time()),
    }

    with open(OUT_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(document, fh, ensure_ascii=False, indent=1)
        fh.write("\n")

    print(f"[成功] 已写入 {OUT_PATH}")
    print(json.dumps(document, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
