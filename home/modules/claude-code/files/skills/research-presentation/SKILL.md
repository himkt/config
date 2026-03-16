---
name: research-presentation
description: Create a Slidev presentation and reading transcript from an existing research report folder. Reads report.md and researcher files for context, creates slides using /my-slidev skill and a reading transcript. Takes folder path as argument (e.g., design-docs/topic-name). Do NOT use for research — use /research-report for that.
allowed-tools: Read, Write, Edit, Glob, Grep, Agent
---

# Research Presentation

Create a Slidev presentation and reading transcript from an existing research report folder. The Director spawns Presentation and Transcript agents, reviews their output, and iterates until quality is met.

| Role | Agent (`subagent_type`) | Does | Does NOT | Role definition |
|:--|:--|:--|:--|:--|
| **Director** | Main Claude | Spawn all teammates, review all deliverables, demand revisions | Create slides/transcript, conduct research, modify report | [roles/director.md](roles/director.md) |
| **Presentation** | `general-purpose` | Create Slidev presentation from report using /my-slidev | Invent data, modify report, conduct research | [roles/presentation.md](roles/presentation.md) |
| **Transcript** | `general-purpose` | Create reading transcript with 1:1 slide correspondence | Invent data, modify report, conduct research | [roles/transcript.md](roles/transcript.md) |
| **Visual Reviewer** | `general-purpose` | Capture screenshots/snapshots of all slides using playwright-mcp, identify visual issues including aesthetic quality, report findings to Director | Edit slide.md, modify report, fix issues directly | [roles/visual-reviewer.md](roles/visual-reviewer.md) |

## Architecture

```
User (or chained from /research-report)
 └── Director (main Claude — creates team, spawns agents, reviews deliverables)
       ├── Presentation Agent (general-purpose teammate — creates Slidev slides using /my-slidev)
       ├── Transcript Agent (general-purpose teammate — creates reading transcript)
       └── Visual Reviewer (general-purpose teammate — spawned just-in-time at Step 4 after content review)
```

## Validation Rules

| Condition | Behavior |
|-----------|----------|
| Folder path argument omitted | Error: "Usage: `/research-presentation design-docs/{folder-name}`. Specify the folder containing report.md." |
| `report.md` not found in folder | Error: "No report.md found in `{folder}`. Run `/research-report` first to generate a report." |
| `report.md` exists | Proceed normally |

## Director Process

### Step 0: Validate Input (Director)

Verify the folder path argument is provided and `{folder}/report.md` exists. If not, error with the appropriate message from the Validation Rules above.

### Step 1: Create Team & Spawn Agents (Director)

Create the team and spawn both agents in parallel:

**Presentation Agent spawn prompt:**

```
You are a Presentation Specialist and a teammate in a research team.

Load the slidev skill using: Skill(slidev-plugin:slidev)
Load the my-slidev skill using: Skill(my-slidev)
Read your role definition at: skills/research-presentation/roles/presentation.md

YOUR TASK: Create a Slidev presentation based on the approved research report.
REPORT FILE: {folder}/report.md
RESEARCHER FILES: {folder}/[0-9][0-9]-*.md (for additional context)
LANGUAGE: {detected from report.md}

CITATION RULES: Carry [N] citations from the report into slides. Renumber
sequentially based on first slide appearance. Add References slide(s) at the
end listing only cited sources.

TIMING: Design for a 30–60 minute presentation (~1.5–2 min per content slide).

Save the presentation to: {folder}/slide.md

When complete, send the file path to the Director.
```

**Transcript Agent spawn prompt:**

```
You are a Transcript Specialist and a teammate in a research team.

Read your role definition at: skills/research-presentation/roles/transcript.md

YOUR TASK: Create a reading transcript based on the approved research report.
REPORT FILE: {folder}/report.md
LANGUAGE: {detected from report.md}

Start by drafting a preliminary narration based on the report's section structure.
The Director will send you the finalized slide structure once available for realignment.

Save the transcript to: {folder}/transcript.md

When complete, send the file path to the Director.
```

**Visual Reviewer spawn prompt (spawned just-in-time at Step 4):**

```
You are a Visual Reviewer and a teammate in a research team.

Read your role definition at: skills/research-presentation/roles/visual-reviewer.md

YOUR TASK: Visually verify the rendered Slidev presentation using playwright-mcp browser tools.
SLIDE FILE: {folder}/slide.md
SCREENSHOT DIR: {folder}/screenshots/
SERVER URL: {server_url}

PROCESS:
1. Navigate to the provided SERVER URL to confirm connectivity
2. For each slide: navigate to {server_url}/{slide_number},
   take a screenshot (save to {folder}/screenshots/slide-{N}.png),
   take an accessibility snapshot, check for visual issues

VISUAL ISSUE CATEGORIES: [OVERFLOW], [BROKEN_LAYOUT], [MISSING_CONTENT], [OVERLAP], [EMPTY_SLIDE], [RENDER_ERROR], [TEXT_WRAPPING]

When complete, send your review report to the Director.
```

**Parallelism strategy:** Both agents start in parallel from the approved report. The Presentation Agent builds the slide deck; the Transcript Agent drafts a preliminary narration script based on the report's section structure. Because the slide deck may not be finalized when the Transcript Agent starts, the workflow has two phases:

1. **Initial phase (parallel):** Both agents work independently from the report. The Transcript Agent uses the report's structure as a provisional slide outline.
2. **Alignment phase (after Presentation review):** Once the Director has a finalized slide deck (after Step 2/3 review), the Director sends the finalized slide structure to the Transcript Agent. The Transcript Agent realigns its narration to match the actual slides — adjusting headings, ordering, and content to achieve exact 1:1 correspondence.

### Step 2: Review Slides & Transcript (Director)

Read the output files and review using the tag criteria in [roles/director.md](roles/director.md). See [roles/director.md](roles/director.md) for report modification policy.

### Step 3: Revision Loop (Director)

- Send tagged feedback to the Presentation and/or Transcript agents
- Agents revise and resubmit
- Re-review against the same criteria
- See [roles/director.md](roles/director.md) for revision approach and iteration limits

### Step 4: Visual Review & Fix (Director)

After the content revision loop completes and the Director is satisfied with slide content, perform a visual review of the rendered presentation.

**Phase 1 — Server Startup & Review:**

1. Director starts the Slidev dev server:
   `script -qf /dev/null -c "npx @slidev/cli --open false {folder}/slide.md"` (run_in_background)
2. Director confirms readiness via `mcp__playwright__browser_navigate` to `http://localhost:3030`
   (retry up to 3 times with 3-second waits)
3. Director spawns the Visual Reviewer, passing `http://localhost:3030` as SERVER URL
4. Visual Reviewer captures screenshots and accessibility snapshots for all slides
5. Visual Reviewer sends a structured review report to the Director

**Phase 2 — Fix (if issues found):**

5. Director extracts issues from the report and sends tagged feedback to the Presentation Agent (using visual issue tags: `[OVERFLOW]`, `[BROKEN_LAYOUT]`, `[MISSING_CONTENT]`, `[OVERLAP]`, `[EMPTY_SLIDE]`, `[RENDER_ERROR]`, `[TEXT_WRAPPING]`)
6. Presentation Agent fixes the issues in `slide.md`
7. Director triggers the Visual Reviewer to re-check only the affected slides
8. Repeat Phase 2 up to 2 rounds
9. After 2 rounds, any remaining issues are reported to the user alongside deliverables

**Phase 2 skip:** If the review report shows zero issues, skip directly to Step 5.

### Step 5: Present Deliverables to User (Director)

After the Director approves all deliverables internally, present them to the user:

1. **File paths** — list deliverable files:
   - Slides: `{folder}/slide.md`
   - Transcript: `{folder}/transcript.md`
2. **Slide preview command**: `npx @slidev/cli {folder}/slide.md`
3. **Request for feedback** — explicitly ask the user to review and provide feedback or approve

### Step 6: User Revision Loop (Director)

When the user provides feedback after reviewing the deliverables:

1. **Triage the feedback** — determine which agent(s) need to act:
   - Slides feedback → Presentation Agent
   - Transcript feedback → Transcript Agent
2. **Route feedback** to the relevant agent(s) using the same tag-based format
3. **Agents revise** and send updated deliverables back to you
4. **Visual re-review (conditional):** If the Presentation Agent modified slides, trigger a focused visual re-review of only the changed slides. The Presentation Agent reports which slide numbers it modified when sending fixes back to the Director. The Director passes these slide numbers to the Visual Reviewer for targeted re-check. This re-review follows the same Phase 1-2 pattern from Step 4 but scoped to affected slides only.
5. **Re-review** the changes, then re-present to the user (return to Step 5)

This loop repeats until the user explicitly approves all deliverables.

### Step 7: Finalize & Clean Up (Director)

1. Confirm all final deliverables are saved
2. **Shutdown sequence:**
   1. Send shutdown requests to: Presentation Agent, Transcript Agent, Visual Reviewer
   2. Kill the Slidev dev server background process if still running
   3. Clean up the team

**Cleanup notes**: Shut down all teammates before cleaning up the team. Kill the Slidev dev server background task if still running. Check `tmux ls` for teammate orphans (`teammateMode: "tmux"` runs each teammate in a tmux session — this check is unrelated to the Slidev server).

$ARGUMENTS
