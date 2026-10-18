"""Shared process, configuration, and JSON response helpers."""
from __future__ import annotations

import json
import datetime
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
        fail("COMMAND_NOT_FOUND", f"Command not found: {args[0]}")
    except subprocess.TimeoutExpired as exc:
        fail("COMMAND_TIMEOUT", f"Command timed out: {args[0]}")
    if result.returncode:
        detail = (result.stderr or result.stdout or "").strip()
        details_path = None
        if detail:
            details_path = save_log(None, f"command-error-{uuid.uuid4().hex}.log", detail)
        fail(error_code, f"Command failed: {args[0]}", details_path)
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
        fail("INVALID_CONFIG", f"Could not read configuration file: {path}: {exc}")
    if not isinstance(raw, dict):
        fail("INVALID_CONFIG", "The top level of config.json must be an object")
    _validate_config(raw)
    return raw


def _validate_config(config: Mapping[str, Any]) -> None:
    if "baseBranch" in config and not isinstance(config["baseBranch"], str):
        fail("INVALID_CONFIG", "baseBranch must be a string")
    jira = config.get("jira", {})
    if not isinstance(jira, dict):
        fail("INVALID_CONFIG", "jira must be an object")
    if "reviewStatus" in jira and not isinstance(jira["reviewStatus"], str):
        fail("INVALID_CONFIG", "jira.reviewStatus must be a string")
    if "acceptanceCriteriaField" in jira and jira["acceptanceCriteriaField"] is not None and not isinstance(jira["acceptanceCriteriaField"], str):
        fail("INVALID_CONFIG", "jira.acceptanceCriteriaField must be a string or null")
    if "maxComments" in jira and (type(jira["maxComments"]) is not int or jira["maxComments"] < 0):
        fail("INVALID_CONFIG", "jira.maxComments must be a non-negative integer")
    validation = config.get("validation", {})
    if not isinstance(validation, dict) or not isinstance(validation.get("commands", []), list):
        fail("INVALID_CONFIG", "validation.commands must be an array")
    for command in validation.get("commands", []):
        if (not isinstance(command, dict) or not isinstance(command.get("name"), str)
                or not isinstance(command.get("argv"), list) or not command["argv"]
                or not all(isinstance(v, str) for v in command["argv"])):
            fail("INVALID_CONFIG", "Each validation.commands item must have a name and a non-empty argv string array")
        if "timeoutSeconds" in command and (type(command["timeoutSeconds"]) is not int or command["timeoutSeconds"] <= 0):
            fail("INVALID_CONFIG", "timeoutSeconds must be a positive integer")
    review = config.get("review", {})
    if not isinstance(review, dict):
        fail("INVALID_CONFIG", "review must be an object")
    if "policy" in review and review["policy"] is not None and not isinstance(review["policy"], str):
        fail("INVALID_CONFIG", "review.policy must be a string or null")
    rules = review.get("rules", {})
    if not isinstance(rules, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in rules.items()):
        fail("INVALID_CONFIG", "review.rules must map strings to strings")
    filters = config.get("filters", {})
    if not isinstance(filters, dict):
        fail("INVALID_CONFIG", "filters must be an object")
    for key in ("excludePaths", "secretPatterns"):
        values = filters.get(key, [])
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            fail("INVALID_CONFIG", f"filters.{key} must be an array of strings")
    for pattern in filters.get("secretPatterns", []):
        try:
            re.compile(pattern)
        except re.error as exc:
            fail("INVALID_CONFIG", f"Invalid regular expression in filters.secretPatterns: {exc}")


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


def save_checkpoint(issue_key: str, phase: str, summary: str, next_step: str = "") -> dict[str, Any]:
    safe_key = "".join(c for c in issue_key if c.isalnum() or c in "-_")
    if not safe_key or safe_key != issue_key:
        fail("INVALID_ISSUE_KEY", "Invalid Jira issue key for checkpoint")
    path = work_dir(safe_key) / "checkpoint.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"issueKey": safe_key, "phases": {}}
    except (OSError, json.JSONDecodeError):
        state = {"issueKey": safe_key, "phases": {}}
    state["phases"][phase] = {"summary": summary, "nextStep": next_step}
    state["updatedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return {"issueKey": safe_key, "phase": phase, "checkpointPath": str(path)}


def load_checkpoint(issue_key: str) -> dict[str, Any] | None:
    safe_key = "".join(c for c in issue_key if c.isalnum() or c in "-_")
    if not safe_key or safe_key != issue_key:
        fail("INVALID_ISSUE_KEY", "Invalid Jira issue key for checkpoint")
    path = work_dir(safe_key) / "checkpoint.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fail("CHECKPOINT_INVALID", "Could not read the saved workflow checkpoint")


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
        fail("INVALID_JSON", f"Could not parse JSON from {context}: {exc}")
