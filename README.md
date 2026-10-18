# jira-fix

`jira-fix` is a Claude Code Skill that guides one Jira issue through focused implementation, configured validation, code review, a GitHub pull request, and a verified Jira transition to **In Review**. Deterministic operations are handled by Python 3 scripts; semantic decisions remain with Claude Code.

> This repository is under initial development. The Jira CLI and GitHub CLI adapters rely on their installed command-line tools and should be exercised against a sandbox Jira/GitHub project before production use.

## Prerequisites

- Claude Code, Node.js/npm
- Python 3.10 or later
- Git
- [GitHub CLI](https://cli.github.com/) authenticated with `gh auth login`
- [jira-cli](https://github.com/ankitpokhrel/jira-cli) configured and authenticated

The scripts use only the Python standard library. They do not store credentials or call an LLM API.

## Install

Install globally for Claude Code:

```bash
npx skills add mugi111/jira-workflow-skills --skill jira-fix -a claude-code -g
```

Omit `-g` for a project-local installation:

```bash
npx skills add mugi111/jira-workflow-skills --skill jira-fix -a claude-code
```

The repository is also usable locally by linking/copying `skills/jira-fix` into the appropriate Claude Code skills directory.

## Configure a project

Copy `.claude/jira-fix/config.example.json` from this repository into the target project's `.claude/jira-fix/config.json`, then adjust it. Configure `baseBranch` explicitly; the Skill will not silently use GitHub's default branch. Jira and review settings are optional. Validation commands are required: `validate` fails closed when none are configured, so configure the project's required checks before running the workflow.

```json
{
  "baseBranch": "develop",
  "jira": {
    "reviewStatus": "In Review",
    "maxComments": 5,
    "acceptanceCriteriaField": null
  },
  "validation": {
    "commands": [
      {"name": "unit", "argv": ["python3", "-m", "unittest", "discover", "-s", "tests"], "timeoutSeconds": 900}
    ]
  },
  "review": {
    "policy": "review/policy.md",
    "rules": {"apis/**/*.py": "review/rules/backend.md"}
  }
}
```

Review paths are relative to `.claude/jira-fix/`. Review rules are selected by matching changed file paths. Add `CLAUDE.md`, `.claude/rules/`, and a PR template to the target project as needed. Each new correction uses a dedicated branch and creates a new PR; an existing branch or open PR is not reused.

## Usage

```text
/jira-fix PROJ-123
```

Additional constraints may follow the issue key. Before implementation, the Skill checks that the Jira issue describes enough expected behavior to proceed; if requirements are missing, it asks the user and waits. It then maps the affected code, consumers, boundaries, and regression risks, identifying the target project's language/framework versions before implementing as a specialist in that stack. It runs configured validation, reviews the diff, commits only explicitly selected files, pushes, creates a new PR for the correction, and then comments on and transitions the Jira issue. It reports completion only after verifying the PR and final Jira status.

Direct script invocation (from the target repository):

```bash
python3 /path/to/skills/jira-fix/scripts/cli.py check
python3 /path/to/skills/jira-fix/scripts/cli.py issue get PROJ-123
python3 /path/to/skills/jira-fix/scripts/cli.py git inspect
```

For manual commits, first run `git stage --files-file <path>` and inspect the returned staged diff; then run `git commit --message-file <path> --files-file <path>`.

Every command prints a single JSON envelope to stdout. Full validation output is stored under the operating system's temporary directory in `jira-fix/<issue-key>/`; inspect `details_path` on failure. No Jira text or credentials are used as executable commands.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 skills/jira-fix/scripts/cli.py --help
```

Unit tests mock external CLIs. Live Jira/GitHub write operations are not part of the test suite.

## Layout

- `skills/jira-fix/SKILL.md`: workflow and agent responsibilities
- `skills/jira-fix/scripts/`: JSON CLI and Jira/Git/GitHub/validation/review adapters
- `skills/jira-fix/references/review.md`: shared review criteria
- `tests/`: standard-library unit tests
