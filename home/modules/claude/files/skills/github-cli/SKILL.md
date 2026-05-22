---
name: github-cli
description: Use this skill when the user shares a GitHub URL (issue or pull request). Automatically fetch details using GitHub CLI (gh command). Triggered by URLs like github.com/himkt/.claude/issues/123 or github.com/himkt/.claude/pull/123. Do NOT run gh commands directly — always invoke this skill first.
---

# GitHub CLI Skill

Fetch GitHub issues and pull requests with `gh` + `--json` + `--jq`.

## Workflow

1. Parse `{owner}`, `{repo}`, `{number}` from the URL. If only a number was given, run `gh repo view --json nameWithOwner -q .nameWithOwner`.
2. Always pass `--jq` to project fields and, when relevant, drop out-of-scope rows. Unfiltered comment/review/file payloads run to thousands of lines; a focused filter shrinks input 10–100×.

Use `gh --jq` directly — do not pipe to external `jq`. The local Bash validator rejects multi-command pipes.

Common `select(...)` predicates:

- Time window: `select((.created_at | fromdateiso8601) > (now - 10800))`
- Author: `select(.user.login == "...")`
- State: `select(.state == "OPEN")`
- Unresolved threads: `select(.in_reply_to_id == null)`

## Fetch commands

```bash
# Issue
gh issue view {url} --json title,author,body,state,labels,comments --jq '...'

# PR overview
gh pr view {url} --json title,author,body,state,reviewDecision,baseRefName,headRefName,comments --jq '...'

# Diff (do NOT use gh api for diffs)
gh pr diff {url}              # full
gh pr diff {url} --name-only  # files only

# Inline review comments
gh api repos/{owner}/{repo}/pulls/{number}/comments --paginate --jq '[.[] | {user: .user.login, path, line, body, html_url, created_at}]'

# Review summaries
gh api repos/{owner}/{repo}/pulls/{number}/reviews --paginate --jq '[.[] | {user: .user.login, state, body, submitted_at}]'

# CI checks
gh pr checks {url}
```

## Creating a PR

```bash
gh pr create --fill                          # auto-populate title+body from commits
gh pr edit {number} --add-reviewer @copilot  # always request Copilot review immediately after
```

Use `--title` / `--body-file` only when the user explicitly asks for a custom title/body.
