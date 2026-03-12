---
name: design-doc-execute
description: Implement features based on a design document with automatic validation and fixing. Use when the user asks to implement or execute a design document. Takes document path as argument. Teammates must always load skills using the Skill tool, not by reading skill files directly. Do NOT implement a design document by reading it and coding manually — always invoke this skill instead.
allowed-tools: Read, Write, Edit, Glob, Grep, Bash, Agent, WebSearch, WebFetch
---

# Design Doc Execute (Agent Teams Edition)

Implement features based on a design document using up to four roles: Director (orchestrator), Programmer (implements), Tester (writes tests), and Verifier (E2E/integration testing). The Director judges which teammates to spawn based on the nature of the implementation tasks. For each step, the Tester writes unit tests first, the Director reviews and approves them, then the Programmer implements code to pass the tests. The Director also reviews the Programmer's implementation for code quality and design doc compliance before committing. After all TDD steps, the Verifier performs E2E/integration verification (Phase D) if spawned.

| Role | Agent | Does | Does NOT | Role definition |
|:--|:--|:--|:--|:--|
| **Director** | Main Claude | Spawn teammates, validate doc, assign steps, review tests against design doc, review implementation code for quality and compliance, commit after each phase, escalation arbitration, orchestrate TDD cycle | Write code, write tests | [roles/director.md](roles/director.md) |
| **Programmer** | `design-doc-executor` | Implement code to pass tests, run tests, report results, escalate test defects to Director, update design doc checkboxes and Progress counter | Write or modify tests, commit code, communicate with user directly | [roles/programmer.md](roles/programmer.md) |
| **Tester** | `design-doc-tester` | Read design doc, write unit tests per step, fix tests based on Director feedback, report to Director | Write implementation code, commit code, communicate with user directly | [roles/tester.md](roles/tester.md) |
| **Verifier** | `design-doc-verifier` | E2E/integration testing, tool discovery, evidence collection (screenshots, logs, output), failure reporting with suggested fixes | Write code, write tests, commit, communicate with user directly | [roles/verifier.md](roles/verifier.md) |

## Architecture

Only the lead (Director) can spawn teammates (no nested teams). The Director decides which teammates to spawn based on task analysis (see [roles/director.md](roles/director.md)). They work together through each step using a TDD workflow, optionally followed by E2E verification.

```
User
 +-- Director (Main Claude -- creates team, validates doc, assigns steps, reviews tests & code, obtains user approval, commits, orchestrates)
      +-- Programmer (teammate -- design-doc-executor agent, implements code to pass tests)
      +-- Tester (teammate -- design-doc-tester agent, writes unit tests per step)
      +-- Verifier (teammate -- design-doc-verifier agent, E2E/integration testing)
```

- **Director <-> Programmer**: team messaging (step assignments, test results, code review feedback, escalation)
- **Director <-> Tester**: team messaging (step assignments, test review feedback, test defect reports)
- **Director <-> Verifier**: team messaging (verification assignments, results, failure routing)
- **Director**: git operations (commit after each phase — tests and implementation separately)

## Process

### Step 0: Validate Design Document & Create Branch (Director)

Before creating any team:

1. Read the design document completely.
2. Check for `COMMENT(` markers using Grep. If found, resolve them directly: apply the requested changes and remove the markers. Verify with Grep that no `COMMENT(` markers remain before proceeding.
3. Check for `FIXME(claude)` markers in the codebase using Grep. If found, note them for the Programmer to resolve first.
4. Determine the step order and total number of steps.
5. **Create a feature branch if on the default branch.** Get the default branch with `gh repo view --json defaultBranchRef --jq '.defaultBranchRef.name'` and the current branch with `git branch --show-current`. If they match, use `AskUserQuestion` to propose the branch name `feat/<design-doc-slug>` and ask the user to approve before creating it. The user will create the branch themselves or approve the proposed name. If already on a non-default branch, skip this step.

### Step 1: Create Team & Spawn Teammates (Director)

Create an agent team and spawn the teammates needed for this project. Analyze the implementation tasks to decide which roles to spawn (see [roles/director.md](roles/director.md) for team composition guidelines).

**Programmer spawn prompt:**

```
You are the Programmer in a design document execution team.

Load the design-doc skill using: Skill(design-doc)
Read your role definition at: roles/programmer.md

DESIGN DOCUMENT: [INSERT DESIGN DOC PATH]

IMPORTANT: Do NOT commit code yourself. The Director handles all git operations.
IMPORTANT: If blocked, message the Director immediately instead of assuming.
IMPORTANT: Read and follow rules/bash-command.md for all Bash commands.

Start by reading the design document. Then wait for the Director to assign your first step.
```

**Tester spawn prompt:**

```
You are the Tester in a design document execution team.

Load the design-doc skill using: Skill(design-doc)
Read your role definition at: roles/tester.md

DESIGN DOCUMENT: [INSERT DESIGN DOC PATH]

IMPORTANT: Do NOT commit code yourself. The Director handles all git operations.
IMPORTANT: Do NOT write implementation code — only test code.
IMPORTANT: If blocked, message the Director immediately instead of assuming.
IMPORTANT: Read and follow rules/bash-command.md for all Bash commands.

Start by reading the design document. Then wait for the Director to assign your first step.
```

**Verifier spawn prompt:**

```
You are the Verifier in a design document execution team.

Load the design-doc skill using: Skill(design-doc)
Read your role definition at: roles/verifier.md

DESIGN DOCUMENT: [INSERT DESIGN DOC PATH]

IMPORTANT: Do NOT commit code or modify implementation/test files.
IMPORTANT: If blocked, message the Director immediately instead of assuming.
IMPORTANT: Read and follow rules/bash-command.md for all Bash commands.

Start by reading the design document and discovering available tools.
Then wait for the Director to assign your first verification task.
```

See [roles/director.md](roles/director.md) for commit message conventions.

### Step 2: Execute Steps with Per-Step TDD Cycle (Director)

For each step in the design document:

#### Phase A: Test Writing

1. **Assign**: Message the Tester with the step number, description, and specification.
2. **Wait for Tester**: Tester reads spec, writes tests, reports. If test framework is ambiguous, ask user via `AskUserQuestion` and relay.
3. **Review tests** against the design doc. Send feedback until satisfied.
4. **Commit tests** (separate commands, do NOT chain with `&&`):
   - `git add <test-files>`
   - `git commit -m "test: add tests for [feature description]"`

#### Phase B: Implementation

1. **Assign**: Message the Programmer with step number, description, and test file paths.
2. **Wait for Programmer**: Programmer implements, runs tests, reports. On suspected test defect, see [roles/director.md](roles/director.md) for the escalation protocol.
3. **Programmer updates design doc**: Checkboxes, timestamps, and Progress counter.

#### Phase C: Code Review (Director)

1. **Review**: Verify code matches design doc, quality is acceptable, no unnecessary changes.
2. **Feedback loop**: Send feedback if issues found. Programmer fixes, re-runs tests, re-reports. Repeat until satisfied.
3. **Commit implementation** (separate commands, do NOT chain with `&&`):
   - `git add <files> <design-doc>`
   - `git commit -m "feat: [description of what was implemented]"`

Repeat from Phase A for the next step. Always include the design document in the implementation commit.

**On-Demand Verification**: Any teammate can request verification mid-task via the Director. The Director decides whether to route immediately or defer:

| Route immediately | Defer to Phase D |
|:--|:--|
| User-visible behavior change (UI, CLI output, API response) | Internal refactoring or data model change |
| Integration with external system | Adequately covered by unit tests |
| Behavior difficult to catch with unit tests alone | Verification requires setup from a later step |

### Phase D: Verification (Director) — conditional

**Skip this phase entirely if the Verifier was not spawned.** Proceed directly to Step 3 (User Approval).

If the Verifier was spawned, assign verification:

1. Send the Verifier the design document, completed steps, and relevant files.
2. Verifier discovers tools, executes E2E verification, captures evidence, reports results.
3. **Route failures**: Implementation bugs → Programmer, test gaps → Tester, spec issues → user.
4. Re-verify after fixes. Proceed to User Approval when all verifiable criteria pass.

### Step 3: User Approval (Director)

After all TDD steps complete but before finalization, present the implementation to the user for approval.

#### Change Presentation

1. **Git diff command** for the user to inspect (e.g., `git diff main...HEAD`).
2. **Step-by-step change summary** — concise prose of what changed per step (files modified, key behaviors).

#### Approval Interaction

Use `AskUserQuestion`:

| Option | Label | Description | Behavior |
|:--|:--|:--|:--|
| 1 | **Approve** | Proceed with the current result | Proceed to finalization (Step 4) |
| 2 | **Scan for COMMENT markers** | Add `COMMENT(name): feedback` markers to the changed source files, then select this option to process them | Scan and process markers (see Revision Loop below) |
| 3 | *(Other — built-in)* | *(Free text input)* | Interpret user intent (see Revision Loop below) |

See [roles/director.md](roles/director.md) for user interaction rules (COMMENT handling, classification, intent judgment, abort detection).

#### Revision Loop (COMMENT Marker-Based Feedback)

When the user selects "Scan for COMMENT markers": scan changed files for `COMMENT(` markers. Classify by file location (see [roles/director.md](roles/director.md)) and route: design doc COMMENTs → Director resolves directly; source file → Programmer; test file → Tester. After all COMMENTs are resolved and verified, re-present to user.

When the user selects "Other": interpret intent per [roles/director.md](roles/director.md) rules.

No round limit — the loop continues until the user approves or aborts.

#### Abort Flow

1. Update design document Status to "Aborted", add Changelog entry.
2. Commit (separate commands): `git add <design-doc>` then `git commit -m "docs: mark design doc as aborted"`
3. Shut down teammates and clean up the team.

### Step 4: Finalize & Clean Up (Director)

1. Update design document Status to "Complete" and add final Changelog entry.
2. Commit (separate commands): `git add <design-doc>` then `git commit -m "docs: mark design doc as complete"`
3. Shut down all teammates, then clean up the team.

**Cleanup notes**: Shut down all teammates before cleaning up the team. Check `tmux ls` for orphans.

$ARGUMENTS
