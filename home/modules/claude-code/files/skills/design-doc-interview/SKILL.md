---
name: design-doc-interview
description: >-
  Validate a design document through fine-grained multi-question Q&A across multiple sessions.
  Adds COMMENT(claude) annotations for discrepancies found.
  Supports multi-session splitting for large documents.
  Use after /design-doc-create and before /design-doc-execute.
  Takes document path as argument.
  Do NOT use this to create or execute design documents — use the dedicated skills instead.
allowed-tools: Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent
---

# Design Doc Interview

Validate a design document through structured, fine-grained Q&A across multiple sessions. The Interviewer (main Claude) drives the conversation, while an Analyzer subagent (Explore type via Agent tool) handles document analysis and question generation. Discrepancies produce inline `COMMENT(claude)` annotations. Multi-session splitting prevents context compaction for large interviews.

| Aspect | Detail |
|:--|:--|
| **Interviewer** | Main Claude — orchestrates session, drives Q&A, annotates findings |
| **Analyzer** | Subagent (Explore type via Agent tool) — reads document, generates question list |
| **Input** | Design document path (required argument via `$ARGUMENTS`) |
| **Output** | Inline `# COMMENT(claude)` annotations, progress update, session report |
| **Interaction** | ALL Analyzer questions asked via `AskUserQuestion` (4 per call, minimized rounds) |
| **Scale** | All Analyzer questions asked — up to 100 across multiple sessions |
| **Allowed tools** | Read, Write, Edit, Glob, Grep, AskUserQuestion, Agent |

## Context Management Strategy

Two mechanisms prevent context compaction:

1. **Subagent offloading**: The Analyzer subagent performs the heavy document analysis (reading, reasoning, question generation) and returns only a compact question list. This keeps the main context clean.
2. **Multi-session splitting**: Each invocation covers a batch of sections. The Interviewer tracks progress via `question.md` in the design document's directory, so subsequent sessions skip already-reviewed sections.

## Interview Progress Tracking

Progress is tracked via `question.md` in the design document's directory (e.g., `design-docs/xxx/question.md`):

```html
<!-- interview-progress: ["Overview", "Success Criteria", "Specification/Retry Strategy"] -->
```

- The `<!-- interview-progress: [...] -->` HTML comment is at the top of `question.md` (not in the design document).
- Contains a JSON array of section headings that have been reviewed (whether clean or with issues).
- Created when `question.md` is first written (after the Analyzer returns questions).
- Appended on subsequent sessions.
- Removed when all sections are covered (final session). If `question.md` exists but the marker is absent, the interview is considered complete.
- The Interviewer reads this to determine resume state.

## Process

### Step 1: Load, Validate & Check Progress

1. Set `doc_path = $ARGUMENTS` (e.g., `design-docs/xxx/design-doc.md`).
2. Set `dir_path = dirname(doc_path)` (e.g., `design-docs/xxx`).
3. Read the design document at `doc_path`. If missing or empty, report the error and stop.
4. Check if `{dir_path}/question.md` exists:
   a. If yes → parse `interview-progress` from `question.md`. If the marker is absent, the interview is already complete — report completion and stop. If the marker is present, proceed to Step 1.5 (resume mode).
   b. If no → fresh start (proceed to Step 2).
5. In resume mode:
   a. Parse the already-reviewed sections from `interview-progress`.
   b. Parse already-answered questions from the Answers section.
   c. Parse remaining unanswered questions from the Questions section.
   d. If all sections covered → report completion, suggest next step, stop.
   e. Else if there are remaining unanswered questions in the Questions section → skip Step 2, proceed to Step 3 with those remaining questions.
   f. Else (no remaining unanswered questions, but not all sections covered) → proceed to Step 2 to generate a new batch of questions for the next uncovered sections.

### Step 2: Analyze Document (Subagent)

Spawn an Analyzer subagent (Explore type via Agent tool) with:

- The design document path
- The list of already-reviewed sections (if any)
- Instructions to generate fine-grained questions for **uncovered sections only**

**Analyzer prompt:**

```
Read the design document at [DOC PATH].

Already-reviewed sections (skip these): [LIST OR "none"]

Generate a prioritized list of fine-grained validation questions for the uncovered sections.
For each question, provide:
- The target section heading
- The question text
- 2-4 suggested answer options (when clear alternatives exist)

Question categories to cover:

| Category | What to look for |
|:--|:--|
| Intent alignment | Does the Overview/Specification match what a reasonable user would expect? |
| Ambiguity | Sections that could be interpreted multiple ways |
| Missing requirements | Gaps in error handling, edge cases, or constraints |
| Implicit assumptions | Undocumented assumptions about dependencies, environment, or behavior |
| Design decisions | Choices that could reasonably go a different way |
| Internal consistency | Contradictions between sections |
| Implementation actionability | Steps that are vague or underspecified |

Priority order: intent confirmation first (for first session only), then ambiguous/risky areas,
implicit assumptions, missing requirements, design challenges, implementation clarity.

Output format:
- Return a flat numbered list: `1. [Section: ...] Question text | Options: A) ... B) ... C) ...`
- End with a total count line: `Total: N questions`
- Do NOT group or batch questions — return a single flat list
- Every question MUST have a number, target section, question text, and 2-4 options

Be thorough and fine-grained — aim for detailed coverage. Up to 100 questions total across
all sessions. Return ONLY the question list in a structured format.
```

The Analyzer returns a numbered question list with a total count. The Interviewer MUST ask every question on this list — no filtering, no skipping, no summarizing multiple questions into one.

After the Analyzer returns the question list, write or update `{dir_path}/question.md`:

**Fresh start** (file does not exist): Create `question.md` with:

```markdown
<!-- interview-progress: [] -->

## Questions

1. [Section: ...] Question text | Options: A) ... B) ...
2. ...

## Answers
```

The `interview-progress` starts as an empty array. The Questions section contains a verbatim copy of the Analyzer's full numbered list. The Answers section is initially empty.

**Resume mode** (Step 1.5.f — file already exists): Do NOT overwrite the file. Append the new questions to the end of the existing Questions list, continuing the numbering from the last existing question (e.g., if the last question is #20, start the new batch at #21). This preserves prior Answers, progress, and stable question numbers for Step 3.

### Step 3: Interview Loop (Explicit Round Counter)

After receiving the Analyzer's question list, the Interviewer executes a deterministic loop:

**Pre-loop setup:**

1. Parse the Analyzer's numbered question list
2. Count total questions: `N`
3. Calculate total rounds: `total_rounds = ceil(N / 4)`
4. Log: `"Starting interview: N questions, total_rounds rounds"`

**Loop: for round = 1 to total_rounds:**

1. Take the next batch of up to 4 questions from the list (questions `(round-1)*4+1` through `min(round*4, N)`)
2. Call `AskUserQuestion` with the batch, grouped by related topic when possible
3. Each question has 2-4 answer options tailored to the question
4. After the user responds:
   a. Append the round's answers to `question.md`'s Answers section under a `### Round X (Questions Y-Z)` heading
   b. Record any discrepancies found (section, current text, what needs to change)
5. Log: `"Completed round X of total_rounds (Y of N questions asked)"`
6. Continue to the next round

**Mandatory completion rule (NON-NEGOTIABLE):**

> The Interviewer MUST complete all rounds. Stopping before all questions are asked is FORBIDDEN. The only exception is if the user explicitly requests early exit via the built-in "Other" option on any question. In that case, proceed directly to Step 4 with the answers collected so far.

**There is no "End interview" option.** The user can always use the built-in "Other" free-text option on any question to request early termination.

Example `AskUserQuestion` call (Round 2 of 5):

```
questions:
  - question: "The Specification says maximum retries is 3. Is that the correct limit?"
    options:
      - label: "3 is correct"
      - label: "Should be 5"
  - question: "Should failed requests be logged for debugging?"
    options:
      - label: "Log all failures"
      - label: "Log only final failure"
```

**Session termination:**

| Condition | Next action |
|:--|:--|
| All rounds completed (round = total_rounds) | Proceed to Step 4 |
| User requests early exit via "Other" | Proceed to Step 4 with answers collected so far |

### Step 4: Annotate & Update Progress

1. **Annotate discrepancies**: For each discrepancy found, add a `COMMENT(claude): ...` annotation inline in the design document, immediately before the relevant content. Use `Edit` to insert each annotation.
2. **Update progress in question.md**: Append the reviewed section headings to the `<!-- interview-progress: [...] -->` marker in `question.md` (NOT in the design document).
3. **If final session** (all sections covered): Remove the `<!-- interview-progress: [...] -->` marker from `question.md`.
4. **Verify**: Grep to confirm all intended annotations were written in the design document.

### Step 5: Session Report

Present a session summary to the user:

| Field | Content |
|:--|:--|
| **Sections reviewed** | List of sections covered in this session |
| **Discrepancies found** | Count and brief list of each COMMENT added |
| **Sections remaining** | List of sections not yet reviewed |
| **Next step** | See decision table below |

**Next step decision:**

| State | Suggested next step |
|:--|:--|
| Sections remain, COMMENT markers present in document | Re-invoke `/design-doc-interview <doc-path>` for the next session |
| Sections remain, no COMMENT markers in document | Re-invoke `/design-doc-interview <doc-path>` for the next session |
| All sections covered, COMMENT markers present in document | Run `/design-doc-create <doc-path>` to fix annotations, then `/design-doc-execute` |
| All sections covered, no COMMENT markers in document | Run `/design-doc-execute <doc-path>` to implement |

## COMMENT Annotation Format

Annotations are plain text inserted inline in the markdown document, immediately before the content they refer to:

```markdown
## Specification

COMMENT(claude): User confirmed the retry limit should be 5, not 3. Update the retry count and adjust the timeout calculation that depends on it.

### Retry Strategy

Maximum retries: 3 with exponential backoff...
```

Rules:

- Format: `COMMENT(claude): <description of discrepancy and what needs to change>`
- Placement: immediately before the relevant content, on its own line
- One COMMENT per discrepancy (do not combine unrelated issues)
- Description must be actionable — state what is wrong AND what the correct behavior should be

$ARGUMENTS
