# Affirmative Writing

Say what should happen. In prose, prescribe the desired behavior directly. In code, assert the expected invariant and fail loudly when it is violated. A document is a clean specification of intended behavior, not a pile of reactive "do not" patches; a program states its assumptions and stops when they break, instead of masking a violation with a meaningless fallback value.

This is not a ban on the words "never" or "do not", nor on defaults. A prohibition is the right tool when it is the clearest way to state a genuine hard constraint — and it is strongest paired with the affirmative instruction it enforces ("always use X" alongside "never use Y"). A default is the right tool when absence is an expected, valid state with a well-defined correct behavior. The anti-pattern is the *reactive residue*: a prohibition bolted on in place of a missing positive spec, or a fallback bolted on in place of a missing invariant check.

## Documentation: prescribe the desired behavior

Lead with what the reader should do and what correct looks like; let the prohibitions fall out of the positive specification. When a hard constraint genuinely needs a prohibition, state it — and pair it with the affirmative.

### Forbidden patterns

- A section that is only a list of "DO NOT X / NEVER Y" bullets, with no statement of the desired behavior the don'ts protect.
- A new "don't do Z" appended each time something goes wrong, instead of revising the positive spec so Z is no longer the natural reading.
- A prohibition with no affirmative counterpart, leaving the reader to infer what they should do instead.

### What's legitimate

- Strong negative phrasing for a genuine hard constraint, paired with the positive instruction — e.g. "NEVER use HEREDOC for git commit; always use `git commit -m`".
- A short "Forbidden patterns" / "anti-patterns" list that *complements* a positive spec (as in this file and in `removal.md`), rather than substituting for one.

## Code: fail fast

When an expected condition is violated, raise (or assert) at the point of violation. Do not substitute a meaningless sentinel or default that lets corrupt state flow downstream, where the real failure surfaces far from its cause and is far harder to diagnose.

### Forbidden patterns

- Silent sentinels for a violated invariant: `rate = total / count if count else 1`; `value = lookup.get(key) or 0`; `user = users.get(uid, AnonymousUser())` where `uid` is required to exist.
- A `try/except` that swallows the error and returns a placeholder, hiding a condition the caller needed to know about.
- Coercing a missing *required* input to an empty/zero/default value instead of raising.

### What's legitimate

- A default that *is* the correct behavior, where absence is an expected, valid state — e.g. `retries = config.get("retries", 3)` with 3 a documented, sensible default.
- Catching an exception you can genuinely recover from, and re-raising (or raising a clearer error for) the ones you cannot.
- An `assert`/`raise` guarding a "can't happen" invariant — the loud failure is the point.

The test: a fallback is legitimate when absence or variation is an expected, well-specified case; it is error-swallowing when absence signals a bug or corrupt state and the fallback merely hides it.

## Why

Affirmative documentation tells a reader what to do in one read; a wall of prohibitions forces them to reverse-engineer the intent from the don'ts. Fail-fast code surfaces a bug at its source; an error-swallowing fallback ships the bug downstream as corrupt state. Both failures share one root: writing the reaction to the bad case instead of the intended good case. This is the same principle as `removal.md` — after a change, the artifact should read as a clean statement of the current, intended state, with no reactive negative residue (deprecation notices, ad-hoc prohibitions, or silent fallbacks) left behind.

## Scope

Applies across all projects, whenever you write or edit documentation or code:

- Authoring or revising docs, READMEs, skills, rules, and comments — prefer the positive spec.
- Writing code that reads configuration, looks up a key, divides, parses, or otherwise depends on an invariant — assert or raise rather than fall back to a meaningless value.
- Reviewing or refactoring — when you find a reactive prohibition or an error-swallowing fallback, replace it with the affirmative spec or the explicit failure.
