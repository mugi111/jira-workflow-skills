import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "skills" / "jira-fix" / "scripts"))
from jira import normalize_issue, validate_key
from common import WorkflowError
from jira import JiraClient


class JiraNormalizationTests(unittest.TestCase):
    def test_normalize_issue_preserves_acceptance_criteria(self):
        issue = normalize_issue({"key": "APP-3", "fields": {
            "summary": "Summary", "description": "Description",
            "customfield_123": "Given X, then Y", "issuetype": {"name": "Bug"},
            "status": {"name": "Open"}, "issuelinks": [{"outwardIssue": {"key": "APP-2"}}],
        }}, "APP-3", "customfield_123")
        self.assertEqual(issue["acceptanceCriteria"], "Given X, then Y")
        self.assertEqual(issue["relatedIssues"], ["APP-2"])

    def test_adf_description_extracts_body_without_structural_metadata(self):
        issue = normalize_issue({"fields": {
            "summary": "ADF issue",
            "description": {
                "type": "doc", "version": 1,
                "content": [
                    {"type": "heading", "attrs": {"level": 2}, "content": [
                        {"type": "text", "text": "背景"},
                    ]},
                    {"type": "paragraph", "content": [
                        {"type": "text", "text": "条件"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "期待結果"},
                    ]},
                    {"type": "bulletList", "content": [
                        {"type": "listItem", "content": [{"type": "paragraph", "content": [
                            {"type": "text", "text": "項目A"},
                        ]}]},
                    ]},
                ],
            },
        }}, "APP-4")
        self.assertEqual(issue["description"], "背景\n条件\n期待結果\n- 項目A")
        self.assertNotIn("doc", issue["description"])
        self.assertNotIn("version", issue["description"])

    def test_invalid_issue_key_rejected(self):
        with self.assertRaises(WorkflowError):
            validate_key("bad key")

    def test_missing_configured_acceptance_criteria_field_is_not_silently_ignored(self):
        with self.assertRaises(WorkflowError) as error:
            normalize_issue({"fields": {"summary": "Issue"}}, "APP-1", "customfield_999")
        self.assertEqual(error.exception.code, "ACCEPTANCE_CRITERIA_MISSING")

    def test_comments_are_extracted_from_raw_jira_json(self):
        class Result:
            returncode = 0; stderr = ""
            stdout = '{"fields":{"comment":{"comments":[{"author":{"displayName":"A"},"body":"note"}]}}}'
        class Runner:
            def run(self, args, **kwargs):
                self.args = args
                return Result()
        runner = Runner()
        comments = JiraClient(runner).get_comments("APP-1", 3)
        self.assertEqual(comments[0]["body"], "note")
        self.assertEqual(runner.args[-1], "--raw")

    def test_explicit_empty_comment_list_is_valid(self):
        class Result:
            returncode = 0; stderr = ""
            stdout = '{"fields":{"comment":{"comments":[]}}}'
        class Runner:
            def run(self, args, **kwargs): return Result()
        self.assertEqual(JiraClient(Runner()).get_comments("APP-1"), [])

    def test_missing_comment_list_fails_closed(self):
        class Result:
            returncode = 0; stderr = ""
            stdout = '{"fields":{}}'
        class Runner:
            def run(self, args, **kwargs): return Result()
        with self.assertRaises(WorkflowError) as error:
            JiraClient(Runner()).get_comments("APP-1")
        self.assertEqual(error.exception.code, "JIRA_COMMENTS_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
