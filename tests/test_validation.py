import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "skills" / "jira-work" / "scripts"))
from validation import run_validation
from common import redact_sensitive, WorkflowError


class Result:
    returncode = 0
    stdout = "ok"
    stderr = ""


class Runner:
    def run(self, *args, **kwargs): return Result()


class ValidationTests(unittest.TestCase):
    def test_configured_command_runs_and_summarizes(self):
        config = {"validation": {"commands": [{"name": "unit", "argv": ["python3", "-m", "unittest"]}]}}
        result = run_validation(config, Path.cwd(), "APP-1", Runner())
        self.assertEqual(result["checks"][0]["status"], "passed")
        self.assertTrue(Path(result["detailsPath"]).is_file())

    def test_missing_commands_are_explicitly_unconfigured(self):
        self.assertFalse(run_validation({}, Path.cwd())["configured"])

    def test_sensitive_values_are_redacted_from_logs(self):
        output = redact_sensitive("Authorization: Bearer abc token=xyz ghp_" + "a" * 25)
        self.assertNotIn("abc", output)
        self.assertNotIn("xyz", output)
        self.assertNotIn("ghp_", output)

    def test_failed_command_returns_check_summary_and_log_path(self):
        class Failed(Result):
            returncode = 1
            stdout = "assertion failed"
        class FailedRunner:
            def run(self, *args, **kwargs): return Failed()
        config = {"validation": {"commands": [{"name": "unit", "argv": ["python3", "-m", "unittest"]}]}}
        with self.assertRaises(WorkflowError) as error:
            run_validation(config, Path.cwd(), "APP-1", FailedRunner())
        self.assertEqual(error.exception.code, "VALIDATION_FAILED")
        self.assertEqual(error.exception.data["checks"][0]["status"], "failed")
        self.assertTrue(Path(error.exception.details_path).is_file())


if __name__ == "__main__": unittest.main()
