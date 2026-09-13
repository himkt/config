# Shared command policy

Edit `himkt/accepts.jsonc` to maintain the command gate used by Codex and Claude Code. Mise installs a copy at `~/.config/himkt/accepts.jsonc`; the validator reads that fixed path on every invocation. Install reviewed changes explicitly. A missing, unreadable, or invalid policy blocks the intercepted command.

The policy contains integer `version: 1` and `allow`/`block` arrays. Each rule is an ordered argument array. `**` matches zero or more whole arguments; `*` inside another element matches characters within one argument. Every other character is literal. Matching is case-sensitive and covers the whole argv. Block rules win, and unmatched commands are blocked. The seed accounts for all 62 Claude Bash entries, normalized to 43 allow rules and 18 block rules, including the CAFleet shell-prompt exceptions. Native Claude permissions and Codex rules remain additional controls; changing them alone cannot authorize a command outside this policy.

Run one literal command in each shell call. Quote literal operators, dollar signs, backticks, glob characters, and leading equals signs. Preserve argument order and pass values obtained from earlier calls directly. Use built-in filters such as `gh --jq` or `rg` options. Pipes, redirection, chaining, active expansion, assignments before executables, and unquoted newlines are blocked. Executable paths and wrappers have their own identity: `/usr/bin/git` and `env git` receive no authority from a `git` rule.

```sh
git status
gh api repos/himkt/config/contents/README.md --jq '.sha'
printf '%s' 'literal | $HOME * =sh'
```

`gh api` also requires an allowed endpoint/method pair in `bin/validate_gh_api.py`. Put the relative endpoint before options and resolve owner/repository placeholders to literal values. Explicit stdin body sources (`--input -` and typed fields ending in `=@-`) are blocked. Other file sources are trusted opaque paths, including stdin aliases, symlinks, and FIFOs. The gate checks endpoint/method and runtime host inputs; effective GitHub authentication configuration and final network destination remain deployment preconditions.

## Diagnostics

The `parse` and `validate` commands below read one JSON envelope from stdin. Submit the envelope using the invoking tool's stdin facility, then close stdin; run each command separately. `parse` prints literal argv without loading policy. Successful validation exits 0: Codex and standalone GitHub diagnostics use empty stdout, while Claude receives one approval JSON object. Denials exit 2 with empty stdout and a bounded `BLOCKED [code]` message on stderr. The `test` commands run without stdin.

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

Verified on 2026-09-13 with Codex 0.153.4 and Claude Code 2.1.260: installed copies matched the repository; both clients executed `printf QUALIFICATION_ALLOWED`, rejected `/usr/bin/printf QUALIFICATION_DENIED` with `RULE_UNMATCHED`, and rejected the allowed command with `POLICY_MISSING` when only the hook's HOME pointed to an empty directory. Codex used `--ask-for-approval never --sandbox workspace-write` with reviewed hooks trusted for that invocation via `--dangerously-bypass-hook-trust`; Claude reported `auto` mode. Ordinary Codex sessions still need their own hook trust. The embedded suites cover the broader parsing, policy, GitHub, and error contracts.

Mise copies both helpers, the policy, and the existing Codex/Claude configuration directories. Confirm that installed helper targets are regular copies rather than links into the repository. This isolates ordinary repository edits; protecting these files from agent writes requires separate filesystem controls. Review copy conflicts and preserve unrelated user configuration when applying updates.

1. Copy the reviewed policy and both executable helpers to their configured targets. Keep `validate_bash.py` and `validate_gh_api.py` together in `~/.local/bin` so imports resolve. Use the targeted mise command below after reviewing its dry run.
2. Validate policy readability, Python availability, helper permissions/imports, and both embedded suites. Compare installed content with the repository. Use trusted PATH and noninteractive Bash/zsh with executable aliases/functions and history expansion disabled, plus disabled zsh `MAGIC_EQUAL_SUBST`/`EXTENDED_GLOB`. GitHub requests assume the effective configuration, including `GH_CONFIG_DIR`, resolves default host `github.com` with no API-host override; report any unresolved prerequisite.
3. Copy the reviewed client settings and confirm trusted hook discovery. Both registrations select `Bash`, run synchronously with timeout 10, and invoke `validate_bash.py validate --client codex` or `--client claude`. Confirm Claude starts in the configured `auto` mode; account/model/organization availability and native ask rules can still require intervention. Launch Codex with `codex --ask-for-approval never --sandbox workspace-write`, retaining its filesystem/network controls. These flags independently select approval behavior and sandbox scope. See [OpenAI's approval and sandbox reference](https://learn.chatgpt.com/docs/agent-approvals-security).
4. Ask each pinned client to execute `printf QUALIFICATION_ALLOWED` and inspect the tool output. Then request `/usr/bin/printf QUALIFICATION_DENIED`: require `RULE_UNMATCHED` and no command execution. Finally, temporarily override HOME for the validation hook process alone to an existing hidden directory whose policy path is absent, and repeat the allowed command; require `POLICY_MISSING` without execution. Preserve the client authentication environment and operator policy, restore the normal hook home, and repeat the unmatched-command check. Record versions, hook trust, modes, actual tool results, and any missing prerequisite before proceeding with ordinary work.

```sh
mise bootstrap dotfiles apply --dry-run '~/.config/himkt/accepts.jsonc' '~/.local/bin/validate_bash.py' '~/.local/bin/validate_gh_api.py'
mise bootstrap dotfiles apply '~/.config/himkt/accepts.jsonc' '~/.local/bin/validate_bash.py' '~/.local/bin/validate_gh_api.py'
```

The two-second evaluation deadline and shared work budget produce exit-2 denials for stalled input and excessive evaluation. Missing interpreters/helpers, disabled or untrusted hooks, client timeouts, process termination, and failed output channels are infrastructure limits outside those denials. The gate covers intercepted shell calls. Codex session input through `write_stdin`, other tools, executable internals, subprocesses, mutable files, and network routing require separate controls for stronger containment.
