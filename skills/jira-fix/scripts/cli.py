#!/usr/bin/env python3
"""Single JSON-producing entry point for the jira-fix Skill."""
from __future__ import annotations

import argparse
from pathlib import Path

from common import (SubprocessRunner, WorkflowError, command_available, emit, fail,
                    find_repo_root, load_config, run_checked)
from git import GitClient
from github import GitHubClient
from jira import JiraClient, validate_key
from review import collect_review_context
from validation import run_validation


class HelpRequested(Exception):
    def __init__(self, help_text: str):
        self.help_text = help_text


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        fail("INVALID_ARGUMENTS", message)

    def print_help(self, file=None) -> None:
        raise HelpRequested(self.format_help())


def parser() -> argparse.ArgumentParser:
    root = JsonArgumentParser(prog="jira-fix")
    commands = root.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)
    commands.add_parser("check")
    issue = commands.add_parser("issue").add_subparsers(dest="action", required=True)
    for action in ("get", "status"):
        item = issue.add_parser(action); item.add_argument("key")
    complete = issue.add_parser("complete"); complete.add_argument("key"); complete.add_argument("--pr-url", required=True)
    git_cmd = commands.add_parser("git").add_subparsers(dest="action", required=True)
    git_cmd.add_parser("inspect")
    branch = git_cmd.add_parser("branch").add_subparsers(dest="branch_action", required=True)
    create = branch.add_parser("create"); create.add_argument("name"); create.add_argument("--base", required=True)
    diff = git_cmd.add_parser("diff"); diff.add_argument("--base", required=True)
    stage = git_cmd.add_parser("stage"); stage.add_argument("--files-file", required=True)
    commit = git_cmd.add_parser("commit"); commit.add_argument("--message-file", required=True); commit.add_argument("--files-file", required=True)
    git_cmd.add_parser("push")
    commands.add_parser("validate")
    review = commands.add_parser("review").add_subparsers(dest="action", required=True)
    context = review.add_parser("context"); context.add_argument("--base", required=True)
    pr = commands.add_parser("pr").add_subparsers(dest="action", required=True)
    template = pr.add_parser("template"); template.add_argument("--path")
    create_pr = pr.add_parser("create"); create_pr.add_argument("--base", required=True); create_pr.add_argument("--title-file", required=True); create_pr.add_argument("--body-file", required=True)
    pr.add_parser("status")
    return root


def execute(args: argparse.Namespace) -> object:
    runner = SubprocessRunner()
    root = find_repo_root(runner=runner)
    config = load_config(root)
    if args.command == "check":
        required = {"python3": command_available("python3"), "git": command_available("git"),
                    "gh": command_available("gh"), "jira": command_available("jira")}
        auth = {}
        if required["gh"]:
            result = runner.run(["gh", "auth", "status"], cwd=root)
            auth["github"] = result.returncode == 0
        else: auth["github"] = False
        if required["jira"]:
            result = runner.run(["jira", "me"], cwd=root)
            auth["jira"] = result.returncode == 0
        else: auth["jira"] = False
        git_state = GitClient(runner, root).inspect()
        data = {"commands": required, "authentication": auth, "repository": git_state}
        if not all(required.values()) or not all(auth.values()):
            fail("PREPARATION_FAILED", "必要なCLIまたは認証状態に問題があります")
        return data
    if args.command == "issue":
        jira = JiraClient(runner, root)
        if args.action == "get":
            issue = jira.get_issue(args.key, config.get("jira", {}).get("acceptanceCriteriaField"))
            issue["comments"] = jira.get_comments(args.key, config.get("jira", {}).get("maxComments", 5))
            return issue
        if args.action == "status": return {"key": validate_key(args.key), "status": jira.get_status(args.key)}
        return _complete_issue(args.key, args.pr_url, jira, config, GitHubClient(runner, root))
    if args.command == "git":
        git = GitClient(runner, root)
        if args.action == "inspect": return git.inspect()
        if args.action == "branch": return git.create_branch(args.name, args.base)
        if args.action == "diff": return git.diff(args.base)
        if args.action == "push": git.push(); return {"pushed": True}
        files = Path(args.files_file).read_text(encoding="utf-8").splitlines()
        if args.action == "stage": return git.stage(files)
        message = Path(args.message_file).read_text(encoding="utf-8")
        return {"commit": git.commit(message, files)}
    if args.command == "validate": return run_validation(config, root)
    if args.command == "review": return collect_review_context(root, args.base, config, runner)
    if args.command == "pr":
        gh = GitHubClient(runner, root)
        if args.action == "template": return gh.template(args.path)
        if args.action == "status": return gh.status()
        return gh.create_pr(args.base, Path(args.title_file), Path(args.body_file))
    fail("UNKNOWN_COMMAND", "不明なコマンドです")


def _complete_issue(key: str, pr_url: str, jira: JiraClient, config: dict, github: GitHubClient) -> object:
    validate_key(key)
    status = github.status_for_url(pr_url)
    if status.get("url") != pr_url or str(status.get("state", "")).casefold() != "open" or status.get("isDraft"):
        fail("PR_NOT_VERIFIED", "指定されたPRがレビュー可能な状態であることを確認できません")
    jira.add_comment(key, f"修正PRを作成しました。\n{pr_url}")
    target = config.get("jira", {}).get("reviewStatus", "In Review")
    current = jira.get_status(key)
    if current.casefold() != target.casefold(): jira.transition(key, target)
    verified = jira.get_status(key)
    if verified.casefold() != target.casefold():
        fail("JIRA_TRANSITION_UNVERIFIED", f"Jiraステータスが{target}へ遷移したことを確認できません（現在: {verified}）")
    return {"key": key, "prUrl": pr_url, "status": verified, "completed": True}


def main(argv: list[str] | None = None) -> int:
    try:
        result = execute(parser().parse_args(argv))
        emit(True, result)
        return 0
    except HelpRequested as help_request:
        emit(True, {"help": help_request.help_text})
        return 0
    except WorkflowError as exc:
        emit(False, exc.data, {"code": exc.code, "message": exc.message}, exc.details_path)
        return 1
    except Exception as exc:
        emit(False, None, {"code": "UNEXPECTED_ERROR", "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
