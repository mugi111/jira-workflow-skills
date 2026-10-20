import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skills" / "jira-work" / "scripts"))
from common import WorkflowError, _validate_config


class ConfigValidationTests(unittest.TestCase):
    def test_boolean_is_not_accepted_as_max_comments_integer(self):
        with self.assertRaises(WorkflowError) as error:
            _validate_config({"jira": {"maxComments": True}})
        self.assertEqual(error.exception.code, "INVALID_CONFIG")

    def test_boolean_is_not_accepted_as_timeout_integer(self):
        with self.assertRaises(WorkflowError) as error:
            _validate_config({"validation": {"commands": [
                {"name": "check", "argv": ["python3", "-V"], "timeoutSeconds": False},
            ]}})
        self.assertEqual(error.exception.code, "INVALID_CONFIG")

    def test_real_integer_limits_are_accepted(self):
        _validate_config({
            "jira": {"maxComments": 0},
            "validation": {"commands": [
                {"name": "check", "argv": ["python3", "-V"], "timeoutSeconds": 1},
            ]},
        })


if __name__ == "__main__":
    unittest.main()
