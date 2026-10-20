# Jira workflow skills

English | [日本語](README.ja.md)

`jira-work` is one Claude Code skill that chooses investigation or implementation based on the Jira issue type. Both workflows use the same Python 3 scripts.

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
npx skills add mugi111/jira-workflow-skills --skill jira-work -a claude-code -g
```

Omit `-g` for a project-local installation:

```bash
npx skills add mugi111/jira-workflow-skills --skill jira-work -a claude-code
```

You can also link or copy `skills/jira-work` into your Claude Code skills directory.

## Configure a project

By default, `Epic` and `Story` route to investigation; `Bug`, `Task`, and `Sub-task` route to fixing. To change the type names or routes, copy `.claude/jira-work/config.example.json` to `.claude/jira-work/config.json` in the target project and edit `investigateTypes` and `fixTypes`. A project config replaces the defaults. Matching ignores case. If a type is missing from both lists or appears in both, the router asks you to fix the mapping.

The same config file holds `baseBranch`, validation commands, review rules, and Jira settings. Set `baseBranch` to use a branch other than GitHub's default.

Configure the project's required checks before running the workflow. If no validation commands are configured, `validate` fails and the workflow stops.

```json
{
  "routing": {
    "investigateTypes": ["Epic", "Story"],
    "fixTypes": ["Bug", "Task", "Sub-task"]
  },
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

Review paths are relative to `.claude/jira-work/`. The CLI selects rules that match changed file paths.

`git branch create` fetches the base branch from `origin` and starts a new branch at `origin/<baseBranch>`. It stops if the fetch fails or the remote branch is missing.

Before staging, the CLI checks for common credential file names, `filters.excludePaths` globs, and content matching built-in patterns or `filters.secretPatterns`. A match stops staging and reports the file and pattern for you to review. The CLI never removes or edits files in response to a match.

Add `CLAUDE.md`, `.claude/rules/`, and a PR template to the target project as needed. Each fix gets a dedicated branch and a new PR. The workflow does not reuse existing branches or open PRs.

## Usage

```text
/jira-work PROJ-123
```

`jira-work` uses its shared CLI to read the issue type and choose an investigation or fix workflow. Add any constraints after the issue key.

Investigation examines related code and tests, then reports findings separately from hypotheses. It does not change files or Jira. The fix workflow confirms requirements before implementation, runs configured checks and review, then creates a pull request from a dedicated branch and moves Jira to In Review. It does not add Jira comments.

Direct script invocation (from the target repository):

```bash
python3 /path/to/skills/jira-work/scripts/cli.py issue route PROJ-123
python3 /path/to/skills/jira-work/scripts/cli.py issue get PROJ-123
python3 /path/to/skills/jira-work/scripts/cli.py check
```

For manual commits, first run `git stage --files-file <path>` and inspect the returned staged diff; then run `git commit --message-file <path> --files-file <path>`.

Each command prints one JSON object to stdout. Validation results include a summary for each check and a short failure excerpt with sensitive information redacted. Detailed output is saved in `jira-work/<issue-key>/` under the operating system's temporary directory and referenced by `details_path` or `detailsPath`. The scripts never execute Jira text or credentials as commands.

Save a checkpoint with `checkpoint PROJ-123 --phase analysis --summary "..." --next "..."` and read it with `checkpoint PROJ-123`. Record only brief, verified facts and recheck them before resuming.

## Development

```bash
python3 -m unittest discover -s tests -v
python3 skills/jira-work/scripts/cli.py --help
```

Unit tests mock external CLIs. Live Jira/GitHub write operations are not part of the test suite.

## Layout

- `skills/jira-work/SKILL.md`: issue-type routing, investigation, and fix workflows
- `skills/jira-work/scripts/`: shared JSON CLI and Jira/Git/GitHub/validation/review operations
- `skills/jira-work/references/`: review criteria and exception handling
- `tests/`: standard-library unit tests
