## Skills

The system-reminder lists each skill with a `description` stating when to invoke it — the description is the authoritative trigger source. Before acting on the user's request, scan the descriptions and match against the user's literal phrasing and the kind of task. If a description matches, invoke it — do NOT bypass with Write/Edit/Bash. When a match is uncertain, invoke rather than skip.

> **EMERGENCY RULE (MUST follow):**
> If the system-reminder does NOT contain the skill list, something is internally broken.
> Do NOT proceed with any work. Immediately terminate the conversation and notify the user that an emergency has occurred
> (skills failed to load). Proceeding without skills loaded would cause catastrophic failures.
