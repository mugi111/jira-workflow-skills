"""Run configured validation commands without a shell and retain full logs."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from common import CommandRunner, SubprocessRunner, fail, redact_sensitive, save_log


def run_validation(config: dict[str, Any], root: Path, issue_key: str | None = None,
                   runner: CommandRunner | None = None) -> dict[str, Any]:
    commands = config.get("validation", {}).get("commands", [])
    if not commands:
        fail("VALIDATION_NOT_CONFIGURED", "No validation commands are configured. Identify the required project checks and add them to config.json.",
             data={"checks": [], "configured": False})
    runner = runner or SubprocessRunner()
    results = []
    all_logs = []
    for item in commands:
        name, argv = item["name"], item["argv"]
        timeout = int(item.get("timeoutSeconds", 1800))
        exit_code = None
        try:
            result = runner.run(argv, cwd=root, timeout=timeout)
            output = (result.stdout or "") + ("\n" + result.stderr if result.stderr else "")
            passed = result.returncode == 0
            exit_code = result.returncode
            status = "passed" if passed else "failed"
        except subprocess.TimeoutExpired as exc:
            output = "Command timed out"
            passed, status = False, "timed_out"
        except FileNotFoundError as exc:
            output = f"Command not found: {argv[0]}"
            passed, status = False, "not_found"
        all_logs.append(f"### {name} ({status})\n$ [configured validation command]\n{output}\n")
        summary = {"name": name, "status": status, "passed": passed}
        if status == "failed":
            summary["exitCode"] = exit_code
            summary["excerpt"] = redact_sensitive(output[-600:])
        elif status in {"timed_out", "not_found"}:
            summary["excerpt"] = output
        results.append(summary)
    log_path = save_log(issue_key, "validation.log", "\n".join(all_logs))
    data = {"checks": results, "configured": True, "detailsPath": log_path}
    if all(item["passed"] for item in results):
        return data
    fail("VALIDATION_FAILED", "One or more validation commands failed", log_path, data)

