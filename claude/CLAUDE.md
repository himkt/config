# Agent Instructions

## Affirmative Writing

Say what should happen. In prose, prescribe the desired behavior directly. In code, assert the expected invariant and fail loudly when it is violated. A document is a clean specification of intended behavior, not a pile of reactive "do not" patches; a program states its assumptions and stops when they break, instead of masking a violation with a meaningless fallback value.

This is not a ban on the words "never" or "do not", nor on defaults. A prohibition is the right tool when it is the clearest way to state a genuine hard constraint — and it is strongest paired with the affirmative instruction it enforces ("always use X" alongside "never use Y"). A default is the right tool when absence is an expected, valid state with a well-defined correct behavior. The anti-pattern is the *reactive residue*: a prohibition bolted on in place of a missing positive spec, or a fallback bolted on in place of a missing invariant check.

### Documentation: prescribe the desired behavior

Lead with what the reader should do and what correct looks like; let the prohibitions fall out of the positive specification. When a hard constraint genuinely needs a prohibition, state it — and pair it with the affirmative.

#### Forbidden patterns

- A section that is only a list of "DO NOT X / NEVER Y" bullets, with no statement of the desired behavior the don'ts protect.
- A new "don't do Z" appended each time something goes wrong, instead of revising the positive spec so Z is no longer the natural reading.
- A prohibition with no affirmative counterpart, leaving the reader to infer what they should do instead.

#### What's legitimate

- Strong negative phrasing for a genuine hard constraint, paired with the positive instruction — e.g. "NEVER use HEREDOC for git commit; always use `git commit -m`".
- A short "Forbidden patterns" / "anti-patterns" list that *complements* a positive spec (as in this section and in § Removal), rather than substituting for one.

### Code: fail fast

When an expected condition is violated, raise (or assert) at the point of violation. Do not substitute a meaningless sentinel or default that lets corrupt state flow downstream, where the real failure surfaces far from its cause and is far harder to diagnose.

#### Forbidden patterns

- Silent sentinels for a violated invariant: `rate = total / count if count else 1`; `value = lookup.get(key) or 0`; `user = users.get(uid, AnonymousUser())` where `uid` is required to exist.
- A `try/except` that swallows the error and returns a placeholder, hiding a condition the caller needed to know about.
- Coercing a missing *required* input to an empty/zero/default value instead of raising.

#### What's legitimate

- A default that *is* the correct behavior, where absence is an expected, valid state — e.g. `retries = config.get("retries", 3)` with 3 a documented, sensible default.
- Catching an exception you can genuinely recover from, and re-raising (or raising a clearer error for) the ones you cannot.
- An `assert`/`raise` guarding a "can't happen" invariant — the loud failure is the point.

The test: a fallback is legitimate when absence or variation is an expected, well-specified case; it is error-swallowing when absence signals a bug or corrupt state and the fallback merely hides it.

### Why

Affirmative documentation tells a reader what to do in one read; a wall of prohibitions forces them to reverse-engineer the intent from the don'ts. Fail-fast code surfaces a bug at its source; an error-swallowing fallback ships the bug downstream as corrupt state. Both failures share one root: writing the reaction to the bad case instead of the intended good case. This is the same principle as § Removal — after a change, the artifact should read as a clean statement of the current, intended state, with no reactive negative residue (deprecation notices, ad-hoc prohibitions, or silent fallbacks) left behind.

### Scope

Applies across all projects, whenever you write or edit documentation or code:

- Authoring or revising docs, READMEs, skills, rules, and comments — prefer the positive spec.
- Writing code that reads configuration, looks up a key, divides, parses, or otherwise depends on an invariant — assert or raise rather than fall back to a meaningless value.
- Reviewing or refactoring — when you find a reactive prohibition or an error-swallowing fallback, replace it with the affirmative spec or the explicit failure.

## Code Comments

Write code that explains itself. Add a comment ONLY WHEN THE LOGIC CANNOT BE UNDERSTOOD WITHOUT IT — carry intent through naming, structure, and small well-named functions, and reserve comments for meaning the code itself cannot express.

Before writing a comment, first try to make it unnecessary: rename, extract, or restructure. Write the comment only if the code still cannot carry the meaning.

### When a comment is justified

- A constraint or invariant the code cannot express (e.g., "callers rely on this list staying sorted", "this call must precede the flush because the API mutates state on read")
- A workaround with an external cause (upstream bug, platform quirk) that would otherwise read as a mistake
- The "why" behind a decision that contradicts the obvious approach

### Forbidden patterns

- Comments that restate what the code does (`# increment counter`, `// loop over users`)
- Section-header comments narrating a function's steps instead of extracting named functions
- Comments addressed to the reviewer ("changed to fix X", "now handles Y correctly") — that context belongs in the commit message or PR description
- Commented-out code — delete it; git history is the archive

### Scope

Applies across all projects whenever source code is written, edited, or reviewed. When editing existing code, match the file's comment density for legitimate comments, and remove comments made redundant by your change rather than leaving them stale.

## Removal

When removing a feature, option, file, or concept from a project, delete every corresponding mention from the repository in the same change. Do not leave historical deprecation notices behind.

The git history and the design document (if any) are the historical record. Source code, user-facing docs, skills, and examples should describe only the current state.

### Forbidden patterns

- Callouts like `**X deprecated**: see design 0000NNN for the restoration plan` in user-facing docs
- Sentences like `pre-existing X rows are preserved for forensic visibility` in schema/data-model docs (keep the column behavior accurate; do not document the removed value)
- Comments like `# X was deprecated in design NNNN` in source code
- Pointers like `(See §13 for the restoration plan)` in README / SKILL.md / cli-options
- "Multi-runner support" / "Backend selector" / similar Features bullets that describe an option that no longer exists
- Flag rows in CLI tables documenting removed flags ("--coding-agent — deprecated")
- Test cases that assert the removed behavior is rejected (positive removal tests are fine; sentinel-style "deprecated → error" tests are not — once the flag/code is gone, the absence is the test)

### What stays

- The design doc that authorized the removal — it is the canonical historical record.
- Migration / restoration plans inside that design doc.
- Git commit messages and the git log.
- Tests that exercise the *current* behavior (e.g., a regression guard that the removed flag no longer parses, asserted via Click's default "no such option" error — that is testing the absence, not advertising the deletion).

### Why

Deprecation notices and "for history" pointers turn user-facing surfaces into archaeological digs. New contributors and users encounter mentions of features that do not exist and have to reason about why. The cleanup should be total: after the removal lands, the repository reads as if the removed feature never existed. The historical record lives where it belongs — in git and in the design doc that scoped the change.

### Scope

This rule applies whenever code, options, files, or features are removed. Common triggers:

- Dropping a feature flag entirely
- Removing a CLI subcommand or option
- Deleting a code path / module / class / function
- Renaming with a hard-break (no aliases) — every mention of the old name goes
- Deprecating in v1 and removing in v2 — the v2 removal must complete the cleanup; v1 is the only place a deprecation note should ever live, and only briefly

## Git Workflow

Rules for consistent, clean git commit history across all projects.

- NEVER use HEREDOC syntax for git commit. Always use simple `git commit -m "message"` format
- NEVER use `git -C <path>`. It breaks the harness's command auto-approval matching. The working directory is already the project root, so `-C` is unnecessary
- Commit messages MUST be a single line. Multi-line commit messages are strictly forbidden
- Write commit messages in English, concise and descriptive
- Use conventional commit prefixes: feat, fix, chore, refactor, docs
- NEVER use `git add -f` or `git add --force`. If a file is gitignored, it is gitignored for a reason. Do not force-stage it under any circumstances
- NEVER commit files from `design-docs/` or `researches/` directories. They are gitignored (globally) and must stay out of version control

### Pull requests

- ALWAYS create PRs with `gh pr create --fill`. Use `--title` / `--body-file` ONLY when the user explicitly asks for a custom title or body.

## Bash Commands

Run one command per Bash tool call so that each invocation matches a `permissions.allow` pattern in settings.json. Shell operators break pattern matching and trigger approval prompts that block work.

- Run each command as a separate Bash call. NEVER chain commands with `&&`, `||`, or `;`. Pipes (`|`) are allowed
- Run `cd /path/to/dir` as its own Bash call, then run subsequent commands in separate calls. The working directory persists between Bash calls, so `cd /path && command` is never necessary
- Write file output with the Write tool. NEVER use redirects (`>`, `>>`, `<`)
- Pass literal arguments. Use command substitution (`$()` or backticks) only when there is no other way to obtain the value

## Codex Sandbox Network Retries

This section applies only to Codex and its command execution tools.

When a command required for the user's authorized task fails because of sandbox or proxy network restrictions, rerun the same command with `sandbox_permissions: "require_escalated"` and a concise `justification`. Proceed directly through the tool's approval flow so existing `allow` rules can apply and any additional approval can be requested there.

Command `allow` rules and proxy domain permissions are separate controls: an allowed command can still fail during ordinary sandbox execution. Perform the escalated retry before reporting the task as blocked. Keep the retry within the authorized task and preserve the configured network restrictions.
