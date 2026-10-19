# jira-fix

[English](README.md) | 日本語

`jira-fix` は、1件の Jira 課題を修正する Claude Code スキルです。実装、設定済みのチェック、コードレビューを行い、GitHub で PR を作成して Jira 課題を In Review に移します。Jira にはコメントを追加しません。コマンドの実行は Python 3 スクリプトが担当し、要件の解釈や修正内容の判断は Claude Code が行います。

## 前提条件

- Claude Code、Node.js/npm
- Python 3.10 以降
- Git
- `gh auth login` で認証済みの [GitHub CLI](https://cli.github.com/)
- 設定・認証済みの [jira-cli](https://github.com/ankitpokhrel/jira-cli)

スクリプトは Python 標準ライブラリのみを使用します。認証情報の保存や LLM API の呼び出しは行いません。

## インストール

Claude Code 向けにグローバルインストールする場合：

```bash
npx skills add mugi111/jira-workflow-skills --skill jira-fix -a claude-code -g
```

プロジェクト単位でインストールする場合は `-g` を省略します。

```bash
npx skills add mugi111/jira-workflow-skills --skill jira-fix -a claude-code
```

`skills/jira-fix` を Claude Code のスキルディレクトリへリンクまたはコピーして利用することもできます。

## プロジェクトの設定

このリポジトリの `.claude/jira-fix/config.example.json` を、対象プロジェクトの `.claude/jira-fix/config.json` にコピーして編集します。GitHub のデフォルトブランチ以外を起点にする場合は、`baseBranch` を指定してください。Jira とレビューの設定も省略可能です。

検証コマンドは必須です。未設定の場合、`validate` は失敗して処理が停止するため、ワークフローの実行前にプロジェクトで必要なチェックを設定してください。

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

レビュー設定のパスは `.claude/jira-fix/` を基準とする相対パスです。変更されたファイルのパスに一致するレビュールールが選択されます。

`git branch create` は、起点となるブランチを `origin` から取得し、`origin/<baseBranch>` を起点に新しいブランチを作成します。取得に失敗した場合や、リモートブランチが存在しない場合は停止します。

ステージング時には、一般的な認証情報ファイル名、`filters.excludePaths` の glob パターン、組み込みまたは `filters.secretPatterns` で設定した内容のパターンをチェックします。一致した場合はステージングを停止し、確認が必要なファイルやパターンを報告します。ファイルを自動で削除・編集することはありません。

必要に応じて、対象プロジェクトに `CLAUDE.md`、`.claude/rules/`、PR テンプレートを追加してください。修正ごとに専用ブランチと新しい PR を作成し、既存ブランチやオープンな PR は再利用しません。

## 使い方

```text
/jira-fix PROJ-123
```

課題キーの後に追加の制約を指定できます。

Claude Code はまず、Jira 課題に期待する動作が十分に記載されているかを確認します。要件が不足している場合はユーザーに質問し、回答を待ちます。その後、関連するコード、呼び出し元、利用箇所、処理の境界をたどり、既存機能への影響を調べます。実装は対象プロジェクトの言語・フレームワークのバージョンに合わせます。

設定済みの検証と差分レビューを行い、明示的に選択したファイルだけをコミット・プッシュして、修正用の新しい PR を作成します。Jira にはコメントを追加せず、ステータスを遷移させます。PR と最終的な Jira ステータスを確認してから完了を報告します。

対象リポジトリからスクリプトを直接実行する場合：

```bash
python3 /path/to/skills/jira-fix/scripts/cli.py check
python3 /path/to/skills/jira-fix/scripts/cli.py issue get PROJ-123
python3 /path/to/skills/jira-fix/scripts/cli.py git inspect
```

手動でコミットする場合は、まず `git stage --files-file <path>` を実行し、返されたステージ済み差分を確認します。その後、`git commit --message-file <path> --files-file <path>` を実行します。

各コマンドは、結果を1つの JSON オブジェクトとして標準出力へ出します。検証結果にはチェックごとの要約と、機密情報を伏せた失敗ログの抜粋が含まれます。完全な出力は、OS の一時ディレクトリ配下の `jira-fix/<issue-key>/` に保存されます。コマンドの応答にある `details_path`、または検証結果の `detailsPath` から参照できます。スクリプトが Jira のテキストや認証情報をコマンドとして実行することはありません。

チェックポイントは `checkpoint PROJ-123 --phase analysis --summary "..." --next "..."` で保存し、`checkpoint PROJ-123` で読み込めます。確認済みの事実だけを簡潔に記録し、再開時には内容を再確認します。

## 開発

```bash
python3 -m unittest discover -s tests -v
python3 skills/jira-fix/scripts/cli.py --help
```

ユニットテストでは外部 CLI をモック化しています。実際の Jira / GitHub への書き込み操作はテストスイートに含まれません。

## ディレクトリ構成

- `skills/jira-fix/SKILL.md`：ワークフローとエージェントの役割
- `skills/jira-fix/scripts/`：JSON CLI と Jira / Git / GitHub / 検証 / レビューのアダプター
- `skills/jira-fix/references/review.md`：共通のレビュー基準
- `tests/`：標準ライブラリを使用したユニットテスト
