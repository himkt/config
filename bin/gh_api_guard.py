#!/usr/bin/env python3

"""PreToolUse hook that validates `gh api` endpoints against an allowlist.

Works with both Claude Code and Codex hooks: reads the hook payload
({"tool_input": {"command": "..."}}) from stdin and, when the command
invokes `gh api` with an endpoint outside ALLOWLIST, emits a
permissionDecision "deny" JSON. Commands that do not invoke `gh api`,
and `gh api` calls whose every segment is allowlisted, produce no output
so the harness's normal permission rules decide.

Pair this hook with a broad allow rule (Claude: `Bash(gh api *)`,
Codex: `prefix_rule(pattern=["gh", "api"], decision="allow")`); the hook
narrows that grant to the endpoints below.

ALLOWLIST entries are (methods, endpoint-glob). Globs use fnmatch
semantics where `*` also matches `/`. The effective method is the value
of -X/--method, else POST when body fields are present (gh's behavior),
else GET.

CLI:
    (no argument) - run as hook: read payload from stdin
    test          - run embedded unittest suite
"""

import json
import os
import re
import sys
from fnmatch import fnmatchcase

# The deployed hook is a symlink; resolve it so validate_bash (kept next to
# this file in the repo) is importable regardless of the symlink location.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from validate_bash import parse

ALLOWLIST = (
    ("GET", "repos/*/*/actions/jobs/*"),
    ("GET PATCH DELETE", "repos/*/*/issues/comments/*"),
    ("GET POST", "repos/*/*/issues/*/comments"),
    ("GET PATCH DELETE", "repos/*/*/pulls/comments/*"),
    ("GET POST", "repos/*/*/pulls/*/comments"),
    ("GET POST", "repos/*/*/pulls/*/reviews"),
    ("GET POST PUT DELETE", "repos/*/*/pulls/*/reviews/*"),
    ("GET POST DELETE", "repos/*/*/pulls/*/requested_reviewers"),
    ("GET", "repos/*/*/contents/*"),
)

_METHOD_FLAGS = ("-X", "--method")
_BODY_FLAGS = ("-f", "--raw-field", "-F", "--field", "--input")

_GH_API_RE = re.compile(r"\bgh\s+api\b")


def _flag_values(keywords, names):
    values = []
    for name in names:
        v = keywords.get(name)
        if v is None:
            continue
        values.extend(v if isinstance(v, list) else [v])
    return values


def _effective_method(keywords):
    explicit = [v for v in _flag_values(keywords, _METHOD_FLAGS) if isinstance(v, str)]
    if explicit:
        return explicit[0].upper() if len(explicit) == 1 else None
    if _flag_values(keywords, _BODY_FLAGS):
        return "POST"
    return "GET"


def _check_segment(seg):
    """Return rejection reason for one `gh api` segment, or None if allowed."""
    if seg["expansions"]:
        e = seg["expansions"][0]
        return f"cannot verify endpoint: {e['reason']} in '{e['token']}'"

    positionals = seg["positionals"][1:]
    if len(positionals) != 1:
        return ("expected exactly one endpoint argument; "
                "place the endpoint immediately after 'gh api'")
    endpoint = positionals[0].lstrip("/").partition("?")[0]

    method = _effective_method(seg["keywords"])
    if method is None:
        return "multiple -X/--method flags"

    for methods, pattern in ALLOWLIST:
        if method in methods.split() and fnmatchcase(endpoint, pattern):
            return None
    return f"{method} {endpoint} is not in the allowlist"


def check(command):
    """Return rejection reason for a command string, or None if no opinion.

    Denies when any `gh api` segment fails validation, or when the
    command mentions `gh api` but cannot be parsed. Commands without
    `gh api` yield None (the hook stays silent).
    """
    try:
        segments = parse(command)
    except ValueError as e:
        if _GH_API_RE.search(command):
            return f"cannot verify 'gh api' command: {e}"
        return None

    for seg in segments:
        if seg["command"] == "gh" and seg["positionals"][:1] == ["api"]:
            if reason := _check_segment(seg):
                return reason
    return None


def _deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason":
                f"{reason} (allowlist: gh_api_guard.py)",
        },
    }))


def _run_tests():
    import unittest

    class GhApiGuardTests(unittest.TestCase):
        def assertAllowed(self, command):
            self.assertIsNone(check(command), command)

        def assertDenied(self, command, reason_part):
            reason = check(command)
            self.assertIsNotNone(reason, command)
            self.assertIn(reason_part, reason, command)

        def test_non_gh_api_commands_pass_through(self):
            for src in [
                "ls -la",
                "gh pr view 123",
                "gh apiary",
                "rg 'gh api' docs/",
            ]:
                with self.subTest(src=src):
                    self.assertAllowed(src)

        def test_allowed_endpoints(self):
            for src in [
                "gh api repos/himkt/config/actions/jobs/123",
                "gh api /repos/himkt/config/actions/jobs/123",
                "gh api repos/himkt/config/issues/1/comments",
                "gh api repos/himkt/config/issues/1/comments -f body=hi",
                "gh api repos/himkt/config/issues/comments/9 -X PATCH -f body=hi",
                "gh api repos/himkt/config/issues/comments/9 -X DELETE",
                "gh api repos/himkt/config/pulls/comments/9 -X PATCH -f body=hi",
                "gh api repos/himkt/config/pulls/2/comments",
                "gh api repos/himkt/config/pulls/2/reviews -f event=APPROVE",
                "gh api repos/himkt/config/pulls/2/reviews/5/dismissals -X PUT -f message=x",
                "gh api repos/himkt/config/pulls/2/requested_reviewers -f 'reviewers[]=a'",
                "gh api repos/himkt/config/contents/README.md",
                "gh api 'repos/himkt/config/contents/README.md?ref=main'",
                "gh api repos/himkt/config/contents/README.md --jq .sha",
                "gh api repos/himkt/config/pulls/2/comments | wc -l",
            ]:
                with self.subTest(src=src):
                    self.assertAllowed(src)

        def test_denied_endpoints(self):
            for src, reason_part in [
                ("gh api user", "GET user is not in the allowlist"),
                ("gh api repos/himkt/config", "not in the allowlist"),
                ("gh api repos/himkt/config/pulls -f title=x",
                 "POST repos/himkt/config/pulls is not in the allowlist"),
                ("gh api repos/himkt/config/contents/x -X PUT -f message=m",
                 "PUT repos/himkt/config/contents/x is not in the allowlist"),
                ("gh api repos/himkt/config/actions/jobs/1 -X POST",
                 "POST repos/himkt/config/actions/jobs/1 is not in the allowlist"),
                ("gh api --method DELETE repos/himkt/config",
                 "not in the allowlist"),
                ("gh api graphql -f query=q", "POST graphql is not in the allowlist"),
            ]:
                with self.subTest(src=src):
                    self.assertDenied(src, reason_part)

        def test_unverifiable_commands_denied(self):
            for src, reason_part in [
                ("gh api", "exactly one endpoint"),
                ("gh api a/b c/d", "exactly one endpoint"),
                ("gh api --paginate repos/x/y/actions/jobs/1", "exactly one endpoint"),
                ('gh api "repos/$OWNER/config/pulls/2/comments"', "cannot verify endpoint"),
                ("gh api 'repos/x/y/pulls/2/comments' -X GET -X DELETE",
                 "multiple -X/--method flags"),
                ("gh api repos/x/y/contents/a 'unclosed", "cannot verify 'gh api' command"),
            ]:
                with self.subTest(src=src):
                    self.assertDenied(src, reason_part)

        def test_denied_segment_inside_pipeline(self):
            self.assertDenied("gh api user | jq .login", "GET user is not in the allowlist")

        def test_method_from_body_flags(self):
            self.assertDenied(
                "gh api repos/x/y/contents/a -F content=@f",
                "POST repos/x/y/contents/a is not in the allowlist",
            )

    suite = unittest.TestLoader().loadTestsFromTestCase(GhApiGuardTests)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        sys.exit(0 if _run_tests() else 1)

    try:
        command = json.load(sys.stdin)["tool_input"]["command"]
    except (json.JSONDecodeError, KeyError, TypeError):
        sys.exit(0)
    if not isinstance(command, str):
        sys.exit(0)

    if reason := check(command):
        _deny(reason)
