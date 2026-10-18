import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "skills" / "jira-fix" / "scripts"))
from review import collect_review_context


class Runner:
    def run(self, args, **kwargs):
        class Result: stdout = "apis/auth.py\nREADME.md\n"; stderr = ""; returncode = 0
        return Result()


class ReviewTests(unittest.TestCase):
    def test_selects_only_matching_rules_and_existing_policies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / ".claude/jira-fix/review/rules").mkdir(parents=True)
            (root / ".claude/jira-fix/review/policy.md").write_text("policy")
            (root / ".claude/jira-fix/review/rules/backend.md").write_text("backend")
            config = {"review": {"policy": "review/policy.md", "rules": {"apis/*.py": "review/rules/backend.md", "frontend/*.tsx": "review/rules/front.md"}}}
            result = collect_review_context(root, "main", config, Runner())
            self.assertEqual(result["changedFiles"], ["apis/auth.py", "README.md"])
            self.assertEqual(len(result["reviewPolicies"]), 2)


if __name__ == "__main__": unittest.main()
