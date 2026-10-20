import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "skills" / "jira-work" / "scripts"))
from common import WorkflowError
from git import GitClient


class Result:
    def __init__(self, stdout="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, "", returncode


class FakeRunner:
    def __init__(self): self.calls = []
    def run(self, args, **kwargs):
        self.calls.append(list(args))
        if args[:3] == ["git", "rev-parse", "--show-toplevel"]: return Result("/repo\n")
        if args[:3] == ["git", "branch", "--show-current"]: return Result("fix/APP-1\n")
        if args[:2] == ["git", "status"]: return Result("")
        if args[:3] == ["git", "diff", "--cached"]: return Result("")
        return Result("abc123\n")


class GitClientTests(unittest.TestCase):
    def test_inspect_reports_clean_repository(self):
        state = GitClient(FakeRunner(), Path("/repo")).inspect()
        self.assertEqual(state["branch"], "fix/APP-1")
        self.assertFalse(state["isDirty"])

    def test_stage_returns_reviewable_diff_then_commit_uses_exact_files(self):
        class StagingRunner(FakeRunner):
            staged = False
            def run(self, args, **kwargs):
                if args[:3] == ["git", "rev-parse", "--show-toplevel"]: return Result("/repo\n")
                if args[:3] == ["git", "branch", "--show-current"]: return Result("fix/APP-1\n")
                if args[:2] == ["git", "status"]: return Result("")
                if args[:4] == ["git", "diff", "--cached", "--name-only"]:
                    return Result("src/app.py\0" if self.staged else "")
                if args[:2] == ["git", "add"]:
                    self.staged = True
                    return Result("")
                if args[:3] == ["git", "diff", "--cached"] and "--no-ext-diff" in args:
                    return Result("diff --git a/src/app.py b/src/app.py\n+change\n")
                if args[:3] == ["git", "rev-parse", "HEAD"]: return Result("abc123\n")
                return Result("")
        runner = StagingRunner()
        client = GitClient(runner, Path("/repo"))
        staged = client.stage(["src/app.py"])
        self.assertIn("diff --git", staged["diff"])
        self.assertEqual(staged["stagedFiles"], ["src/app.py"])
        self.assertEqual(client.commit("fix: 修正", ["src/app.py"]), "abc123")

    def test_existing_local_branch_is_not_reused(self):
        class ExistingBranchRunner(FakeRunner):
            def run(self, args, **kwargs):
                self.calls.append(list(args))
                if args[:3] == ["git", "rev-parse", "--show-toplevel"]: return Result("/repo\n")
                if args[:3] == ["git", "branch", "--show-current"]: return Result("main\n")
                if args[:2] == ["git", "status"]: return Result("")
                if args[:3] == ["git", "show-ref", "--verify"]: return Result("", 0)
                return Result("")
        runner = ExistingBranchRunner()
        with self.assertRaises(WorkflowError) as error:
            GitClient(runner, Path("/repo")).create_branch("fix/APP-1", "main")
        self.assertEqual(error.exception.code, "BRANCH_ALREADY_EXISTS")
        self.assertFalse(any(call[:2] == ["git", "switch"] for call in runner.calls))

    def test_inspect_reports_both_paths_for_a_rename(self):
        class RenameRunner(FakeRunner):
            def run(self, args, **kwargs):
                self.calls.append(list(args))
                if args[:3] == ["git", "rev-parse", "--show-toplevel"]: return Result("/repo\n")
                if args[:3] == ["git", "branch", "--show-current"]: return Result("fix/APP-1\n")
                if args[:2] == ["git", "status"]: return Result("R  new-name.py\0old-name.py\0")
                return Result("")
        state = GitClient(RenameRunner(), Path("/repo")).inspect()
        self.assertTrue(state["isDirty"])
        self.assertEqual(state["changedFiles"], ["new-name.py", "old-name.py"])


if __name__ == "__main__": unittest.main()
