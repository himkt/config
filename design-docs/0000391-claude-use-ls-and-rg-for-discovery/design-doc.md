# Use `ls` and `rg` for Claude Discovery

**Status**: Complete
**Progress**: 6/6 tasks complete
**Last Updated**: 2026-07-22

## Overview

Update the Claude configuration so routine repository discovery uses `ls` for immediate directory inspection, `rg --files` for recursive file discovery, and `rg` for content search. Align the Bash permission allowlist with that guidance so these commands run without approval prompts while preserving the existing shell-safety restrictions.

## Success Criteria

- [x] `claude/rules/bash-command.md` recommends `ls`, `rg --files`, and `rg` for their distinct discovery use cases and no longer classifies `ls` or `rg` as prohibited substitutions.
- [x] `claude/settings.json` explicitly allows both `Bash(rg)` and `Bash(rg *)`; the existing `ls` permissions remain valid.
- [x] Existing restrictions on shell chaining, redirects, command substitution, and unrelated prohibited commands remain unchanged.
- [x] Discovery guidance defines default ignore/hidden-file behavior and directs broad searches to use an explicit path or other narrowing arguments.
- [x] The edited settings file parses as JSON, the existing Bash validator self-tests pass, and repository checks find no contradictory generic Bash discovery guidance within `claude/rules/`.

---

## Background

`claude/rules/bash-command.md` currently sends directory listing to Glob and content search to Grep by grouping `ls` with `tree` and `rg` with `grep` in its prohibited-command table. This conflicts with issue #391's desired discovery workflow. Although `claude/settings.json` already allowlists `ls` with and without arguments, it does not explicitly allow `rg`, so guidance alone would still risk approval prompts.

---

## Specification

### Affected Files

| File | Required change |
|------|-----------------|
| `claude/rules/bash-command.md` | Define the shell-native discovery workflow, remove `ls` and `rg` from the prohibited substitutions, and update the broad-navigation note to refer to the new workflow. |
| `claude/settings.json` | Add explicit allow entries for `Bash(rg)` and `Bash(rg *)` beside the existing search/listing permissions. |

No other file needs modification:

- `claude/rules/tool-discovery.md` governs discovery of Skills and MCP tools, not repository paths or contents.
- `claude/bin/validate_bash.py` validates shell syntax hazards independently of the permission allowlist; it has no command-specific discovery policy.
- `claude/skills/` contains task-specific tool instructions and is outside this generic Bash-policy change. Existing references there do not override `claude/rules/bash-command.md` for routine repository discovery.

### Discovery Command Policy

Revise the Tool Substitution section of `claude/rules/bash-command.md` so the preferred commands are unambiguous:

| Need | Preferred command | Guidance |
|------|-------------------|----------|
| Inspect one directory | `ls [PATH]` | Use for a shallow view of immediate entries. |
| Discover files recursively | `rg --files [PATH]` | Add glob or path arguments when the search can be narrowed. |
| Search file contents | `rg PATTERN [PATH]` | Scope large searches with a path, file type, or glob. |

The prohibited-command table must stop grouping allowed commands with prohibited ones:

- Keep `find` mapped to Glob, `tree` mapped to Glob, and `grep` mapped to Grep.
- Remove `ls` and `rg` from those prohibited-command cells because the preceding discovery policy now directs Claude to use them.
- Keep every unrelated substitution and every restriction above the table unchanged.
- Update the Explore-agent fallback sentence from “simple Glob/Grep” to “simple `ls`/`rg` discovery” so the section does not contradict itself.

The normal `rg` ignore rules are the default. Claude should add `--hidden` or `--no-ignore` only when the task requires searching hidden or ignored content. Standard shell quoting remains responsible for paths and patterns containing spaces or metacharacters; no wrapper command or special filename-handling layer is introduced.

### Permission Contract

Add both settings entries to mirror the repository's explicit paired convention for commands such as `ls` and `tree`:

```json
"Bash(rg)",
"Bash(rg *)"
```

Under current Claude Code permission semantics, the trailing space-wildcard form also matches the bare command. Keeping the exact form makes the intended no-argument permission visible and consistent with the repository's existing style instead of relying only on that wildcard behavior. Place both entries in the alphabetized `permissions.allow` list near the existing `Bash(ls)` entries, and retain `Bash(ls)`, `Bash(ls *)`, and all existing allow, deny, and ask entries. The change assumes ripgrep is already installed in the managed environment and introduces no package or version change.

### Verification

This documentation-and-configuration change does not require a new automated test suite. Implementation verification must cover:

1. Parse `claude/settings.json` with `jq empty claude/settings.json`.
2. Run `claude/bin/validate_bash.py test` to ensure the existing syntax-safety hook still passes.
3. Use `rg` to confirm the two `Bash(rg...)` allow entries exist and the generic rule no longer presents `ls` or `rg` as prohibited.
4. Review `git diff --check` and the scoped diff for only the two affected files.

---

## Implementation

### Step 1: Align Permissions

- [x] Add `Bash(rg)` and `Bash(rg *)` to `permissions.allow` in `claude/settings.json`, preserving alphabetical placement and all existing permission entries. <!-- completed: 2026-07-22T23:27 -->

### Step 2: Revise the Bash Discovery Rule

- [x] Add positive, use-case-specific guidance for `ls`, `rg --files`, and `rg` to `claude/rules/bash-command.md`, including scoped-search and ignore/hidden-file behavior. <!-- completed: 2026-07-22T23:31 -->
- [x] Split the prohibited-command rows so `find`, `tree`, and `grep` retain their existing dedicated-tool substitutions while `ls` and `rg` are no longer prohibited. <!-- completed: 2026-07-22T23:31 -->
- [x] Update the broad-discovery fallback wording to reference `ls`/`rg` and verify all unrelated shell-safety and substitution rules are unchanged. <!-- completed: 2026-07-22T23:31 -->

### Step 3: Verify the Change

- [x] Parse `claude/settings.json`, run the Bash validator self-tests, and perform scoped `rg` consistency checks against `claude/rules/`. <!-- completed: 2026-07-22T23:36 -->
- [x] Run `git diff --check` and inspect the diff limited to `claude/settings.json` and `claude/rules/bash-command.md`. <!-- completed: 2026-07-22T23:36 -->

---

## Changelog

- 2026-07-22: Implemented all six tasks, passed validation, received fresh Reviewer approval, and opened PR #393.
