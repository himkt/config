# Bash Command

Rules to ensure Bash commands match `permissions.allow` patterns in settings.json.
Using shell operators breaks pattern matching and triggers user approval prompts that block work.

- NEVER use `&&` or `;` to chain commands. Each command must be a separate Bash tool call. Pipes (`|`) are allowed
- **ESPECIALLY NEVER `cd /path && command`** — this is the single most common violation. `cd` MUST be a separate Bash call. The working directory persists between Bash calls, so there is zero reason to chain
- NEVER use redirects (`>`, `>>`, `<`). Use the Write tool for file output
- NEVER use command substitution (`$()` or backticks) unless absolutely unavoidable
- When you need to work in a specific directory, run `cd /path/to/dir` as a separate Bash call FIRST, then run subsequent commands in separate Bash calls (the working directory persists between Bash calls)

## Tool Substitution

Use dedicated tools instead of the following Bash commands. These are denied in settings.json.

| Prohibited Command | Use Instead | Notes |
|-------------------|-------------|-------|
| `find` | Glob | Pattern-based file search |
| `ls`, `tree` | Glob | For directory listing. Use Read to inspect a single directory when needed |
| `grep`, `rg` | Grep | Content search across files |
| `cat`, `head`, `tail` | Read | Read supports line offset and limit for partial reads |
| `sed`, `awk` | Edit | Exact string replacement in files |
| `mkdir`, `touch` | Write | Write auto-creates parent directories and can create empty files |
| `echo`, `printf` | Write (files) or direct text output (communication) | Never use shell output redirection |
| `curl`, `wget` | WebFetch (public URLs) or delegate to a Visual Reviewer / agent-browser teammate (local dev servers) | Never fetch HTTP yourself with curl/wget — for public URLs use the WebFetch tool, for local dev server diagnostics delegate to a teammate using the agent-browser CLI |

Additional guidance:
- Use Explore agent (Agent tool with subagent_type=Explore) for broader codebase navigation when simple Glob/Grep is insufficient
- Exception for `mkdir`/`touch`: `.keep` files for directories needed before a non-Write tool writes to them
