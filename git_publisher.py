"""按指定文件提交快照，正常合并并发更新，不强制覆盖远端。"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from fetch_usage import QuotaRequestError, safe_detail


def git_command(repository: Path, arguments: list[str]) -> subprocess.CompletedProcess[str]:
    result: subprocess.CompletedProcess[str] = subprocess.run(
        ["git", "-C", str(repository), *arguments], capture_output=True, text=True, encoding="utf-8", timeout=45)
    if result.returncode != 0:
        raise QuotaRequestError("storage", result.returncode, safe_detail(result.stderr))
    return result


def publish_files(repository: Path, paths: list[str], message: str) -> None:
    git_command(repository, ["config", "user.name", "nox-quota[bot]"])
    git_command(repository, ["config", "user.email", "nox-quota@users.noreply.github.com"])
    git_command(repository, ["add", "--", *paths])
    staged: subprocess.CompletedProcess[str] = subprocess.run(
        ["git", "-C", str(repository), "diff", "--cached", "--quiet"], capture_output=True, text=True, timeout=10)
    if staged.returncode == 0:
        return
    if staged.returncode != 1:
        raise QuotaRequestError("storage", staged.returncode, safe_detail(staged.stderr))
    git_command(repository, ["commit", "-m", message])
    for attempt in range(1, 4):
        try:
            git_command(repository, ["fetch", "origin", "main"])
            git_command(repository, ["merge", "--no-edit", "origin/main"])
            git_command(repository, ["push", "origin", "HEAD:main"])
            return
        except QuotaRequestError as error:
            print(json.dumps({"event": "publish_retry", "attempt": attempt, "kind": error.kind, "detail": safe_detail(str(error))}), flush=True)
            if attempt == 3:
                raise
            time.sleep(attempt * 2)
    raise QuotaRequestError("internal", 0, "Invalid publishing retry state")


