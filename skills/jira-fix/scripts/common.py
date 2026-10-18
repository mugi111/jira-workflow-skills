"""Shared process, configuration, and JSON response helpers."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


class CommandRunner(Protocol):
    def run(self, args: Sequence[str], *, cwd: Path | None = None,
            timeout: int = 30, input_text: str | None = None) -> subprocess.CompletedProcess[str]: ...


class SubprocessRunner:
    def run(self, args: Sequence[str], *, cwd: Path | None = None,
            timeout: int = 30, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(list(args), cwd=cwd, input=input_text, capture_output=True,
                              text=True, timeout=timeout, shell=False, check=False)


@dataclass
class WorkflowError(Exception):
    code: str
    message: str
    details_path: str | None = None
    data: Any = None

    def __str__(self) -> str:
        return self.message


def emit(success: bool, data: Any = None, error: dict[str, str] | None = None,
         details_path: str | None = None) -> None:
    print(json.dumps({"success": success, "data": data, "error": error,
                      "details_path": details_path}, ensure_ascii=False))


def fail(code: str, message: str, details_path: str | None = None, data: Any = None) -> None:
    raise WorkflowError(code, message, details_path, data)


def run_checked(runner: CommandRunner, args: Sequence[str], *, cwd: Path | None = None,
                timeout: int = 30, error_code: str = "COMMAND_FAILED") -> subprocess.CompletedProcess[str]:
    try:
        result = runner.run(args, cwd=cwd, timeout=timeout)
    except FileNotFoundError:
        fail("COMMAND_NOT_FOUND", f"コマンドが見つかりません: {args[0]}")
    except subprocess.TimeoutExpired as exc:
        fail("COMMAND_TIMEOUT", f"コマンドがタイムアウトしました: {args[0]}")
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        details_path = None
        if detail:
            details_path = save_log(None, f"command-error-{uuid.uuid4().hex}.log", detail)
        fail(error_code, f"コマンドに失敗しました: {args[0]}", details_path)
    return result


def find_repo_root(start: Path | None = None, runner: CommandRunner | None = None) -> Path:
    runner = runner or SubprocessRunner()
    result = run_checked(runner, ["git", "rev-parse", "--show-toplevel"],
                         cwd=start or Path.cwd(), error_code="NOT_GIT_REPOSITORY")
    return Path(result.stdout.strip()).resolve()


def load_config(root: Path) -> dict[str, Any]:
    path = root / ".claude" / "jira-fix" / "config.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail("INVALID_CONFIG", f"設定ファイルを読み込めません: {path}: {exc}")
    if not isinstance(raw, dict):
        fail("INVALID_CONFIG", "config.jsonのトップレベルはオブジェクトである必要があります")
    _validate_config(raw)
    return raw


def _validate_config(config: Mapping[str, Any]) -> None:
    if "baseBranch" in config and not isinstance(config["baseBranch"], str):
        fail("INVALID_CONFIG", "baseBranchは文字列で指定してください")
    jira = config.get("jira", {})
    if not isinstance(jira, dict):
        fail("INVALID_CONFIG", "jiraはオブジェクトで指定してください")
    if "reviewStatus" in jira and not isinstance(jira["reviewStatus"], str):
        fail("INVALID_CONFIG", "jira.reviewStatusは文字列で指定してください")
    if "acceptanceCriteriaField" in jira and jira["acceptanceCriteriaField"] is not None and not isinstance(jira["acceptanceCriteriaField"], str):
        fail("INVALID_CONFIG", "jira.acceptanceCriteriaFieldは文字列またはnullで指定してください")
    if "maxComments" in jira and (type(jira["maxComments"]) is not int or jira["maxComments"] < 0):
        fail("INVALID_CONFIG", "jira.maxCommentsは0以上の整数で指定してください")
    validation = config.get("validation", {})
    if not isinstance(validation, dict) or not isinstance(validation.get("commands", []), list):
        fail("INVALID_CONFIG", "validation.commandsは配列で指定してください")
    for command in validation.get("commands", []):
        if (not isinstance(command, dict) or not isinstance(command.get("name"), str)
                or not isinstance(command.get("argv"), list) or not command["argv"]
                or not all(isinstance(v, str) for v in command["argv"])):
            fail("INVALID_CONFIG", "validation.commandsの各項目にnameとargv文字列配列が必要です")
        if "timeoutSeconds" in command and (type(command["timeoutSeconds"]) is not int or command["timeoutSeconds"] <= 0):
            fail("INVALID_CONFIG", "timeoutSecondsは正の整数で指定してください")
    review = config.get("review", {})
    if not isinstance(review, dict):
        fail("INVALID_CONFIG", "reviewはオブジェクトで指定してください")
    if "policy" in review and review["policy"] is not None and not isinstance(review["policy"], str):
        fail("INVALID_CONFIG", "review.policyは文字列またはnullで指定してください")
    rules = review.get("rules", {})
    if not isinstance(rules, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in rules.items()):
        fail("INVALID_CONFIG", "review.rulesは文字列から文字列へのマップで指定してください")


def work_dir(issue_key: str | None = None) -> Path:
    safe = "".join(c for c in (issue_key or "general") if c.isalnum() or c in "-_")
    path = Path(tempfile.gettempdir()) / "jira-fix" / (safe or "general")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


def save_log(issue_key: str | None, name: str, content: str) -> str:
    path = work_dir(issue_key) / name
    path.write_text(redact_sensitive(content), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return str(path)


def redact_sensitive(text: str) -> str:
    patterns = (
        (r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+", r"\1[REDACTED]"),
        (r"(?i)(\b(?:token|api[_-]?key|password|passwd|secret)\b\s*[:=]\s*)['\"]?[^\s,'\"]+", r"\1[REDACTED]"),
        (r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b", "[REDACTED]"),
    )
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


def command_available(name: str) -> bool:
    return shutil.which(name) is not None


def parse_json_output(text: str, context: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        fail("INVALID_JSON", f"{context}のJSONを解析できません: {exc}")
