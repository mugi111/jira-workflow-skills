import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "skills" / "jira-work" / "scripts"))
import cli
from cli import main


class CliTests(unittest.TestCase):
    def test_workflow_error_is_json_and_nonzero(self):
        from common import WorkflowError
        with patch.object(cli, "execute", side_effect=WorkflowError("NOPE", "expected")), patch("builtins.print") as output:
            code = main(["check"])
        self.assertEqual(code, 1)
        payload = json.loads(output.call_args.args[0])
        self.assertFalse(payload["success"])
        self.assertEqual(payload["error"]["code"], "NOPE")

    def test_invalid_arguments_are_json(self):
        with patch("builtins.print") as output:
            code = main(["issue", "get"])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output.call_args.args[0])["error"]["code"], "INVALID_ARGUMENTS")

    def test_help_is_json(self):
        with patch("builtins.print") as output:
            code = main(["--help"])
        self.assertEqual(code, 0)
        payload = json.loads(output.call_args.args[0])
        self.assertTrue(payload["success"])
        self.assertIn("usage: jira-work", payload["data"]["help"])


if __name__ == "__main__": unittest.main()
