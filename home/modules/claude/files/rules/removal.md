# Removal

When removing a feature, option, file, or concept from a project, delete every corresponding mention from the repository in the same change. Do not leave historical deprecation notices behind.

The git history and the design document (if any) are the historical record. Source code, user-facing docs, skills, and examples should describe only the current state.

## Forbidden patterns

- Callouts like `**X deprecated**: see design 0000NNN for the restoration plan` in user-facing docs
- Sentences like `pre-existing X rows are preserved for forensic visibility` in schema/data-model docs (keep the column behavior accurate; do not document the removed value)
- Comments like `# X was deprecated in design NNNN` in source code
- Pointers like `(See §13 for the restoration plan)` in README / SKILL.md / cli-options
- "Multi-runner support" / "Backend selector" / similar Features bullets that describe an option that no longer exists
- Flag rows in CLI tables documenting removed flags ("--coding-agent — deprecated")
- Test cases that assert the removed behavior is rejected (positive removal tests are fine; sentinel-style "deprecated → error" tests are not — once the flag/code is gone, the absence is the test)

## What stays

- The design doc that authorized the removal — it is the canonical historical record.
- Migration / restoration plans inside that design doc.
- Git commit messages and the git log.
- Tests that exercise the *current* behavior (e.g., a regression guard that the removed flag no longer parses, asserted via Click's default "no such option" error — that is testing the absence, not advertising the deletion).

## Why

Deprecation notices and "for history" pointers turn user-facing surfaces into archaeological digs. New contributors and users encounter mentions of features that do not exist and have to reason about why. The cleanup should be total: after the removal lands, the repository reads as if the removed feature never existed. The historical record lives where it belongs — in git and in the design doc that scoped the change.

## Scope

This rule applies whenever code, options, files, or features are removed. Common triggers:

- Dropping a feature flag entirely
- Removing a CLI subcommand or option
- Deleting a code path / module / class / function
- Renaming with a hard-break (no aliases) — every mention of the old name goes
- Deprecating in v1 and removing in v2 — the v2 removal must complete the cleanup; v1 is the only place a deprecation note should ever live, and only briefly
