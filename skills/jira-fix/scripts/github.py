"""GitHub CLI integration for repository and pull request workflows."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from common import CommandRunner, SubprocessRunner, fail, run_checked

TEMPLATE_CANDIDATES = (
    ".github/PULL_REQUEST_TEMPLATE.md", ".github/PULL_REQUEST_TEMPLATE",
    "PULL_REQUEST_TEMPLATE.md", "docs/PULL_REQUEST_TEMPLATE.md",
)


class GitHubClient:
    def __init__(self, runner: CommandRunner | None = None, cwd: Path | None = None):
        self.runner = runner or SubprocessRunner()
        self.cwd = cwd or Path.cwd()

    def repo(self) -> dict[str, str]:
        result = run_checked(self.runner, ["gh", "repo", "view", "--json", "nameWithOwner,url,defaultBranchRef"], cwd=self.cwd)
        raw = json.loads(result.stdout)
        return {"nameWithOwner": raw.get("nameWithOwner", ""), "url": raw.get("url", ""),
                "defaultBranch": (raw.get("defaultBranchRef") or {}).get("name", "")}

    def template(self, selected_path: str | None = None) -> dict[str, Any]:
        found = []
        for candidate in TEMPLATE_CANDIDATES:
            path = self.cwd / candidate
            if path.is_file():
                content = path.read_text(encoding="utf-8")
                found.append({"path": candidate, "content": content})
            elif path.is_dir():
                for file in sorted(path.glob("*.md")):
                    found.append({"path": file.relative_to(self.cwd).as_posix(),
                                  "content": file.read_text(encoding="utf-8")})
        if selected_path is not None:
            selected = next((item for item in found if item["path"] == selected_path), None)
            if selected is None:
                fail("PR_TEMPLATE_NOT_FOUND", f"Selected pull request template was not found: {selected_path}")
            return {"found": True, "selected": selected}
        summaries = [{"path": item["path"], "headings": re.findall(r"^#{1,6}\s+.+$", item["content"], re.MULTILINE),
                      "characterCount": len(item["content"])} for item in found]
        return {"templates": summaries, "found": bool(summaries)}

    def existing_pr(self, branch: str | None = None) -> dict[str, Any] | None:
        args = ["gh", "pr", "list", "--state", "open", "--json", "number,url,title,isDraft,headRefName"]
        if branch:
            args.extend(["--head", branch])
        result = run_checked(self.runner, args, cwd=self.cwd)
        items = json.loads(result.stdout)
        return items[0] if items else None

    def create_pr(self, base: str, title_file: Path, body_file: Path) -> dict[str, str]:
        branch_result = run_checked(self.runner, ["git", "branch", "--show-current"], cwd=self.cwd)
        branch = branch_result.stdout.strip()
        existing = self.existing_pr(branch)
        if existing:
            fail("PR_ALREADY_EXISTS", f"An open pull request already exists for this branch. Use a dedicated new branch instead: {existing.get('url', '')}")
        if not title_file.is_file() or not body_file.is_file():
            fail("PR_CONTENT_MISSING", "Pull request title or body file is missing")
        title = title_file.read_text(encoding="utf-8").strip()
        if not title:
            fail("PR_TITLE_EMPTY", "Pull request title is empty")
        result = run_checked(self.runner, ["gh", "pr", "create", "--base", base, "--head", branch,
                                           "--title", title, "--body-file", str(body_file)], cwd=self.cwd, timeout=120)
        url = result.stdout.strip().splitlines()[-1]
        return {"url": url, "number": url.rstrip("/").split("/")[-1]}

    def status(self, branch: str | None = None) -> dict[str, Any]:
        if branch is None:
            branch = run_checked(self.runner, ["git", "branch", "--show-current"], cwd=self.cwd).stdout.strip()
            if not branch:
                fail("DETACHED_HEAD", "Cannot check pull request status because the current branch cannot be determined")
        pr = self.existing_pr(branch)
        if pr is None:
            return {"exists": False, "state": None}
        view = run_checked(self.runner, ["gh", "pr", "view", str(pr["number"]), "--json",
                                         "number,url,title,state,isDraft,headRefName,baseRefName"], cwd=self.cwd)
        data = json.loads(view.stdout)
        data["exists"] = True
        return data

    def status_for_url(self, url: str) -> dict[str, Any]:
        if not url.startswith(("https://github.com/", "https://")):
            fail("INVALID_PR_URL", "Invalid pull request URL")
        result = run_checked(self.runner, ["gh", "pr", "view", url, "--json",
                                           "number,url,title,state,isDraft,headRefName,baseRefName"], cwd=self.cwd)
        data = json.loads(result.stdout)
        data["exists"] = True
        return data

