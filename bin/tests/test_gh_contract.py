import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bin"))
import validate_bash as gate
import validate_gh_api as gh


COMMENTS = "repos/himkt/config/issues/1/comments"
COMMENT = "repos/himkt/config/issues/comments/9"
CONTENTS = "repos/himkt/config/contents/README.md"


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
        scratch = ROOT / ".test-scratch" / "gh-policy"
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
        fixtures = json.loads((Path(__file__).parent / "fixtures/gh_deployment_hosts.json").read_text())
        for fixture in fixtures:
            with self.subTest(name=fixture["name"]):
                if fixture["trusted"]:
                    self.assertIsNone(gh.check_deployment_hosts(
                        fixture["default_host"], fixture["api_host_override"]))
                else:
                    with self.assertRaises(ValueError):
                        gh.check_deployment_hosts(fixture["default_host"], fixture["api_host_override"])

    def test_runtime_argv_approval_is_independent_of_github_configuration_preflight(self):
        fixtures = json.loads((Path(__file__).parent / "fixtures/gh_deployment_hosts.json").read_text())
        scratch = ROOT / ".test-scratch" / "gh-policy"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            config = Path(directory)
            (config / "config.yml").write_text("{}\n")
            for fixture in fixtures:
                with self.subTest(name=fixture["name"]):
                    (config / "hosts.yml").write_text(fixture["hosts_yaml"])
                    with patch.dict(os.environ, {"GH_CONFIG_DIR": str(config)}):
                        self.assert_allowed()


if __name__ == "__main__":
    unittest.main()
