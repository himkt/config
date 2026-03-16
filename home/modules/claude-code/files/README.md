# ~/.claude

Personal configuration repository for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

This repository tracks reusable customizations — skills, agents, scripts, and settings — while keeping ephemeral data (history, caches, session state) gitignored.

## Structure

```
~/.claude/
├── CLAUDE.md          # Global instructions applied to all projects
├── .claude/CLAUDE.md  # Instructions specific to this repository
├── settings.json      # Claude Code settings (model, permissions, etc.)
├── agents/            # Custom agent definitions
├── skills/            # Skills (slash commands invoked via the Skill tool)
├── bin/               # Utility scripts (e.g., status line)
└── external-skills/   # Plugin marketplace for external skills
```

### Skills

Skills are reusable prompt templates that Claude Code can invoke as slash commands. Each skill lives in its own directory under `skills/` and is registered in `CLAUDE.md` via the `/sync-skills` skill.

### Agents

Agents are specialized subagent definitions written in Markdown with YAML frontmatter. They extend Claude Code with domain-specific capabilities such as document creation, test generation, and web research.

### Bin

Executable scripts used by Claude Code features. For example, the status line script provides contextual information in the terminal.
