# Code Comments

Write code that explains itself. Add a comment ONLY WHEN THE LOGIC CANNOT BE UNDERSTOOD WITHOUT IT — carry intent through naming, structure, and small well-named functions, and reserve comments for meaning the code itself cannot express.

Before writing a comment, first try to make it unnecessary: rename, extract, or restructure. Write the comment only if the code still cannot carry the meaning.

## When a comment is justified

- A constraint or invariant the code cannot express (e.g., "callers rely on this list staying sorted", "this call must precede the flush because the API mutates state on read")
- A workaround with an external cause (upstream bug, platform quirk) that would otherwise read as a mistake
- The "why" behind a decision that contradicts the obvious approach

## Forbidden patterns

- Comments that restate what the code does (`# increment counter`, `// loop over users`)
- Section-header comments narrating a function's steps instead of extracting named functions
- Comments addressed to the reviewer ("changed to fix X", "now handles Y correctly") — that context belongs in the commit message or PR description
- Commented-out code — delete it; git history is the archive

## Scope

Applies across all projects whenever source code is written, edited, or reviewed. When editing existing code, match the file's comment density for legitimate comments, and remove comments made redundant by your change rather than leaving them stale.
