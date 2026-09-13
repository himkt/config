#!/usr/bin/env python3

"""Validate literal GitHub API arguments against the endpoint policy."""

import os
import sys
from dataclasses import dataclass


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

_VALUE_OPTIONS = {
    "-X": "method", "--method": "method",
    "-f": "raw-field", "--raw-field": "raw-field",
    "-F": "field", "--field": "field",
    "--input": "input", "-H": "header", "--header": "header",
    "--hostname": "hostname", "--cache": "cache",
    "-q": "jq", "--jq": "jq", "-t": "template", "--template": "template",
}
_BOOLEAN_OPTIONS = {
    "--paginate": "paginate", "--slurp": "slurp",
    "-i": "include", "--include": "include", "--silent": "silent",
    "--verbose": "verbose", "--allow-escape-sequences": "allow-escape-sequences",
}
_REPEATABLE = frozenset(("field", "raw-field", "header"))
_METHODS = frozenset(("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"))


def _block(message):
    from validate_bash import PolicyError

    raise PolicyError("GH_API_BLOCK", message)


def _options(arguments, budget):
    options = {}
    i = 0
    while i < len(arguments):
        budget.charge()
        token = arguments[i]
        i += 1
        if token == "--":
            if i != len(arguments):
                _block("Endpoint must precede options with no extra arguments")
            break
        if token in _BOOLEAN_OPTIONS:
            name = _BOOLEAN_OPTIONS[token]
            value = True
        else:
            if token.startswith("--"):
                flag, separator, value = token.partition("=")
                attached = bool(separator)
            elif token.startswith("-") and len(token) >= 2:
                flag, value = token[:2], token[2:]
                attached = bool(value)
                if value.startswith("="):
                    value = value[1:]
            else:
                _block("Expected an API option after the endpoint")
            if flag not in _VALUE_OPTIONS:
                _block("Unsupported API option")
            name = _VALUE_OPTIONS[flag]
            if not attached:
                if i == len(arguments):
                    _block("API option requires a value")
                value = arguments[i]
                i += 1
            if not value:
                _block("API option requires a nonempty value")
        if name in options and name not in _REPEATABLE:
            _block("Repeated scalar API option")
        options.setdefault(name, []).append(value)
    return options


def check_argv(argv, budget=None):
    from validate_bash import EvaluationBudget, PolicyError, _match_argument

    if budget is None:
        budget = EvaluationBudget()
    if not isinstance(argv, list) or any(not isinstance(arg, str) for arg in argv):
        _block("Expected literal API arguments")
    if len(argv) > 1024:
        raise PolicyError("EVALUATION_LIMIT", "Argument count limit exceeded")
    total_bytes = 0
    for arg in argv:
        budget.charge(len(arg) + 1)
        try:
            total_bytes += len(arg.encode("utf-8"))
        except UnicodeError:
            _block("Invalid Unicode in API arguments")
        if total_bytes > 65536:
            raise PolicyError("EVALUATION_LIMIT", "API argument byte limit exceeded")
    if len(argv) < 3 or argv[:2] != ["gh", "api"] or argv[2].startswith("-"):
        _block("Place one relative endpoint immediately after gh api")
    budget.charge(len(argv[2]))
    if "#" in argv[2]:
        _block("Use a GitHub endpoint without a URL fragment")
    endpoint = argv[2].partition("?")[0]
    budget.charge(len(endpoint) * 8)
    if (not endpoint or endpoint.startswith("//") or "://" in endpoint
            or any(char in endpoint for char in "\\%{}")
            or "//" in endpoint or any(ord(char) < 32 or ord(char) == 127 for char in endpoint)):
        _block("Use an unambiguous relative GitHub endpoint")
    endpoint = endpoint.removeprefix("/")
    if any(component in (".", "..") for component in endpoint.split("/")):
        _block("Endpoint path traversal is unsupported")
    options = _options(argv[3:], budget)
    host = os.environ.get("GH_HOST", "")
    budget.charge(len(host) + 1)
    if host and host != "github.com":
        _block("GH_HOST must select github.com")
    if "hostname" in options and options["hostname"][0] != "github.com":
        _block("API hostname must be github.com")
    for header in options.get("header", []):
        budget.charge(len(header))
        if header.partition(":")[0].strip().lower() == "host":
            _block("Use the configured GitHub host without a Host header override")
    if "input" in options and options["input"][0] == "-":
        _block("Provide a file source for the request body")
    for field in options.get("field", []):
        budget.charge(len(field))
        if field.partition("=")[2] == "@-":
            _block("Provide a file source for typed fields")
    if "method" in options:
        budget.charge(len(options["method"][0]))
        method = options["method"][0].upper()
    else:
        method = "POST" if any(name in options for name in ("field", "raw-field", "input")) else "GET"
    if method not in _METHODS:
        _block("Unsupported HTTP method")
    for entry in ALLOWLIST:
        budget.charge(len(entry.endpoint_glob) + 1)
        if method in entry.methods and _match_argument(endpoint, entry.endpoint_glob, True, budget):
            return None
    _block("Endpoint and method require GitHub policy review")


def _run_tests():
    import unittest
    from unittest.mock import patch
    from validate_bash import PolicyError

    contents = "repos/himkt/config/contents/x"
    comments = "repos/himkt/config/issues/1/comments"

    class GitHubTests(unittest.TestCase):
        def test_endpoint_methods(self):
            for path, methods in (
                ("actions/jobs/1", {"GET"}),
                ("issues/comments/1", {"GET", "PATCH", "DELETE"}),
                ("issues/1/comments", {"GET", "POST"}),
                ("pulls/comments/1", {"GET", "PATCH", "DELETE"}),
                ("pulls/1/comments", {"GET", "POST"}),
                ("pulls/1/reviews", {"GET", "POST"}),
                ("pulls/1/reviews/1", {"GET", "POST", "PUT", "DELETE"}),
                ("pulls/1/requested_reviewers", {"GET", "POST", "DELETE"}),
                ("contents/x", {"GET"}),
            ):
                for method in ("GET", "POST", "PATCH", "PUT", "DELETE", "HEAD"):
                    with self.subTest(path=path, method=method):
                        self.check(["repos/himkt/config/" + path, "-X", method], method in methods)

        def check(self, arguments, allowed):
            if allowed:
                self.assertIsNone(check_argv(["gh", "api", *arguments]))
            else:
                with self.assertRaises(PolicyError) as caught:
                    check_argv(["gh", "api", *arguments])
                self.assertEqual(caught.exception.code, "GH_API_BLOCK")

        def test_options_and_paths(self):
            for arguments in (
                [contents], ["/" + contents], [contents + "?ref=main"],
                [contents + "?ref=a%23b"], [contents, "-XGET"],
                [contents, "--method=get"], [contents, "--paginate", "--jq", ".[] | .name"],
                [comments, "-fbody=x"], [comments, "--raw-field", "body=x"],
                [comments, "-Fbody=@file"], [comments, "--input", "file"],
                [contents, "--hostname=github.com"],
            ):
                with self.subTest(arguments=arguments):
                    self.check(arguments, True)
            for arguments in (
                [], ["user"], ["-X", "GET", contents], [contents, "extra"],
                [contents, "--unknown"], [contents, "--method"],
                [contents, "-XGET", "--method=GET"], [contents, "--method=HEAD"],
                [contents, "-f", "body=x"], [comments, "--input", "-"],
                [comments, "-Fbody=@-"], [contents, "--hostname=enterprise.example"],
                [contents, "-H", "Host: alternate.example"],
                ["https://github.com/" + contents], ["//" + contents],
                ["repos/x/y/../contents/x"], ["repos/x/y/contents/%2e%2e/x"],
                ["repos/{owner}/x/contents/x"], ["repos/x/y\\contents/x"],
                ["repos/himkt/config#/pulls/1/reviews/1", "-XDELETE"],
                [contents + "#"], [contents + "?ref=main#fragment"],
            ):
                with self.subTest(arguments=arguments):
                    self.check(arguments, False)

        def test_runtime_host(self):
            with patch.dict(os.environ, GH_HOST="enterprise.example"):
                self.check([contents], False)

    with patch.dict(os.environ, GH_HOST=""):
        suite = unittest.TestLoader().loadTestsFromTestCase(GitHubTests)
        return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main():
    import argparse
    from validate_bash import _validate_cli

    parser = argparse.ArgumentParser(prog="validate_gh_api.py")
    parser.add_argument("subcommand", choices=("validate", "test"))
    arguments = parser.parse_args()
    if arguments.subcommand == "test":
        return 0 if _run_tests() else 1
    return _validate_cli(github_only=True)


if __name__ == "__main__":
    sys.exit(main())
