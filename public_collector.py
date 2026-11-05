"""公共运行器连续查额度；仅解密短期访问快照，不能解密或续期完整会话。"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from access_snapshot import access_key, read_access
from fetch_usage import JsonObject, QuotaRequestError, QuotaSnapshot, build_snapshot, fetch_usage, last_success, safe_detail, write_snapshot
from git_publisher import git_command, publish_files


def update_access_state(repository: Path) -> None:
    for attempt in range(1, 4):
        try:
            git_command(repository, ["fetch", "origin", "main"])
            git_command(repository, ["merge", "--ff-only", "origin/main"])
            return
        except QuotaRequestError as error:
            print(json.dumps({"event": "access_state_read_retry", "attempt": attempt, "detail": safe_detail(str(error))}), flush=True)
            if attempt == 3:
                raise
            time.sleep(attempt * 2)
    raise QuotaRequestError("internal", 0, "Invalid read retry state")


def sample_access(state_repository: Path, output_repository: Path) -> None:
    output: Path = output_repository / "usage.json"
    previous: int = 0
    try:
        previous = last_success(output)
        update_access_state(state_repository)
        access: JsonObject = read_access(state_repository / "access.enc", access_key())
        if access["status"] == "reauthorization_required":
            raise QuotaRequestError("unauthorized", 401, "Private maintainer confirmed that reauthorization is required")
        if int(access["expires_at"]) <= int(time.time()):
            raise QuotaRequestError("renewal_pending", 0, "Waiting for private session maintenance")
        payload: JsonObject = fetch_usage(str(access["access_token"]), str(access["account_id"]))
        snapshot: QuotaSnapshot = build_snapshot(payload, int(time.time()))
    except QuotaRequestError as error:
        failed: QuotaSnapshot = {"schema": 2, "ok": False, "plan": "", "h5": None, "d7": None,
                                 "ts": int(time.time()), "last_success_at": previous, "error": error.kind}
        write_snapshot(output, failed)
        publish_files(output_repository, ["usage.json"], "Publish Nox quota query state")
        raise
    write_snapshot(output, snapshot)
    publish_files(output_repository, ["usage.json"], "Publish fresh Nox quota snapshot")
    print(json.dumps({"event": "quota_updated", "checked_at": snapshot["ts"], "five": snapshot["h5"], "week": snapshot["d7"]}), flush=True)


def collect(state_repository: Path, output_repository: Path, duration_seconds: int) -> None:
    if not 120 <= duration_seconds <= 2700:
        raise ValueError("Collector duration must be between 120 and 2700 seconds")
    deadline: float = time.monotonic() + duration_seconds
    failures: int = 0
    while time.monotonic() < deadline:
        started: float = time.monotonic()
        try:
            sample_access(state_repository, output_repository)
            failures = 0
        except QuotaRequestError as error:
            failures += 1
            print(json.dumps({"event": "sample_failed", "attempt": failures, "kind": error.kind, "detail": safe_detail(str(error))}), flush=True)
            if failures >= 3 or error.kind == "unauthorized":
                raise
        remaining: float = min(deadline - time.monotonic(), started + 120 - time.monotonic())
        if remaining > 0:
            time.sleep(remaining)


if __name__ == "__main__":
    collect(Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]))
