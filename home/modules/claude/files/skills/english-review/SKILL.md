---
name: english-review
description: >
  Review the user's English writing and produce structured feedback with a
  fluency score, passage-level revisions, and sophistication suggestions that
  go beyond simple grammar fixes. Use when the user invokes /english-review,
  asks to review or polish their English, or asks for feedback on chat
  messages, commit messages, or prose they have written. This is also the
  canonical format used by the Stop-hook English reviewer.
---

# English Review

Help the user write more polished, natural, and sophisticated English.
Grammar correctness is the floor, not the ceiling — always look for stylistic
and idiomatic upgrades, not just errors.

## How to run a review

1. Identify the target text:
   - If the user invokes `/english-review` with no argument, review the most
     recent English text they have written in the current conversation.
   - If they paste text or reference a file, review that instead.
2. Read `format.md` in this skill's directory. It defines the review criteria,
   output shape, formatting rules, and a worked example.
3. Produce output that follows `format.md` exactly. Do not restate or
   paraphrase the rules in your response — just emit the formatted output.

## When the text has nothing to review

If the target text contains no English content worth reviewing (entirely in
another language, or only trivial greetings), say so in one plain sentence
instead of forcing the template.

## Notes for maintainers

- `format.md` is the single source of truth for the output format.
- The Stop-hook reviewer at `bin/english_review.py` reads `format.md` at
  runtime and injects it into its prompt, so updating `format.md` keeps both
  consumers in sync automatically.
