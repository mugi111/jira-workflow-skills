# jira-fix

English | [日本語](README.ja.md)

`jira-fix` is a Claude Code skill for resolving one Jira issue. It implements the fix, runs configured checks, reviews the changes, creates a GitHub pull request, and moves the issue to In Review. It does not add Jira comments. Python 3 scripts run the commands; Claude Code interprets requirements and decides what to change.

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

You can also link or copy `skills/jira-fix` into your Claude Code skills directory.

## Configure a project

Copy `.claude/jira-fix/config.example.json` from this repository to the target project's `.claude/jira-fix/config.json` and edit it. Set `baseBranch` to override the repository's GitHub default branch. Jira and review settings are optional.

Configure the project's required checks before running the workflow. If no validation commands are configured, `validate` fails and the workflow stops.

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
  "filters": {
    "excludePaths": [".env*", "secrets/**", "**/credentials.json"],
    "secretPatterns": []
  },
  "review": {
    "policy": "review/policy.md",
    "rules": {"apis/**/*.py": "review/rules/backend.md"}
  }
}
```

Review paths are relative to `.claude/jira-fix/`. The CLI selects review rules that match the changed file paths.

`git branch create` fetches the base branch from `origin` and starts a new branch at `origin/<baseBranch>`. It stops if the fetch fails or the remote branch is missing.

Before staging, the CLI checks for common credential file names, `filters.excludePaths` globs, and content matching built-in patterns or `filters.secretPatterns`. A match stops staging and reports the file and pattern for you to review. The CLI never removes or edits files in response to a match.

Add `CLAUDE.md`, `.claude/rules/`, and a PR template to the target project as needed. Each fix gets a dedicated branch and a new PR. The workflow does not reuse existing branches or open PRs.

## Usage

```text
/jira-fix PROJ-123
```

Add any constraints after the issue key.

Claude Code first checks whether the Jira issue describes the expected behavior well enough to implement. If requirements are missing, it asks you and waits for an answer. It then traces the affected code, callers, consumers, and boundaries to identify regression risks. It checks the project's language and framework versions before implementing the fix.

After running the configured checks and reviewing the diff, it commits only explicitly selected files, pushes, creates a new PR, and transitions the Jira issue without adding a comment. It verifies the PR and final Jira status before reporting completion.

Direct script invocation (from the target repository):

```bash
python3 /path/to/skills/jira-fix/scripts/cli.py check
python3 /path/to/skills/jira-fix/scripts/cli.py issue get PROJ-123
python3 /path/to/skills/jira-fix/scripts/cli.py git inspect
```

For manual commits, first run `git stage --files-file <path>` and inspect the returned staged diff; then run `git commit --message-file <path> --files-file <path>`.

Each command prints one JSON object to stdout. Validation results include a summary for each check and a short failure excerpt with sensitive information redacted. Full output is saved in `jira-fix/<issue-key>/` under the operating system's temporary directory. Follow `details_path` in the command response or `detailsPath` in the validation result to read it. The scripts never execute Jira text or credentials as commands.

Save a checkpoint with `checkpoint PROJ-123 --phase analysis --summary "..." --next "..."` and read it with `checkpoint PROJ-123`. Record only brief, verified facts and recheck them before resuming.

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
