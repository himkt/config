# Git Workflow

Rules for consistent, clean git commit history across all projects.

- NEVER use HEREDOC syntax for git commit. Always use simple `git commit -m "message"` format
- NEVER use `git -C <path>`. It breaks auto-approval patterns in settings.json. The working directory is already the project root, so `-C` is unnecessary
- Commit messages MUST be a single line. Multi-line commit messages are strictly forbidden
- Write commit messages in English, concise and descriptive
- Use conventional commit prefixes: feat, fix, chore, refactor, docs
- NEVER use `git add -f` or `git add --force`. If a file is gitignored, it is gitignored for a reason. Do not force-stage it under any circumstances
- NEVER commit files from `design-docs/` or `researches/` directories. They are gitignored (globally) and must stay out of version control
