#!/usr/bin/env python3

"""PreToolUse hook that restricts `gh api` to an allowlist of endpoints.

Reads {"tool_input": {"command": "..."}} from stdin and denies when any
`gh api` segment targets an endpoint/method outside ALLOWLIST or cannot be
verified literally (shell expansion, unbalanced quotes, ambiguous flags).

CLI subcommands:
    validate  - emit a PreToolUse deny decision when the command is rejected
    test      - run embedded unittest suite
"""

import json
import re
import shlex
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase


@dataclass(frozen=True)
class AllowlistEntry:
    methods: frozenset[str]
    endpoint_glob: str


ALLOWLIST = (
    AllowlistEntry(frozenset({"GET"}), "repos/*/*/actions/jobs/*"),
    AllowlistEntry(frozenset({"GET", "PATCH", "DELETE"}), "repos/*/*/issues/comments/*"),
    AllowlistEntry(frozenset({"GET", "POST"}), "repos/*/*/issues/*/comments"),
    AllowlistEntry(frozenset({"GET", "PATCH", "DELETE"}), "repos/*/*/pulls/comments/*"),
    AllowlistEntry(frozenset({"GET", "POST"}), "repos/*/*/pulls/*/comments"),
    AllowlistEntry(frozenset({"GET", "POST"}), "repos/*/*/pulls/*/reviews"),
    AllowlistEntry(frozenset({"GET", "POST", "PUT", "DELETE"}), "repos/*/*/pulls/*/reviews/*"),
    AllowlistEntry(frozenset({"GET", "POST", "DELETE"}), "repos/*/*/pulls/*/requested_reviewers"),
    AllowlistEntry(frozenset({"GET"}), "repos/*/*/contents/*"),
)

_METHOD_FLAGS = ("-X", "--method")
_BODY_FLAGS = ("-f", "--raw-field", "-F", "--field", "--input")

_GH_API_RE = re.compile(r"\bgh\s+api\b")

# shlex splits these out as standalone tokens when unquoted; every such
# token ends the current segment so a `gh api` after `;`, `|`, `&&`, or a
# redirect is still inspected on its own.
_OPERATOR_CHARS = set("();<>|&")


def _segments(command):
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    segments = [[]]
    for token in lex:
        if set(token) <= _OPERATOR_CHARS:
            segments.append([])
        else:
            segments[-1].append(token)
    return [s for s in segments if s]


def _classify(words):
    positionals = []
    keywords = {}
    i = 0
    while i < len(words):
        w = words[i]
        i += 1
        if w == "--":
            positionals.extend(words[i:])
            break
        if w.startswith("--") and "=" in w:
            key, _, value = w.partition("=")
            keywords.setdefault(key, []).append(value)
        elif w.startswith("-") and w != "-":
            if i < len(words) and not words[i].startswith("-"):
                keywords.setdefault(w, []).append(words[i])
                i += 1
            else:
                keywords.setdefault(w, []).append(True)
        else:
            positionals.append(w)
    return positionals, keywords


def _effective_method(keywords):
    explicit = [v for flag in _METHOD_FLAGS for v in keywords.get(flag, ()) if isinstance(v, str)]
    if explicit:
        return explicit[0].upper() if len(explicit) == 1 else None
    if any(flag in keywords for flag in _BODY_FLAGS):
        return "POST"
    return "GET"


def _check_segment(words):
    positionals, keywords = _classify(words)
    if positionals[:2] != ["gh", "api"]:
        return None

    for w in words:
        if "$" in w or "`" in w:
            return f"cannot verify endpoint: shell expansion in '{w}'"

    endpoints = positionals[2:]
    if len(endpoints) != 1:
        return ("expected exactly one endpoint argument; "
                "place the endpoint immediately after 'gh api'")
    endpoint = endpoints[0].lstrip("/").partition("?")[0]

    method = _effective_method(keywords)
    if method is None:
        return "multiple -X/--method flags"

    for entry in ALLOWLIST:
        if method in entry.methods and fnmatchcase(endpoint, entry.endpoint_glob):
            return None
    return f"{method} {endpoint} is not in the allowlist"


def check(command):
    try:
        segments = _segments(command)
    except ValueError as e:
        if _GH_API_RE.search(command):
            return f"cannot verify 'gh api' command: {e}"
        return None

    for words in segments:
        if reason := _check_segment(words):
            return reason
    return None


def _deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason":
                f"{reason} (allowlist: validate_gh_api.py)",
        },
    }))


def _run_tests():
    import unittest

    class ValidateGhApiTests(unittest.TestCase):
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
                "echo 'price $'",
                "cat 'unclosed",
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
                "gh api repos/himkt/config/contents/README.md --jq '.x > 0'",
                "gh api repos/himkt/config/pulls/2/comments | wc -l",
                "gh -R himkt/config api repos/himkt/config/pulls/2/comments",
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
                ("gh api repos/x/y/contents/a -F content=@f",
                 "POST repos/x/y/contents/a is not in the allowlist"),
            ]:
                with self.subTest(src=src):
                    self.assertDenied(src, reason_part)

        def test_unverifiable_commands_denied(self):
            for src, reason_part in [
                ("gh api", "exactly one endpoint"),
                ("gh api a/b c/d", "exactly one endpoint"),
                ("gh api --paginate repos/x/y/actions/jobs/1", "exactly one endpoint"),
                ("gh api repos/x/y/actions/jobs/1 2>/dev/null", "exactly one endpoint"),
                ('gh api "repos/$OWNER/config/pulls/2/comments"', "cannot verify endpoint"),
                ("gh api repos/x/y/contents/a -H \"Auth: `cat t`\"", "cannot verify endpoint"),
                ("gh api 'repos/x/y/pulls/2/comments' -X GET -X DELETE",
                 "multiple -X/--method flags"),
                ("gh api repos/x/y/contents/a 'unclosed", "cannot verify 'gh api' command"),
            ]:
                with self.subTest(src=src):
                    self.assertDenied(src, reason_part)

        def test_gh_api_found_after_any_operator(self):
            for src in [
                "gh api user | jq .login",
                "echo x; gh api user",
                "true && gh api user",
                "false || gh api user",
                "gh api user > out",
                "gh api user&",
            ]:
                with self.subTest(src=src):
                    self.assertDenied(src, "not in the allowlist")

    suite = unittest.TestLoader().loadTestsFromTestCase(ValidateGhApiTests)
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(prog="validate_gh_api.py")
    ap.add_argument("subcommand", choices=("validate", "test"))
    subcmd = ap.parse_args().subcommand

    if subcmd == "test":
        sys.exit(0 if _run_tests() else 1)

    try:
        command = json.load(sys.stdin)["tool_input"]["command"]
    except (json.JSONDecodeError, KeyError, TypeError):
        sys.exit(0)
    if not isinstance(command, str):
        sys.exit(0)

    if reason := check(command):
        _deny(reason)
