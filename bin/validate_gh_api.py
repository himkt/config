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
    from pathlib import Path
    import unittest

    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent / "tests"))
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
