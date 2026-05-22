---
name: pathfinder-explain
description: Explain the implementation of a symbol by tracing its definition using LSP. Use when user asks to explain, trace, or understand how a specific symbol (function, class, variable) is implemented. Takes symbol name as argument. Do NOT rely on grep and reading files alone — use this skill for accurate LSP-based tracing.
context: fork
---

# Pathfinder Explain

Explain the implementation of a symbol by tracing its definition using LSP.

Symbol to explain: $ARGUMENTS

## Instructions

1. Find where the symbol `$ARGUMENTS` is imported or defined in the current codebase using Grep
2. Use `mcp__pathfinder-{lang}__definition` tool to jump to its actual definition
3. Read the source code of the definition
4. If the definition references other symbols, recursively trace those definitions as needed
5. Provide a comprehensive explanation based on the actual source code

## CRITICAL

- ALWAYS use the LSP definition tool (`mcp__pathfinder-python__definition`, `mcp__pathfinder-typescript__definition`, etc.) to trace symbols
- Do NOT rely on general knowledge or guessing - read the actual implementation

## Character Position Calculation

When calling LSP definition tool, count the character position carefully:
1. The position is 0-indexed (first character is position 0)
2. Count each character one by one, including spaces
3. Do NOT guess or estimate - count precisely

## If LSP Returns Empty Targets

The position is likely wrong. Do NOT give up:
1. Re-read the line and count character position from 0
2. Try position +1 or -1 if still failing
3. Do NOT fall back to other methods until you've tried at least 3 different positions
