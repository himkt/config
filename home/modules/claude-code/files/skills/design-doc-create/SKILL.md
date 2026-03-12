---
name: design-doc-create
description: Create a new design document using the design-doc-creator agent. Use when user wants to create a specification, implementation plan, or technical document. Teammates must always load skills using the Skill tool, not by reading skill files directly. Do NOT use EnterPlanMode — always invoke this skill instead.
allowed-tools: Read, Write, Edit, Glob, Grep, Agent, WebSearch, WebFetch
---

# Design Doc Create (Agent Teams Edition)

Create high-quality design documents using a three-role agent team: Director (orchestrator), Drafter (writes the document), and Reviewer (critically reviews drafts). The team iterates through an internal quality loop before presenting a polished draft to the user.

| Role | Agent | Does | Does NOT | Role definition |
|:--|:--|:--|:--|:--|
| **Director** | Main Claude | Spawn teammates, relay user answers, enforce clarification gate, orchestrate internal quality loop, present polished draft to user | Write the document, review it in detail | [roles/director.md](roles/director.md) |
| **Drafter** | `design-doc-creator` | Ask clarifying questions (via Director relay), read target codebase, write and revise the design document | Communicate with user directly (goes through Director), review own work | [roles/drafter.md](roles/drafter.md) |
| **Reviewer** | `general-purpose` | Critically review drafts for rule compliance, readability, completeness, correctness | Write the document, communicate with user | [roles/reviewer.md](roles/reviewer.md) |

## Additional resources

- For the document template, see /design-doc: [template.md](../design-doc/template.md)
- For section guidelines and quality standards, see: [guidelines.md](../design-doc/guidelines.md)

## Architecture

Only the lead (Director) can spawn teammates (no nested teams). The Director spawns both the Drafter and Reviewer as teammates.

```
User
 +-- Director (main Claude -- creates team, relays user input, orchestrates the cycle)
      +-- Drafter (teammate -- design-doc-creator agent, writes the design document)
      +-- Reviewer (teammate -- general-purpose agent, critically reviews the draft)
```

- **Director <-> User**: AskUserQuestion (clarification relay, draft presentation, feedback collection)
- **Director <-> Drafter**: team messaging (questions relay, user answers, reviewer feedback, drafting instructions)
- **Director <-> Reviewer**: team messaging (draft review requests, review feedback)

## Process

### Step 0: Resume Detection (Director)

`$ARGUMENTS` is the full file path (e.g., `design-docs/xxx/design-doc.md`). Check file existence directly — no normalization needed.

1. **File does not exist** → Fresh creation (proceed to Step 1 as normal).
2. **File exists** → Check for COMMENT markers:
   - Use Grep to search for `COMMENT(` in the file.
   - **COMMENT markers found** → This is **resume mode**. Proceed to Step 1 with resume-specific Drafter spawn prompt. Set an internal flag so Step 2 (clarification) is skipped.
   - **No COMMENT markers found** → Inform the user: "No COMMENT markers found in the existing document." Use `AskUserQuestion` with two options:
     - **"Run quality review"**: Run the Reviewer on the existing document (spawn Reviewer, route the document for review, then enter the quality loop at Step 3).
     - **"Start fresh"**: Treat as new creation, ignoring the existing file (proceed to Step 1 as normal).

### Step 1: Create Team & Spawn Teammates (Director)

Create an agent team and spawn both the Drafter and Reviewer.

**Drafter spawn prompt:**

```
You are the Drafter in a design document creation team.

Load the design-doc skill using: Skill(design-doc)
Read your role definition at: roles/drafter.md

IMPORTANT: You MUST ask clarifying questions BEFORE writing any design document file.
Send your questions to the Director who will relay them to the user.

OUTPUT PATH: [INSERT $ARGUMENTS HERE]

The user's request: [INSERT USER'S ORIGINAL REQUEST HERE]

Start by reading the target codebase for context, then send your clarifying questions
to the Director. Do NOT create any design document file until you have received answers.
```

**Drafter spawn prompt (resume mode):**

When Step 0 detected resume mode, use this prompt instead of the standard Drafter spawn prompt:

```
You are the Drafter in a design document creation team (RESUME MODE).

Load the design-doc skill using: Skill(design-doc)
Read your role definition at: roles/drafter.md

DESIGN DOCUMENT: [INSERT DOC PATH]

This is a RESUME session. The document contains COMMENT markers from a previous
interview. Follow the Resume Mode instructions in your role definition.
Do NOT ask clarifying questions — the COMMENTs contain the needed information.
Start by reading the design document.
```

**Reviewer spawn prompt:**

```
You are the Reviewer in a design document creation team.

Load the design-doc skill using: Skill(design-doc)
Read your role definition at: roles/reviewer.md

Read the document file and provide specific, actionable feedback.
If the draft meets all quality standards, signal: "APPROVED - Ready for user review."
```

### Step 2: Clarification Phase (Director)

**Resume mode**: Skip this step entirely. In resume mode, the COMMENT markers serve as the clarification — the Drafter already has all the information needed. Proceed directly to Step 3 after the Drafter reports its changes.

1. Wait for the Drafter's clarifying questions. Relay to the user via AskUserQuestion, then relay answers back.
2. **Gate check**: If the Drafter produces a draft without prior questions, reject it and instruct them to ask first. A focused confirmation round counts as valid clarification.

### Step 3: Internal Quality Loop (Director)

After the Drafter produces a draft:

1. **Route to Reviewer** with the document path for critical review.
2. **On feedback**: Route to Drafter for revision, then back to Reviewer. Repeat until Reviewer signals "APPROVED".
3. **Iteration limit**: Aim for 2-3 rounds. If not converging, proceed to user presentation with a note about remaining issues.

### Step 4: Present to User (Director)

Once the Reviewer approves, present a summary (including file path) and use `AskUserQuestion`:

| Option | Label | Description | Behavior |
|:--|:--|:--|:--|
| 1 | **Approve** | Proceed with the current result | Proceed to finalization (Step 6) |
| 2 | **Scan for COMMENT markers** | Add `COMMENT(name): feedback` markers to the design document, then select this option to process them | Scan and process markers (see Step 5) |
| 3 | *(Other — built-in)* | *(Free text input)* | Interpret user intent (see Step 5) |

See [roles/director.md](roles/director.md) for user interaction rules (COMMENT handling, intent judgment, abort detection).

### Step 5: User Feedback Loop (Director)

Process the user's selection per the rules in [roles/director.md](roles/director.md):
- **"Scan for COMMENT markers"**: Scan, route to Drafter if found, explain convention if not. After fixes, re-enter quality loop (Step 3) then re-present (Step 4).
- **"Other" (free text)**: Interpret intent per director.md rules.

No round limit — loop continues until approved or aborted.

### Step 6: Finalize & Clean Up (Director)

1. Instruct the Drafter to finalize (update Status, verify steps are actionable).
2. Shut down all teammates, then clean up the team.

**Cleanup notes**: Shut down all teammates before cleaning up the team. Check `tmux ls` for orphans.

$ARGUMENTS
