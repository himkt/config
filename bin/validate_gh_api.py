#!/usr/bin/env python3

import json
import os
import re
import sys
from dataclasses import dataclass
from fnmatch import fnmatchcase

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from validate_bash import parse


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

    for entry in ALLOWLIST:
        if method in entry.methods and fnmatchcase(endpoint, entry.endpoint_glob):
            return None
    return f"{method} {endpoint} is not in the allowlist"


def check(command):
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
