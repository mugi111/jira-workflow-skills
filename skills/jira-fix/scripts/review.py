"""Collect changed files and applicable review policy paths."""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from common import CommandRunner, SubprocessRunner, fail, run_checked


def collect_review_context(root: Path, base: str, config: dict[str, Any], runner: CommandRunner | None = None) -> dict[str, Any]:
    runner = runner or SubprocessRunner()
    root = root.resolve()
    tracked = run_checked(runner, ["git", "diff", "--name-only", "-z", base], cwd=root).stdout
    untracked = run_checked(runner, ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root).stdout
    files = sorted({entry for entry in (tracked + "\0" + untracked).split("\0") if entry})
    review_root = root / ".claude" / "jira-fix"
    candidates: list[str] = []
    policy = config.get("review", {}).get("policy", "review/policy.md")
    if policy:
        candidates.append(policy)
    rules = config.get("review", {}).get("rules", {})
    if not isinstance(rules, dict):
        fail("INVALID_CONFIG", "review.rulesはglobとパスのオブジェクトで指定してください")
    for pattern, path in rules.items():
        if any(fnmatch.fnmatchcase(file, pattern) for file in files):
            candidates.append(path)
    policies = []
    for relative in dict.fromkeys(candidates):
        path = (review_root / relative).resolve()
        if review_root.resolve() not in path.parents:
            fail("INVALID_CONFIG", f"レビュー基準のパスが設定ディレクトリ外です: {relative}")
        if path.is_file():
            policies.append(path.relative_to(root).as_posix())
    return {"changedFiles": files, "reviewPolicies": policies}

