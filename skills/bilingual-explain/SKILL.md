---
name: bilingual-explain
description: >
  Format responses for non-native English speakers by using simplified English
  and adding a Japanese explanation of the original message. Use when the user
  invokes /bilingual-explain, or asks for easy English with Japanese notes.
  Applies to the current response and all subsequent responses in the session
  until the user cancels it.
---

# Bilingual Explain

Make responses accessible to non-native English speakers by combining plain
English with a Japanese explanation of the same content.

## When to apply

- User invokes `/bilingual-explain`.
- User explicitly asks for simplified English plus Japanese notes.

Once activated, keep using this format for every subsequent response in the
session until the user asks to stop.

## Response format

Every response must contain two sections, in this order.

### Section 1: Plain English

- Use short sentences. Aim for under 15 words per sentence.
- Prefer common, everyday words. Avoid idioms, phrasal verbs, and rare jargon.
- When a technical term is unavoidable, keep it in English and add a short
  gloss in parentheses on first use.
- Use active voice. Be direct.
- Use bullet points for lists and steps when they improve clarity.

### Section 2: Japanese explanation

- Start this section with the heading `## 日本語での説明`.
- Explain the same content in natural Japanese. This is an explanation, not a
  literal translation. Rephrase freely when that makes the meaning clearer.
- Keep technical terms (API names, code identifiers, library names) in their
  original English form. Do not translate code or identifiers.
- Use polite form (です・ます調) by default.
- When the English section shows a command, file path, or code snippet, repeat
  the same literal value in the Japanese section. Do not localize it.

## Content rules

- Both sections must cover the same information. Do not introduce new facts in
  one that are missing from the other.
- Keep the two sections consistent. If you correct a mistake in one, correct
  it in the other.
- Show code blocks, file paths, and command examples once per section, in
  their original form.
- Length guidance from the main system prompt still applies. Count the two
  sections together when judging length. Do not double the budget.

## Example output

User asks: "How do I list files changed in the last commit?"

> ### Plain English
>
> Run `git show --name-only HEAD`. This shows the files changed in the most
> recent commit. Use `--stat` instead of `--name-only` if you also want line
> counts.
>
> ### 日本語での説明
>
> `git show --name-only HEAD` を実行すると、直前のコミットで変更された
> ファイルの一覧が表示されます。変更行数も確認したい場合は `--name-only` の
> 代わりに `--stat` を使ってください。

## Stopping

If the user says "stop", "cancel", "plain only", or any similar request,
return to the normal single-language response format.
