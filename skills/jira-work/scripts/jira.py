"""Jira CLI adapter and issue normalization."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from common import CommandRunner, SubprocessRunner, fail, parse_json_output, run_checked

ISSUE_KEY = re.compile(r"^[A-Z][A-Z0-9_]*-\d+$")


def validate_key(key: str) -> str:
    if not ISSUE_KEY.fullmatch(key):
        fail("INVALID_ISSUE_KEY", f"Invalid Jira issue key: {key}")
    return key


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text for item in value if (text := _text(item)))
    if isinstance(value, dict):
        node_type = value.get("type")
        if node_type == "text":
            return str(value.get("text", ""))
        if node_type == "hardBreak":
            return "\n"
        if isinstance(node_type, str):
            content = value.get("content", [])
            if node_type in {"bulletList", "orderedList"} and isinstance(content, list):
                rows = []
                for index, item in enumerate(content, 1):
                    text = _text(item).strip()
                    if text:
                        marker = f"{index}." if node_type == "orderedList" else "-"
                        rows.append(f"{marker} {text}")
                return "\n".join(rows)
            if node_type == "listItem":
                return _text(content)
            if node_type in {"paragraph", "heading", "codeBlock"} and isinstance(content, list):
                return "".join(_text(item) for item in content)
            if node_type in {"mention", "emoji"}:
                attrs = value.get("attrs", {})
                if isinstance(attrs, dict):
                    return str(attrs.get("text") or attrs.get("shortName") or "")
                return ""
            # ADF node metadata (type, attrs, marks, version, etc.) is not body text.
            return _text(content)
        # Jira user/status objects are not ADF nodes. Extract only known display
        # fields instead of recursively serializing arbitrary metadata.
        for key in ("displayName", "name", "value"):
            if value.get(key) is not None:
                return _text(value[key])
        return ""
    return str(value)


def normalize_issue(raw: dict[str, Any], key: str, acceptance_field: str | None = None) -> dict[str, Any]:
    fields = raw.get("fields", raw)
    if not isinstance(fields, dict):
        fail("INVALID_JIRA_RESPONSE", "Jira issue response has invalid fields")
    if acceptance_field and acceptance_field not in fields:
        fail("ACCEPTANCE_CRITERIA_MISSING", f"Configured acceptance criteria field is missing: {acceptance_field}")
    ac = fields.get(acceptance_field) if acceptance_field else None
    if ac is None:
        ac = fields.get("acceptanceCriteria") or fields.get("acceptance_criteria")
    issue_type = fields.get("issuetype") or fields.get("issueType") or {}
    status = fields.get("status") or {}
    links = fields.get("issuelinks") or fields.get("relatedIssues") or []
    related = []
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict):
                target = link.get("outwardIssue") or link.get("inwardIssue") or link
                related.append(target.get("key", ""))
    return {
        "key": raw.get("key", key),
        "summary": _text(fields.get("summary")),
        "description": _text(fields.get("description")),
        "acceptanceCriteria": _text(ac),
        "issueType": _text(issue_type.get("name") if isinstance(issue_type, dict) else issue_type),
        "status": _text(status.get("name") if isinstance(status, dict) else status),
        "relatedIssues": [item for item in related if item],
    }


class JiraClient:
    def __init__(self, runner: CommandRunner | None = None, cwd: Path | None = None):
        self.runner = runner or SubprocessRunner()
        self.cwd = cwd or Path.cwd()

    def get_issue(self, key: str, acceptance_field: str | None = None) -> dict[str, Any]:
        validate_key(key)
        raw_result = run_checked(self.runner, ["jira", "issue", "view", key, "--raw"], cwd=self.cwd)
        raw = parse_json_output(raw_result.stdout, "jira issue view")
        issue = normalize_issue(raw, key, acceptance_field)
        if not issue["summary"]:
            fail("INVALID_JIRA_RESPONSE", "Jira response does not contain a summary")
        return issue

    def get_comments(self, key: str, limit: int = 5) -> list[dict[str, str]]:
        validate_key(key)
        if limit <= 0:
            return []
        result = run_checked(self.runner, ["jira", "issue", "view", key, "--comments", str(limit), "--raw"], cwd=self.cwd)
        parsed = parse_json_output(result.stdout, "jira comments")
        fields = parsed.get("fields", parsed) if isinstance(parsed, dict) else None
        comment_field = fields.get("comment") if isinstance(fields, dict) else None
        if not isinstance(comment_field, dict) or not isinstance(comment_field.get("comments"), list):
            fail("JIRA_COMMENTS_UNAVAILABLE", "Could not read Jira comments; stopped to prevent a duplicate comment")
        items = comment_field["comments"]
        if any(not isinstance(item, dict) for item in items):
            fail("JIRA_COMMENTS_INVALID", "Jira comments have an invalid format; stopped to prevent a duplicate comment")
        return [{"author": _text(x.get("author")), "body": _text(x.get("body")), "created": _text(x.get("created"))}
                for x in items[:limit]]

    def get_status(self, key: str) -> str:
        return self.get_issue(key)["status"]

    def transition(self, key: str, status: str) -> None:
        validate_key(key)
        current = self.get_status(key)
        if current.casefold() == status.casefold():
            return
        run_checked(self.runner, ["jira", "issue", "move", key, status], cwd=self.cwd)

