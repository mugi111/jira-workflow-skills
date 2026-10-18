import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "skills" / "jira-fix" / "scripts"))
from common import WorkflowError
from github import GitHubClient


class Result:
    returncode = 0
    stderr = ""
    def __init__(self, stdout): self.stdout = stdout


class Runner:
    def __init__(self, items=None): self.items, self.calls = items or [], []
    def run(self, args, **kwargs):
        self.calls.append(args)
        if args[1:3] == ["pr", "list"]: return Result(json.dumps(self.items))
        return Result("https://github.com/acme/repo/pull/4\n")


class GitHubTests(unittest.TestCase):
    def test_discovers_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".github" / "PULL_REQUEST_TEMPLATE.md"
            path.parent.mkdir(parents=True); path.write_text("## Summary", encoding="utf-8")
            result = GitHubClient(Runner(), Path(tmp)).template()
            self.assertTrue(result["found"])
            self.assertEqual(result["templates"][0]["headings"], ["## Summary"])
            self.assertEqual(result["templates"][0]["characterCount"], len("## Summary"))
            selected = GitHubClient(Runner(), Path(tmp)).template(".github/PULL_REQUEST_TEMPLATE.md")
            self.assertEqual(selected["selected"]["content"], "## Summary")

    def test_existing_draft_pr_is_not_reused_or_marked_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            title, body = root / "title.txt", root / "body.md"
            title.write_text("fix: 修正", encoding="utf-8"); body.write_text("内容", encoding="utf-8")
            runner = Runner([{"number": 7, "url": "https://github.com/acme/repo/pull/7", "isDraft": True}])
            with self.assertRaises(WorkflowError) as error:
                GitHubClient(runner, root).create_pr("main", title, body)
            self.assertEqual(error.exception.code, "PR_ALREADY_EXISTS")
            self.assertNotIn(["gh", "pr", "ready", "7"], runner.calls)
            self.assertFalse(any(call[:3] == ["gh", "pr", "create"] for call in runner.calls))

    def test_new_correction_creates_a_new_pr_when_branch_has_no_open_pr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            title, body = root / "title.txt", root / "body.md"
            title.write_text("fix: 修正", encoding="utf-8"); body.write_text("内容", encoding="utf-8")
            runner = Runner()
            result = GitHubClient(runner, root).create_pr("main", title, body)
            self.assertEqual(result, {"url": "https://github.com/acme/repo/pull/4", "number": "4"})
            self.assertTrue(any(call[:3] == ["gh", "pr", "create"] for call in runner.calls))


if __name__ == "__main__": unittest.main()
