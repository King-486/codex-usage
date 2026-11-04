"""查询真实额度；每次发布查询时间，失败也发布明确状态。"""

from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import TypeAlias, TypedDict

JsonValue: TypeAlias = "str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]"
JsonObject: TypeAlias = dict[str, JsonValue]


class Window(TypedDict):
    used: float
    left: float
    reset: int
    win: int


class QuotaSnapshot(TypedDict):
    schema: int
    ok: bool
    plan: str
    h5: Window | None
    d7: Window | None
    ts: int
    last_success_at: int
    error: str | None


class QuotaRequestError(RuntimeError):
    """携带可安全记录的外部查询错误。"""

    def __init__(self, kind: str, status: int, detail: str) -> None:
        super().__init__(f"Codex query failed: kind={kind} status={status} detail={detail}")
        self.kind: str = kind
        self.status: int = status


def require_environment(name: str) -> str:
    value: str = os.environ.get(name, "").strip()
    if not value:
        raise QuotaRequestError("configuration", 0, "Missing environment variable " + name)
    return value


def normalize_window(value: JsonValue) -> Window:
    if not isinstance(value, dict):
        raise QuotaRequestError("invalid_response", 200, "Window is missing")
    used: JsonValue = value.get("used_percent")
    reset: JsonValue = value.get("reset_at")
    duration: JsonValue = value.get("limit_window_seconds")
    if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used) or not 0 <= used <= 100:
        raise QuotaRequestError("invalid_response", 200, "used_percent is outside 0..100")
    if type(reset) is not int or type(duration) is not int:
        raise QuotaRequestError("invalid_response", 200, "Window duration/reset timestamp is invalid")
    return {"used": float(used), "left": round(100 - float(used), 1), "reset": reset, "win": duration}


def build_snapshot(payload: JsonObject, checked_at: int) -> QuotaSnapshot:
    limits: JsonValue = payload.get("rate_limit")
    if not isinstance(limits, dict):
        raise QuotaRequestError("invalid_response", 200, "rate_limit is missing")
    windows: tuple[Window, Window] = (normalize_window(limits.get("primary_window")), normalize_window(limits.get("secondary_window")))
    five: Window | None = next((window for window in windows if window["win"] == 18000), None)
    week: Window | None = next((window for window in windows if window["win"] == 604800), None)
    plan: JsonValue = payload.get("plan_type")
    if five is None or week is None or not isinstance(plan, str):
        raise QuotaRequestError("invalid_response", 200, "Expected five-hour and weekly quota windows")
    return {"schema": 2, "ok": True, "plan": plan, "h5": five, "d7": week, "ts": checked_at,
            "last_success_at": checked_at, "error": None}


def safe_detail(value: str) -> str:
    text: str = re.sub(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[redacted]", value)
    return re.sub(r"(?i)Bearer\s+[^\s\"]+", "Bearer [redacted]", text)[:180]


def fetch_usage(token: str, account: str) -> JsonObject:
    request: urllib.request.Request = urllib.request.Request(
        "https://chatgpt.com/backend-api/wham/usage",
        headers={"Authorization": "Bearer " + token, "ChatGPT-Account-Id": account,
                 "User-Agent": "codex-cli", "Accept": "application/json"})
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload: JsonValue = json.load(response)
            if not isinstance(payload, dict):
                raise QuotaRequestError("invalid_response", 200, "Response is not an object")
            return payload
        except urllib.error.HTTPError as error:
            kind: str = "unauthorized" if error.code == 401 else "forbidden" if error.code == 403 else "upstream"
            failure: QuotaRequestError = QuotaRequestError(kind, error.code, safe_detail(error.read().decode("utf-8", "replace")))
            print(json.dumps({"event": "query_failed", "attempt": attempt, "status": error.code, "kind": kind}), flush=True)
            if error.code in (401, 403) or attempt == 3:
                raise failure from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            print(json.dumps({"event": "query_failed", "attempt": attempt, "kind": "network", "type": type(error).__name__}), flush=True)
            if attempt == 3:
                raise QuotaRequestError("network", 0, safe_detail(str(error))) from None
        except (ValueError, UnicodeError) as error:
            raise QuotaRequestError("invalid_response", 200, type(error).__name__) from None
        time.sleep(attempt * 2)
    raise QuotaRequestError("internal", 0, "Invalid retry state")


def last_success(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open(encoding="utf-8") as source:
            payload: JsonValue = json.load(source)
    except (OSError, ValueError, UnicodeError) as error:
        raise QuotaRequestError("invalid_cache", 0, "Cannot read saved snapshot: " + type(error).__name__) from None
    if not isinstance(payload, dict):
        raise QuotaRequestError("invalid_cache", 0, "Saved snapshot is not an object")
    value: JsonValue = payload.get("last_success_at", payload.get("ts", 0))
    if type(value) is not int:
        raise QuotaRequestError("invalid_cache", 0, "Saved success timestamp is invalid")
    return value


def write_snapshot(path: Path, snapshot: QuotaSnapshot) -> None:
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    output: Path = Path(__file__).with_name("usage.json")
    previous_success: int = 0
    try:
        previous_success = last_success(output)
        payload: JsonObject = fetch_usage(require_environment("CODEX_TOKEN"), require_environment("CODEX_ACCOUNT_ID"))
        snapshot: QuotaSnapshot = build_snapshot(payload, int(time.time()))
    except QuotaRequestError as error:
        failed: QuotaSnapshot = {"schema": 2, "ok": False, "plan": "", "h5": None, "d7": None,
                                 "ts": int(time.time()), "last_success_at": previous_success, "error": error.kind}
        write_snapshot(output, failed)
        raise
    write_snapshot(output, snapshot)
    print(json.dumps({"event": "quota_updated", "checked_at": snapshot["ts"], "five": snapshot["h5"], "week": snapshot["d7"]}), flush=True)


if __name__ == "__main__":
    main()
