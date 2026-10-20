"""Git operations with explicit file selection and dirty-tree protection."""
from __future__ import annotations

import re
import difflib
import fnmatch
from pathlib import Path
from typing import Sequence

from common import CommandRunner, SubprocessRunner, fail, run_checked


class GitClient:
    def __init__(self, runner: CommandRunner | None = None, cwd: Path | None = None):
        self.runner = runner or SubprocessRunner()
        self.cwd = cwd or Path.cwd()

    def inspect(self) -> dict[str, object]:
        root = run_checked(self.runner, ["git", "rev-parse", "--show-toplevel"], cwd=self.cwd).stdout.strip()
        branch = run_checked(self.runner, ["git", "branch", "--show-current"], cwd=self.cwd).stdout.strip()
        status = run_checked(self.runner, ["git", "status", "--porcelain=v1", "-z"], cwd=self.cwd).stdout
        changed: list[str] = []
        entries = status.split("\0")
        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if not entry:
                continue
            if len(entry) < 4 or entry[2] != " ":
                fail("GIT_STATUS_INVALID", "Could not parse git status --porcelain output")
            changed.append(entry[3:])
            # Porcelain v1 -z emits the destination first and the source path
            # as a separate NUL-delimited record for renames/copies.
            if "R" in entry[:2] or "C" in entry[:2]:
                if index >= len(entries) or not entries[index]:
                    fail("GIT_STATUS_INVALID", "Could not read the source path for a Git rename")
                changed.append(entries[index])
                index += 1
        return {"root": root, "branch": branch, "isDirty": bool(changed), "changedFiles": changed}

    def create_branch(self, name: str, base: str) -> dict[str, str]:
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", name) or name.startswith("-") or ".." in name:
            fail("INVALID_BRANCH", "Branch name contains unsupported characters")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", base) or base.startswith("-") or ".." in base:
            fail("INVALID_BASE_BRANCH", "Base branch name contains unsupported characters")
        current = self.inspect()
        if current["isDirty"]:
            fail("DIRTY_WORKTREE", "Uncommitted changes are present; branch creation stopped to protect existing work")
        exists = self.runner.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{name}"], cwd=self.cwd)
        if exists.returncode == 0:
            fail("BRANCH_ALREADY_EXISTS", f"Local work branch already exists. Do not reuse it; choose a unique name: {name}")
        remote_refs = run_checked(self.runner, ["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/"], cwd=self.cwd).stdout
        if any(ref.strip().endswith(f"/{name}") for ref in remote_refs.splitlines()):
            fail("BRANCH_ALREADY_EXISTS", f"Remote work branch already exists. Do not reuse it; choose a unique name: {name}")
        remote_base = f"origin/{base}"
        run_checked(self.runner, ["git", "fetch", "origin", f"{base}:refs/remotes/{remote_base}"], cwd=self.cwd, timeout=120,
                    error_code="BASE_FETCH_FAILED")
        check = self.runner.run(["git", "rev-parse", "--verify", "--quiet", remote_base], cwd=self.cwd)
        if check.returncode:
            fail("REMOTE_BASE_NOT_FOUND", f"Remote base branch was not found: {remote_base}")
        run_checked(self.runner, ["git", "switch", "-c", name, remote_base], cwd=self.cwd)
        return {"branch": name, "base": remote_base}

    def diff(self, base: str) -> dict[str, object]:
        root = Path(str(self.inspect()["root"]))
        # Comparing BASE to the worktree includes both staged and unstaged tracked edits.
        result = run_checked(self.runner, ["git", "diff", "--no-ext-diff", "--find-renames", base], cwd=root)
        names_result = run_checked(self.runner, ["git", "diff", "--name-only", "-z", base], cwd=root).stdout
        tracked = [entry for entry in names_result.split("\0") if entry]
        stat = run_checked(self.runner, ["git", "diff", "--stat", base], cwd=root).stdout.strip()
        untracked_result = run_checked(self.runner, ["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root).stdout
        untracked = [entry for entry in untracked_result.split("\0") if entry]
        untracked_diffs: list[str] = []
        for name in untracked:
            path = root / name
            # Do not follow symlinks when collecting review material.
            if path.is_symlink() or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            lines = content.splitlines(keepends=True)
            untracked_diffs.extend(difflib.unified_diff([], lines, fromfile="/dev/null", tofile=f"b/{name}"))
        combined_diff = result.stdout
        if untracked_diffs:
            combined_diff += ("\n" if combined_diff else "") + "".join(untracked_diffs)
        names = sorted(set(tracked + untracked))
        return {"base": base, "changedFiles": names, "trackedFiles": tracked,
                "untrackedFiles": untracked, "stat": stat, "diff": combined_diff}

    def commit(self, message: str, files: Sequence[str]) -> str:
        if not message.strip() or not files:
            fail("INVALID_COMMIT", "Provide a commit message and at least one file")
        root = Path(str(self.inspect()["root"]))
        safe_files: list[str] = []
        for item in files:
            path = Path(item)
            if path.is_absolute() or ".." in path.parts:
                fail("INVALID_FILE_PATH", f"Paths outside the repository are not allowed: {item}")
            safe_files.append(path.as_posix())
        staged = run_checked(self.runner, ["git", "diff", "--cached", "--name-only", "-z"], cwd=root).stdout
        staged_files = {entry for entry in staged.split("\0") if entry}
        if not staged_files or staged_files != set(safe_files):
            fail("STAGING_MISMATCH", "Staged files do not match the approved file list; commit stopped")
        run_checked(self.runner, ["git", "diff", "--cached", "--check"], cwd=root)
        run_checked(self.runner, ["git", "commit", "-m", message], cwd=root)
        return run_checked(self.runner, ["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()

    def stage(self, files: Sequence[str], filters: dict[str, object] | None = None) -> dict[str, object]:
        if not files:
            fail("INVALID_FILE_LIST", "Specify at least one file to stage")
        root = Path(str(self.inspect()["root"]))
        safe_files: list[str] = []
        for item in files:
            path = Path(item)
            if path.is_absolute() or ".." in path.parts:
                fail("INVALID_FILE_PATH", f"Paths outside the repository are not allowed: {item}")
            safe_files.append(path.as_posix())
        filters = filters or {}
        excluded = list(filters.get("excludePaths", []))
        secret_patterns = [
            r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
            r"(?i)(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[^\s'\"]{8,}",
            r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b",
        ] + list(filters.get("secretPatterns", []))
        sensitive_names = (".env", ".env.*", "*.pem", "*.key", "id_rsa", "id_ed25519", "*.p12", "*.pfx")
        blocked = [name for name in safe_files if
                   any(fnmatch.fnmatchcase(name, pattern) for pattern in excluded) or
                   any(fnmatch.fnmatchcase(Path(name).name, pattern) for pattern in sensitive_names)]
        if blocked:
            fail("FILE_FILTER_MATCH", "Staging stopped because files match an exclusion or sensitive-file rule",
                 data={"blockedFiles": blocked, "reason": "path_filter"})
        matches = []
        for name in safe_files:
            path = root / name
            if path.is_symlink():
                matches.append({"file": name, "pattern": "symlink_requires_manual_review"})
                continue
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pattern in secret_patterns:
                if re.search(pattern, content):
                    matches.append({"file": name, "pattern": pattern})
                    break
        if matches:
            fail("SECRET_PATTERN_MATCH", "Staging stopped because content matched a possible secret pattern; review and remove any secrets",
                 data={"matches": matches})
        existing = run_checked(self.runner, ["git", "diff", "--cached", "--name-only", "-z"], cwd=root).stdout
        if not {entry for entry in existing.split("\0") if entry}.issubset(set(safe_files)):
            fail("PRESTAGED_FILES", "Changes outside the selected file list are already staged; staging stopped")
        run_checked(self.runner, ["git", "add", "--", *safe_files], cwd=root)
        staged = run_checked(self.runner, ["git", "diff", "--cached", "--name-only", "-z"], cwd=root).stdout
        staged_files = sorted(entry for entry in staged.split("\0") if entry)
        if set(staged_files) != set(safe_files):
            fail("STAGING_MISMATCH", "Staged files do not match the selected file list")
        diff = run_checked(self.runner, ["git", "diff", "--cached", "--no-ext-diff", "--find-renames"], cwd=root)
        run_checked(self.runner, ["git", "diff", "--cached", "--check"], cwd=root)
        return {"stagedFiles": staged_files, "diff": diff.stdout}

    def push(self) -> None:
        branch = str(self.inspect()["branch"])
        if not branch:
            fail("DETACHED_HEAD", "Cannot push from a detached HEAD")
        run_checked(self.runner, ["git", "push", "--set-upstream", "origin", branch], cwd=self.cwd, timeout=120)

