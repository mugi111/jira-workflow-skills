# Jira workflow skills

[English](README.md) | 日本語

`jira-work` は Jira 課題を調査するか修正するか、課題タイプを見て選ぶ Claude Code スキルです。どちらの処理も同じ Python 3 スクリプトを使います。

## 前提条件

- Claude Code、Node.js/npm
- Python 3.10 以降
- Git
- `gh auth login` で認証済みの [GitHub CLI](https://cli.github.com/)
- 設定・認証済みの [jira-cli](https://github.com/ankitpokhrel/jira-cli)

スクリプトは Python 標準ライブラリのみを使用します。認証情報の保存や LLM API の呼び出しは行いません。

## インストール

Claude Code にグローバルインストールする場合：

```bash
npx skills add mugi111/jira-workflow-skills --skill jira-work -a claude-code -g
```

プロジェクト単位でインストールする場合は `-g` を省きます。

```bash
npx skills add mugi111/jira-workflow-skills --skill jira-work -a claude-code
```

`skills/jira-work` を Claude Code のスキルディレクトリへリンクまたはコピーして使うこともできます。

## プロジェクトの設定

既定では `Epic` と `Story` を調査、`Bug`、`Task`、`Sub-task` を修正に振り分けます。種別名や割り当てを変える場合は、このリポジトリの `.claude/jira-work/config.example.json` を対象プロジェクトの `.claude/jira-work/config.json` にコピーして編集します。設定がある場合は、既定値を置き換えます。名前は大文字小文字を無視して照合します。一覧にない種別や両方にある種別は振り分けず、確認を求めます。

同じ設定ファイルで `baseBranch`、検証コマンド、レビュー規則、Jira の設定も行います。GitHub のデフォルトブランチ以外を起点にする場合は `baseBranch` を指定します。

検証コマンドは必須です。未設定の場合、`validate` は失敗して処理が停止するため、ワークフローの実行前にプロジェクトで必要なチェックを設定してください。

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

レビュー設定のパスは `.claude/jira-work/` を基準とする相対パスです。変更ファイルに一致するレビュールールを選びます。

`git branch create` は、起点となるブランチを `origin` から取得し、`origin/<baseBranch>` を起点に新しいブランチを作成します。取得に失敗した場合や、リモートブランチが存在しない場合は停止します。

ステージング時には、一般的な認証情報ファイル名、`filters.excludePaths` の glob パターン、組み込みまたは `filters.secretPatterns` で設定した内容のパターンをチェックします。一致した場合はステージングを停止し、確認が必要なファイルやパターンを報告します。ファイルを自動で削除・編集することはありません。

必要に応じて、対象プロジェクトに `CLAUDE.md`、`.claude/rules/`、PR テンプレートを追加してください。修正ごとに専用ブランチと新しい PR を作成し、既存ブランチやオープンな PR は再利用しません。

## 使い方

```text
/jira-work PROJ-123
```

`jira-work` は共有 CLI で課題タイプを取得し、調査または修正の手順を選びます。課題キーの後ろに追加の制約も指定できます。

調査では関連コードやテストを調べ、根拠と推定を分けて報告します。この手順ではファイルや Jira を変更しません。修正では要件を確認してから実装し、設定済みの検証とレビューを行います。問題がなければ専用ブランチから PR を作成し、Jira を In Review に移します。Jira へのコメント追加は行いません。

対象リポジトリからスクリプトを直接実行する場合：

```bash
python3 /path/to/skills/jira-work/scripts/cli.py issue route PROJ-123
python3 /path/to/skills/jira-work/scripts/cli.py issue get PROJ-123
python3 /path/to/skills/jira-work/scripts/cli.py check
```

手動でコミットする場合は、まず `git stage --files-file <path>` を実行し、返されたステージ済み差分を確認します。その後、`git commit --message-file <path> --files-file <path>` を実行します。

各コマンドは結果を1つの JSON オブジェクトとして標準出力へ出します。検証結果にはチェックごとの要約と、機密情報を伏せた失敗ログの抜粋が含まれます。詳しい出力は OS の一時ディレクトリ配下の `jira-work/<issue-key>/` に保存され、応答の `details_path` または検証結果の `detailsPath` から参照できます。スクリプトが Jira のテキストや認証情報をコマンドとして実行することはありません。

チェックポイントは `checkpoint PROJ-123 --phase analysis --summary "..." --next "..."` で保存し、`checkpoint PROJ-123` で読み込めます。確認済みの事実だけを簡潔に記録し、再開時には内容を再確認します。

## 開発

```bash
python3 -m unittest discover -s tests -v
python3 skills/jira-work/scripts/cli.py --help
```

ユニットテストでは外部 CLI をモック化しています。実際の Jira / GitHub への書き込み操作はテストスイートに含まれません。

## ディレクトリ構成

- `skills/jira-work/SKILL.md`：課題タイプ判定、調査、修正のワークフロー
- `skills/jira-work/scripts/`：共有 JSON CLI と Jira / Git / GitHub / 検証 / レビューの処理
- `skills/jira-work/references/`：レビュー基準と例外対応
- `tests/`：標準ライブラリを使用したユニットテスト
