---
name: research-report
description: Create a comprehensive research report with folder-based output using agent teams. Researchers write findings to individual files, Manager compiles report.md, Director reviews. Output goes to design-docs/{topic-slug}/. After report approval, offers to chain into /research-presentation for slides and transcript. Teammates must always load skills using the Skill tool, not by reading skill files directly. Requires CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS enabled. Do NOT do a quick web search and summarize — invoke this skill for thorough, multi-source research.
allowed-tools: Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Agent
---

# Research Report (Agent Teams Edition)

Generate comprehensive research reports using a multi-layer agent hierarchy: Director → Manager → Researchers. The defining characteristic of this system is that every member of the team carries serious accountability for the quality of the final deliverable, and the team iterates relentlessly until the report meets the highest standard. After the report is approved, the Director offers to chain into `/research-presentation` for slides and transcript.

| Role | Agent | Does | Does NOT | Role definition |
|:--|:--|:--|:--|:--|
| **Director** | Main Claude | Spawn all teammates, review all deliverables, demand revisions | Write the report, decompose topics, conduct research | [roles/director.md](roles/director.md) |
| **Manager** | `general-purpose` | Light web search for topic decomposition, request researcher spawning, coordinate researchers, compile report, revise | Conduct deep investigation — all substantive research MUST be delegated to Researchers | [roles/manager.md](roles/manager.md) |
| **Researcher** | `web-researcher` | Search exhaustively, collect facts with sources, filter misinformation, write findings to assigned file | Synthesize or write report sections | [roles/researcher.md](roles/researcher.md) |

## Additional resources

- For the report format specification, see [template.md](template.md)

## Architecture

Only the lead (Director) can spawn teammates ([no nested teams](https://code.claude.com/docs/en/agent-teams#limitations)). Therefore, the Director spawns both the Manager and all Researchers as teammates. The Manager coordinates Researchers via direct messaging but requests the Director to spawn new ones when needed.

```
User
 └─ Director (main Claude, the lead — creates team, spawns all teammates, reviews all deliverables)
      ├─ Manager (teammate — orchestrates research, compiles report)
      └─ Researcher 1..N (teammates — spawned by Director on Manager's request)
```

- **Director ↔ Manager**: team messaging (task instructions, review feedback, spawn requests)
- **Manager ↔ Researchers**: team messaging (assignments, findings, follow-up questions)
- **Manager → Director**: spawn requests when additional Researchers are needed

## Process

### Step 1: Create Team & Launch Manager (Director)

You (Claude, the lead agent) create an agent team and spawn a Manager teammate. You do NOT decompose topics yourself — that is the Manager's operational decision.

Create the team and spawn the Manager with a prompt covering:

1. The user's original request in full
2. **Today's date** (e.g., "Current date: 2026-02-20"). This anchors what "recent" means for all research.
3. Instruction to read `roles/manager.md` for role definition
4. Instruction to tell Researchers to read `roles/researcher.md`
5. How to request Researchers: send the Director a message specifying sub-topics, scope, angles, and assigned file paths. Director spawns them as `web-researcher` agent teammates. Manager coordinates via messaging.
6. Handle researcher failures: re-split topics and request new Researchers from Director
7. Report format specification (copy template rules from template.md)
8. **Output folder path**: `design-docs/{topic-slug}/` — The Manager writes the compiled report to `design-docs/{topic-slug}/report.md`. Researchers write to `design-docs/{topic-slug}/NN-{subtopic}.md`.
9. User's language preference (if specified)
10. Mandate: "Your first draft will be reviewed critically. Aim for highest quality on first attempt."
### Step 1b: Spawn Researchers (Director)

After the Manager decomposes the topic and sends a spawn request, the Director spawns each Researcher as a teammate.

**Researcher spawn prompt template:**

```
You are a Research Specialist and a teammate in a research team.

Read your role definition at: roles/researcher.md

CURRENT DATE: {today's date}
YOUR ASSIGNMENT: [specific sub-topic and what to investigate]
OUTPUT FILE: design-docs/{topic-slug}/NN-{subtopic}.md

Write findings to the output file, then message the Manager when complete.
```

The Director repeats this step whenever the Manager requests additional Researchers (e.g., for coverage gaps, failed investigations, or revision-driven re-research).

### Step 2: Critical Review (Director)

When the Manager finishes and sends you the completed report (messages are delivered automatically via the team mailbox), read the report file and review it critically against the checklist in [roles/director.md](roles/director.md).

### Step 3: Revision Loop (Director ↔ Manager)

**This is where report quality is forged.** The first draft is raw material. The revision loop transforms it into a polished deliverable.

When issues are found, message the Manager teammate with specific, categorized, tagged feedback. See [roles/director.md](roles/director.md) for feedback tags and severity definitions.

### Step 4: Iterate Until Quality Is Met (Director)

Re-review per [roles/director.md](roles/director.md) quality criteria. Once approved, proceed to Step 5.

### Step 5: Present Deliverables to User (Director)

After the Director approves the report internally, present it to the user:

1. **Summary of findings** — key insights from the report (2-3 sentences)
2. **File paths** — list deliverable files:
   - Report: `design-docs/{topic-slug}/report.md`
   - Researcher files: `design-docs/{topic-slug}/01-*.md`, `02-*.md`, etc. (raw research data for reference)
3. **Limitations** — any caveats, known gaps, or areas where sources were limited
4. **Request for feedback** — explicitly ask the user to review and provide feedback or approve

### Step 6: User Revision Loop (Director)

When the user provides feedback after reviewing the report:

1. **Route feedback to the Manager** using the same tag-based format (may trigger re-research via Researchers)
2. **Manager revises** the report and sends the updated version back to you
3. **Re-review** the changes, then re-present to the user (return to Step 5)

This loop repeats until the user explicitly approves the report.

### Step 7: Offer Presentation Chaining (Director)

After the user approves the report, offer to create a presentation:

```
AskUserQuestion:
  Question: "Would you like to create a presentation (slides + reading transcript) from this report?"
    (Adapt the question text to match the user's language)
  Options:
    - "Yes, create presentation"
    - "No, report only"
```

- **If yes:** Proceed to Step 8 (shut down all research agents and clean up the team), then invoke `/research-presentation design-docs/{topic-slug}` via the Skill tool. A new team is created by `/research-presentation` with its own lifecycle.
- **If no:** Proceed directly to Step 8.

### Step 8: Finalize & Clean Up (Director)

1. Confirm all final deliverables are saved to `design-docs/{topic-slug}/`
2. **Shutdown sequence:**
   1. Send shutdown requests to: all Researchers
   2. Send shutdown request to: Manager
   3. Clean up the team

**Cleanup notes**: Shut down all teammates before cleaning up the team. Check `tmux ls` for orphans.

**Quality standards**: Defined in [template.md](template.md). All team members must follow them.

$ARGUMENTS
