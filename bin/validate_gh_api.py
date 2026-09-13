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


def check_deployment_hosts(default_host, api_host_override):
    if default_host != "github.com" or api_host_override is not None:
        raise ValueError("Deploy with default host github.com and no API-host override")


def check(command):
    from validate_bash import EvaluationBudget, parse

    budget = EvaluationBudget()
    return check_argv(parse(command, budget), budget)


def _run_tests():
    import tempfile
    import unittest
    from pathlib import Path
    from unittest.mock import patch
    import validate_bash as gate

    gh = sys.modules[__name__]
    COMMENTS = "repos/himkt/config/issues/1/comments"
    COMMENT = "repos/himkt/config/issues/comments/9"
    CONTENTS = "repos/himkt/config/contents/README.md"
    host_fixtures = [
        {"name":"github_default","hosts_yaml":"github.com:\n  user: fixture\n","default_host":"github.com","api_host_override":None,"trusted":True},
        {"name":"enterprise_default","hosts_yaml":"enterprise.example:\n  user: fixture\n","default_host":"enterprise.example","api_host_override":None,"trusted":False},
        {"name":"github_api_host_override","hosts_yaml":"github.com:\n  user: fixture\n  api_host: alternate.example\n","default_host":"github.com","api_host_override":"alternate.example","trusted":False}
    ]

    class GitHubArgvTests(unittest.TestCase):
        def setUp(self):
            environment = patch.dict(os.environ, {}, clear=False)
            environment.start()
            self.addCleanup(environment.stop)
            os.environ.pop("GH_HOST", None)

        def assert_allowed(self, endpoint=CONTENTS, *options):
            self.assertIsNone(gh.check_argv(["gh", "api", endpoint, *options]))

        def assert_blocked(self, argv):
            with self.assertRaises(gate.PolicyError) as caught:
                gh.check_argv(argv)
            self.assertEqual(caught.exception.code, "GH_API_BLOCK")

        def test_all_nine_endpoint_method_entries_are_preserved(self):
            self.assertEqual([(sorted(entry.methods), entry.endpoint_glob) for entry in gh.ALLOWLIST], [
                (["GET"], "repos/*/*/actions/jobs/*"),
                (["DELETE", "GET", "PATCH"], "repos/*/*/issues/comments/*"),
                (["GET", "POST"], "repos/*/*/issues/*/comments"),
                (["DELETE", "GET", "PATCH"], "repos/*/*/pulls/comments/*"),
                (["GET", "POST"], "repos/*/*/pulls/*/comments"),
                (["GET", "POST"], "repos/*/*/pulls/*/reviews"),
                (["DELETE", "GET", "POST", "PUT"], "repos/*/*/pulls/*/reviews/*"),
                (["DELETE", "GET", "POST"], "repos/*/*/pulls/*/requested_reviewers"),
                (["GET"], "repos/*/*/contents/*"),
            ])

        def test_every_endpoint_family_accepts_exactly_its_existing_methods(self):
            cases = [
                ("actions/jobs/1", {"GET"}),
                ("issues/comments/1", {"GET", "PATCH", "DELETE"}),
                ("issues/1/comments", {"GET", "POST"}),
                ("pulls/comments/1", {"GET", "PATCH", "DELETE"}),
                ("pulls/1/comments", {"GET", "POST"}),
                ("pulls/1/reviews", {"GET", "POST"}),
                ("pulls/1/reviews/1", {"GET", "POST", "PUT", "DELETE"}),
                ("pulls/1/requested_reviewers", {"GET", "POST", "DELETE"}),
                ("contents/README.md", {"GET"}),
            ]
            for suffix, methods in cases:
                for method in ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                    endpoint = "repos/himkt/config/" + suffix
                    with self.subTest(endpoint=endpoint, method=method):
                        if method in methods:
                            self.assert_allowed(endpoint, "--method", method)
                        else:
                            self.assert_blocked(["gh", "api", endpoint, "--method", method])

        def test_existing_descendant_matching_is_preserved(self):
            self.assert_allowed("repos/himkt/config/pulls/2/reviews/5/dismissals", "-X", "PUT")
            self.assert_allowed("repos/himkt/config/contents/a/b/c")
            self.assert_allowed("repos/himkt/config/actions/jobs/1/logs")

        def test_attached_separated_equals_and_case_normalized_methods(self):
            for options in (["-X", "DELETE"], ["-XDELETE"], ["-X=DELETE"],
                            ["--method", "delete"], ["--method=DeLeTe"]):
                with self.subTest(options=options):
                    self.assert_allowed(COMMENT, *options)
                    self.assert_blocked(["gh", "api", CONTENTS, *options])

        def test_body_and_field_options_default_to_post(self):
            for options in (["-f", "body=x"], ["-fbody=x"], ["-f=body=x"],
                            ["--raw-field=body=x"], ["--raw-field", "body=x"],
                            ["-F", "body=x"], ["-Fbody=x"], ["-F=body=x"],
                            ["--field=body=x"], ["--field", "body=x"],
                            ["--input", "body.json"], ["--input=body.json"]):
                with self.subTest(options=options):
                    self.assert_allowed(COMMENTS, *options)
                    self.assert_blocked(["gh", "api", CONTENTS, *options])

        def test_explicit_method_overrides_body_driven_post(self):
            self.assert_allowed(CONTENTS, "-fbody=x", "-XGET")
            self.assert_allowed(COMMENT, "-XPATCH", "--input=body.json")

        def test_boolean_options_preserve_default_get_and_do_not_consume_an_endpoint(self):
            for option in ("--paginate", "--slurp", "-i", "--include", "--silent", "--verbose",
                           "--allow-escape-sequences"):
                with self.subTest(option=option):
                    self.assert_allowed(CONTENTS, option)
                    self.assert_blocked(["gh", "api", CONTENTS, option, CONTENTS])

        def test_supported_scalar_option_spellings_preserve_get(self):
            for options in (["--hostname", "github.com"], ["--hostname=github.com"],
                            ["--cache", "1h"], ["--cache=1h"],
                            ["-q", ".sha"], ["-q.sha"], ["-q=.sha"], ["--jq=.sha"],
                            ["--jq", ".sha"], ["-t", "{{.sha}}"], ["-t{{.sha}}"],
                            ["--template={{.sha}}"], ["--template", "{{.sha}}"],
                            ["-H", "Accept: application/json"], ["-HAccept: application/json"],
                            ["-H=Accept: application/json"], ["--header=Accept: application/json"]):
                with self.subTest(options=options):
                    self.assert_allowed(CONTENTS, *options)

        def test_missing_option_values_and_unknown_flags_are_rejected(self):
            for option in ("-X", "--method", "-f", "--raw-field", "-F", "--field", "--input",
                           "-H", "--header", "--hostname", "--cache", "-q", "--jq", "-t", "--template",
                           "--unknown", "-iv", "-ii", "--paginate=true"):
                with self.subTest(option=option):
                    self.assert_blocked(["gh", "api", CONTENTS, option])

        def test_scalar_duplicates_are_rejected_across_aliases(self):
            for options in (["-XGET", "--method=GET"], ["--input=a", "--input", "b"],
                            ["--hostname=github.com", "--hostname", "github.com"],
                            ["--cache=1h", "--cache=2h"], ["-q.x", "--jq=.y"],
                            ["-tfoo", "--template=bar"], ["--paginate", "--paginate"],
                            ["-i", "--include"]):
                with self.subTest(options=options):
                    self.assert_blocked(["gh", "api", CONTENTS, *options])

        def test_field_and_header_repetition_is_supported(self):
            self.assert_allowed(COMMENTS, "-fa=1", "--raw-field=b=2", "-Fc=3", "--field=d=4",
                                "-HAccept: application/json", "--header=X-Trace: test")

        def test_endpoint_precedes_options_and_has_no_extra_positionals(self):
            for argv in (["gh", "api"], ["gh", "api", "--method", "GET", CONTENTS],
                         ["gh", "api", CONTENTS, CONTENTS],
                         ["gh", "-R", "himkt/config", "api", CONTENTS],
                         ["gh", "--hostname", "github.com", "api", CONTENTS]):
                with self.subTest(argv=argv):
                    self.assert_blocked(argv)
            self.assert_allowed(CONTENTS, "--")
            self.assert_blocked(["gh", "api", CONTENTS, "--", "extra"])

        def test_unknown_or_empty_methods_are_rejected(self):
            for method in ("", "TRACE", "GET POST", "GET\n", "=GET"):
                with self.subTest(method=method):
                    self.assert_blocked(["gh", "api", CONTENTS, "--method", method])

        def test_relative_paths_allow_one_leading_slash_and_optional_query(self):
            for endpoint in (CONTENTS, "/" + CONTENTS, CONTENTS + "?ref=main", CONTENTS + "?x=%2f"):
                with self.subTest(endpoint=endpoint):
                    self.assert_allowed(endpoint)

        def test_endpoint_normalization_rejects_ambiguous_destinations(self):
            for endpoint in (
                "https://api.github.com/" + CONTENTS, "//github.com/" + CONTENTS,
                "//" + CONTENTS, "repos//himkt/config/contents/x",
                "repos/himkt/config/contents/../secrets", "repos/himkt/config/contents/./x",
                "repos/himkt/config/contents/%2e%2e/x", "repos/himkt/config/contents/%61",
                "repos/himkt/config/contents/a\\b", "repos/{owner}/{repo}/contents/x",
            ):
                with self.subTest(endpoint=endpoint):
                    self.assert_blocked(["gh", "api", endpoint])

        def test_runtime_host_inputs_require_github_com(self):
            self.assert_allowed(CONTENTS, "--hostname=github.com")
            self.assert_blocked(["gh", "api", CONTENTS, "--hostname=enterprise.example"])
            with patch.dict(os.environ, {"GH_HOST": "github.com"}):
                self.assert_allowed()
            with patch.dict(os.environ, {"GH_HOST": "enterprise.example"}):
                self.assert_blocked(["gh", "api", CONTENTS])
                self.assert_blocked(["gh", "api", CONTENTS, "--hostname=github.com"])

        def test_host_header_override_is_rejected_for_all_header_spellings(self):
            for options in (["-H", "Host: enterprise.example"], ["-Hhost: github.com"],
                            ["-H=HOST: enterprise.example"], ["--header=Host: enterprise.example"]):
                with self.subTest(options=options):
                    self.assert_blocked(["gh", "api", CONTENTS, *options])

        def test_explicit_stdin_body_spellings_are_rejected(self):
            for options in (["--input", "-"], ["--input=-"], ["-F", "body=@-"],
                            ["-Fbody=@-"], ["-F=body=@-"], ["--field=body=@-"]):
                with self.subTest(options=options):
                    self.assert_blocked(["gh", "api", COMMENTS, *options])
            self.assert_allowed(COMMENTS, "-fbody=@-")

        def test_stdin_alias_and_file_sources_are_opaque_and_never_opened(self):
            for source in ("/dev/stdin", "/dev/fd/0", "missing.json", "relative/body.json"):
                with self.subTest(source=source):
                    with patch("builtins.open", side_effect=AssertionError("Body source opened")), \
                         patch("os.open", side_effect=AssertionError("Body source opened")):
                        self.assert_allowed(COMMENTS, "--input", source)
                        self.assert_allowed(COMMENTS, "-Fbody=@" + source)

        def test_symlink_and_fifo_sources_are_accepted_without_reading(self):
            scratch = Path.cwd() / ".test-scratch" / "gh-policy"
            scratch.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=scratch) as directory:
                fifo = Path(directory) / "body.fifo"
                os.mkfifo(fifo)
                link = Path(directory) / "body.link"
                link.symlink_to(fifo)
                for source in (fifo, link):
                    with self.subTest(source=source.name):
                        with patch("builtins.open", side_effect=AssertionError("Body source opened")), \
                             patch("os.open", side_effect=AssertionError("Body source opened")):
                            self.assert_allowed(COMMENTS, "--input", str(source))
                            self.assert_allowed(COMMENTS, "-Fbody=@" + str(source))

        def test_github_checks_share_the_invocation_work_budget(self):
            budget = gate.EvaluationBudget(limit=0)
            with self.assertRaises(gate.PolicyError) as caught:
                gh.check_argv(["gh", "api", CONTENTS], budget=budget)
            self.assertEqual(caught.exception.code, "EVALUATION_LIMIT")

        def test_resolved_deployment_hosts_enforce_the_trusted_configuration_precondition(self):
            fixtures = host_fixtures
            for fixture in fixtures:
                with self.subTest(name=fixture["name"]):
                    if fixture["trusted"]:
                        self.assertIsNone(gh.check_deployment_hosts(
                            fixture["default_host"], fixture["api_host_override"]))
                    else:
                        with self.assertRaises(ValueError):
                            gh.check_deployment_hosts(fixture["default_host"], fixture["api_host_override"])

        def test_runtime_argv_approval_is_independent_of_github_configuration_preflight(self):
            fixtures = host_fixtures
            scratch = Path.cwd() / ".test-scratch" / "gh-policy"
            scratch.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=scratch) as directory:
                config = Path(directory)
                (config / "config.yml").write_text("{}\n")
                for fixture in fixtures:
                    with self.subTest(name=fixture["name"]):
                        (config / "hosts.yml").write_text(fixture["hosts_yaml"])
                        with patch.dict(os.environ, {"GH_CONFIG_DIR": str(config)}):
                            self.assert_allowed()

    suite = unittest.TestLoader().loadTestsFromTestCase(GitHubArgvTests)
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
