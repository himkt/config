# English Review Output Format

Canonical specification for English-review output. Used by the
`english-review` skill (manual invocation) and by the Stop-hook reviewer at
`bin/english_review.py`. Keep this file as the single source of truth — if you
change the format, both consumers pick it up automatically.

## Review criteria

Evaluate the text against all of the following, in roughly this priority order:

1. **Grammar and syntax** — article use, agreement, tense, pluralization,
   prepositions, sentence structure.
2. **Naturalness and idiomatic phrasing** — would a fluent speaker say it this
   way? Flag literal translations and non-native collocations.
3. **Word choice and precision** — is there a sharper, more specific, or more
   appropriate word? Watch register (too casual / too stiff for the context).
4. **Clarity and concision** — trim filler, resolve ambiguous references,
   prefer concrete over vague.
5. **Sophistication** — even when the text is already correct, suggest
   upgrades: stronger verbs, varied sentence openers, parallel structure,
   cohesion markers, tone calibration. This dimension is important and must
   not be skipped when the text supports it.

## Output shape

```
score: N / 10

### <original passage> -> <improved passage>

- <concise reason 1>
- <concise reason 2>

### <another original passage> -> <another improved passage>

- <reason>
```

## Rules

- The very first line is `score: N / 10`, where `N` is an integer 1–10:
  - 1–3: hard to parse, many errors.
  - 4–6: understandable but clearly non-native, frequent issues.
  - 7–8: fluent with occasional awkwardness.
  - 9–10: native-like, polished.
- One blank line after the score, then one `###` section per revision.
- In each heading, quote the **original passage verbatim** on the left, then
  ` -> ` (space, ASCII hyphen, greater-than, space), then the improved version.
- Under each heading, give 1–3 short bullet reasons. One idea per bullet. No
  nested lists, no paragraphs.
- Do **not** wrap passages in backticks, quotes, or code fences.
- Cover a mix of issues. When the text supports it, include at least one
  section that is a **sophistication upgrade** (style, tone, variety), not
  merely a grammar correction.
- No preamble, no headers above `###`, no closing remarks, no summary.
- Do not invent passages that are not in the source text.

## Example

Input (user-authored text):

> i wanna improve english. this is points i want to work on.

Output:

```
score: 5 / 10

### i wanna improve english -> I want to improve my English

- `wanna` is too casual for written text; `want to` fits a broader register.
- `english` is a proper noun and must be capitalized.
- A possessive (`my`) is needed before `English` when referring to your own skill.

### this is points -> these are the points

- `points` is plural, so the verb and determiner must agree: `these are`.
- Add `the` to point to a specific, known set.

### i want to work on -> I'd like to focus on

- `I'd like to` softens the tone and sounds less mechanical in prose.
- `focus on` is a sharper, more idiomatic verb than `work on` for this context.
```
