# Shared command policy

Edit `himkt/accepts.jsonc` to maintain the command gate used by Codex and Claude Code. Mise installs a copy at `~/.config/himkt/accepts.jsonc`. On every invocation, the validator reads this global policy and the project's `.rules/accepts.jsonc` when present. Install reviewed global changes explicitly. The global policy is required; every policy that is present must be readable and valid.

The policy contains integer `version: 1` and `allow`/`block` arrays. Each rule is an ordered argument array. The first element is a nonempty literal executable name or path. In subsequent elements, `**` matches zero or more whole arguments; `*` inside another element matches characters within one argument. Every other character is literal. Matching is case-sensitive and covers the whole argv. For example, `["git", "status"]` matches only `git status`; `["git", "status", "**"]` also matches its options.

The two files contribute rules to the same collections, with identical rules across files deduplicated. Every block rule takes precedence over every allow rule, regardless of source. An allow match produces a Claude approval response; Codex continues to its native permission checks. An unmatched command returns successfully with empty output, leaving the decision to Codex or Claude. Shell parsing and GitHub API checks apply to both allowed and unmatched commands. A malformed policy or command produces a denial.

Project discovery starts at the hook envelope's absolute `cwd`, or the hook process's working directory when `cwd` is absent. The nearest ancestor containing a `.git` file or directory is the project root, including worktrees and nested repositories. Outside Git, the working directory is the project root. Only that root's `.rules/accepts.jsonc` is loaded. Maintain project rules in trusted workspaces, since their allow rules can grant Claude permission. Native client permissions and sandbox controls continue to apply.

Run one literal command in each shell call. Quote literal operators, dollar signs, backticks, glob characters, and leading equals signs. Preserve argument order and pass values obtained from earlier calls directly. Use built-in filters such as `gh --jq` or `rg` options. Pipes, redirection, chaining, active expansion, assignments before executables, and unquoted newlines are blocked. Executable paths and wrappers have their own identity: `/usr/bin/git` and `env git` receive no authority from a `git` rule.

```sh
git status
gh api repos/himkt/config/contents/README.md --jq '.sha'
printf '%s' 'literal | $HOME * =sh'
```

`gh api`, including invocation through an executable path ending in `gh`, also requires an allowed endpoint/method pair in `bin/validate_gh_api.py`. Put the relative endpoint before options and resolve owner/repository placeholders to literal values. Explicit stdin body sources (`--input -` and typed fields ending in `=@-`) are blocked. Other file sources are trusted opaque paths, including stdin aliases, symlinks, and FIFOs. The gate checks endpoint/method and runtime host inputs; effective GitHub authentication configuration and final network destination remain deployment preconditions.

## Diagnostics

The `parse` and `validate` commands below read one JSON envelope from stdin. Submit the envelope using the invoking tool's stdin facility, then close stdin; run each command separately. `parse` prints literal argv without loading policy. Successful validation exits 0: Codex and standalone GitHub diagnostics use empty stdout, while Claude receives one approval JSON object only for an allow match. Unmatched commands produce empty stdout for both clients. Denials exit 2 with empty stdout and a bounded `BLOCKED [code]` message on stderr. The `test` commands run without stdin.

```sh
python3 bin/validate_bash.py parse
python3 bin/validate_bash.py validate --client codex
python3 bin/validate_bash.py validate --client claude
python3 bin/validate_gh_api.py validate
python3 bin/validate_bash.py test
python3 bin/validate_gh_api.py test
```

```json
{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"git status"}}
```

The standalone GitHub validator checks literal syntax and GitHub endpoint policy; the combined validator enforces the shared command policy. Run both embedded `test` commands to check parsing, policy matching, client responses, and GitHub restrictions. Tests clean up their temporary files. Run diagnostics through an operator shell when native agent permissions restrict Python execution.

## Installation and qualification

The embedded suites cover parsing, policy merging, executable paths, client responses, and GitHub checks. Codex sessions must trust the installed hooks. Qualify native permission behavior in each client after installing the helpers.

Mise copies both helpers, the policy, and the existing Codex/Claude configuration directories. Confirm that installed helper targets are regular copies rather than links into the repository. This isolates ordinary repository edits; protecting these files from agent writes requires separate filesystem controls. Review copy conflicts and preserve unrelated user configuration when applying updates.

1. Copy the reviewed policy and both executable helpers to their configured targets. Keep `validate_bash.py` and `validate_gh_api.py` together in `~/.local/bin` so imports resolve. Use the targeted mise command below after reviewing its dry run.
2. Validate policy readability, Python availability, helper permissions/imports, and both embedded suites. Compare installed content with the repository. Use trusted PATH and noninteractive Bash/zsh with executable aliases/functions and history expansion disabled, plus disabled zsh `MAGIC_EQUAL_SUBST`/`EXTENDED_GLOB`. GitHub requests assume the effective configuration, including `GH_CONFIG_DIR`, resolves default host `github.com` with no API-host override; report any unresolved prerequisite.
3. Copy the reviewed client settings and confirm trusted hook discovery. Both registrations select `Bash`, run synchronously with timeout 10, and invoke `validate_bash.py validate --client codex` or `--client claude`. Confirm Claude starts in the configured `auto` mode; account/model/organization availability and native ask rules can still require intervention. Launch Codex with `codex --approve-for-me` to retain the workspace sandbox and route escalation requests to auto-review. The equivalent settings are `approval_policy = "on-request"`, `approvals_reviewer = "auto_review"`, and `sandbox_mode = "workspace-write"`. The reviewer may approve or reject an escalation independently of the shared command policy. See [OpenAI's auto-review reference](https://learn.chatgpt.com/docs/sandboxing/auto-review).
4. Exercise an allowed command, an unmatched harmless command, and a harmless command explicitly listed in block using isolated test policies. Verify allow responses, native handling of the unmatched command, and `RULE_BLOCK` without execution for the blocked command. Include project allow/global block and global allow/project block cases. A missing global policy must produce `POLICY_MISSING`. Preserve the operator policy and client authentication environment, and record versions, hook trust, modes, and actual tool results.

```sh
mise bootstrap dotfiles apply --dry-run '~/.config/himkt/accepts.jsonc' '~/.local/bin/validate_bash.py' '~/.local/bin/validate_gh_api.py'
mise bootstrap dotfiles apply '~/.config/himkt/accepts.jsonc' '~/.local/bin/validate_bash.py' '~/.local/bin/validate_gh_api.py'
```

The two-second evaluation deadline and shared work budget produce exit-2 denials for stalled input and excessive evaluation. Missing interpreters/helpers, disabled or untrusted hooks, client timeouts, process termination, and failed output channels are infrastructure limits outside those denials. The gate covers intercepted shell calls. Codex session input through `write_stdin`, other tools, executable internals, subprocesses, mutable files, and network routing require separate controls for stronger containment.
