import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bin"))
import validate_bash as gate


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/command_policy_seed.json").read_text()
)
EMPTY = {"version": 1, "allow": [], "block": []}


class SeedContractTests(unittest.TestCase):
    def test_fixture_accounts_for_every_source_bash_entry(self):
        settings = json.loads((ROOT / "claude/settings.json").read_text())
        actual = [
            (category, entry)
            for category in ("allow", "deny", "ask")
            for entry in settings["permissions"][category]
            if entry.startswith("Bash(")
        ]
        recorded = [(entry["category"], entry["source"]) for entry in FIXTURE["entries"]]
        self.assertCountEqual(recorded, actual)
        self.assertEqual(len(recorded), 62)

    def test_fixture_records_the_complete_normalized_policy(self):
        result = {"version": 1, "allow": [], "block": []}
        for entry in FIXTURE["entries"]:
            expected_target = "allow" if entry["category"] == "allow" else "block"
            self.assertEqual(entry["target"], expected_target)
            for rule in entry["rules"]:
                if rule not in result[expected_target]:
                    result[expected_target].append(rule)
        self.assertEqual(result, FIXTURE["expected"])
        self.assertEqual(len(result["allow"]), 43)
        self.assertEqual(len(result["block"]), 18)

    def test_source_translation_preserves_exact_rules_and_argument_boundaries(self):
        for entry in FIXTURE["entries"]:
            with self.subTest(source=entry["source"]):
                if entry["source"].startswith("Bash(cafleet member prompt "):
                    self.assertEqual(entry["rules"], [
                        ["cafleet", "member", "prompt", "**", "--shell", "**"],
                        ["cafleet", "member", "prompt", "**", "--shell=*", "**"],
                    ])
                else:
                    self.assertEqual(entry["rules"], [[
                        "**" if token == "*" else token
                        for token in entry["source"][5:-1].split(" ")
                    ]])

    def test_translator_matches_reviewed_seed(self):
        settings = json.loads((ROOT / "claude/settings.json").read_text())
        self.assertEqual(gate.translate_seed(settings), FIXTURE["expected"])

    def test_cafleet_shell_exceptions_overlap_the_broad_allow(self):
        policy = FIXTURE["expected"]
        self.assertIn(["cafleet", "**"], policy["allow"])
        self.assertIn(["cafleet", "member", "prompt", "**", "--shell", "**"], policy["block"])
        self.assertIn(["cafleet", "member", "prompt", "**", "--shell=*", "**"], policy["block"])

    def test_native_only_executable_is_absent_from_shared_allow(self):
        self.assertTrue(all(rule[0] != "herdr" for rule in FIXTURE["expected"]["allow"]))
        self.assertIn(
            {"argv": ["herdr", "pane", "read", "1"], "decision": "RULE_UNMATCHED"},
            FIXTURE["command_cases"],
        )

    def test_translator_collapses_identical_rules_and_excludes_other_tools(self):
        settings = {"permissions": {
            "allow": ["Edit", "Bash(git status)", "Bash(git status)", "Read(/x)"],
            "deny": ["Bash(git push *)"],
            "ask": ["Bash(git push *)", "Write"],
        }}
        self.assertEqual(gate.translate_seed(settings), {
            "version": 1, "allow": [["git", "status"]],
            "block": [["git", "push", "**"]],
        })

    def test_translator_fails_visibly_for_unsupported_source_syntax(self):
        for source in (
            "Bash(git status", "Bash(git status; echo x)",
            "Bash(git 'status')", "Bash(git $OPTION)",
            "Bash(git status\nwhoami)", "Bash(/usr/bin/git status)",
        ):
            with self.subTest(source=source):
                settings = {"permissions": {"allow": [source], "deny": [], "ask": []}}
                with self.assertRaises(ValueError):
                    gate.translate_seed(settings)


class PolicyLoadingTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".test-scratch" / "command-policy"
        scratch.mkdir(parents=True, exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.path = self.home / ".config/himkt/accepts.jsonc"
        self.path.parent.mkdir(parents=True)
        self.environment = patch.dict(os.environ, {"HOME": str(self.home)})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def write_policy(self, policy):
        self.path.write_text(json.dumps(policy), encoding="utf-8")

    def assert_policy_error(self, code="POLICY_INVALID"):
        with self.assertRaises(ValueError) as caught:
            gate.load_policy()
        self.assertEqual(caught.exception.code, code)

    def test_empty_lists_are_a_valid_policy(self):
        self.write_policy(EMPTY)
        self.assertEqual(gate.load_policy(), EMPTY)

    def test_complete_seed_is_a_valid_policy(self):
        self.write_policy(FIXTURE["expected"])
        self.assertEqual(gate.load_policy(), FIXTURE["expected"])

    def test_jsonc_comments_trailing_commas_and_string_escapes(self):
        self.path.write_text(r'''
// leading comment
{
  "version": 1, /* comment */
  "allow": [["printf", "https://a/*b*/", "quote\"//x", "slash\\",],],
  "block": [], // trailing field
}
''')
        self.assertEqual(gate.load_policy(), {
            "version": 1,
            "allow": [["printf", "https://a/*b*/", 'quote"//x', "slash\\"]],
            "block": [],
        })

    def test_comment_between_trailing_comma_and_closing_token(self):
        self.path.write_text(
            '{"version":1,"allow":[["git", /* a */], /* b */],"block":[], /* c */}'
        )
        self.assertEqual(gate.load_policy(), {"version": 1, "allow": [["git"]], "block": []})

    def test_comments_are_whitespace_and_preserve_token_boundaries(self):
        for text in (
            '{"version":1/*x*/0,"allow":[],"block":[]}',
            '{"version":1,"allow":[["g"/*x*/"it"]],"block":[]}',
        ):
            with self.subTest(text=text):
                self.path.write_text(text)
                self.assert_policy_error()

    def test_jsonc_rejects_malformed_separators_and_incomplete_tokens(self):
        for text in (
            '{"version":1,"allow":[,],"block":[]}',
            '{"version":1,"allow":[],"block":[],,}',
            '{,"version":1,"allow":[],"block":[]}',
            '{"version":1 "allow":[],"block":[]}',
            '{"version":1,"allow":[["git",,]],"block":[]}',
            '{"version":1,"allow":[],"block":[]} /* unfinished',
            '{"version":1,"allow":[["unfinished]],"block":[]}',
            '{"version":1,"allow":[],"block":[]} true',
            '{"version":1,"allow":[],"block":[]} /* outer /* inner */ */',
            "{'version':1,'allow':[],'block':[]}",
            '{version:1,"allow":[],"block":[]}',
        ):
            with self.subTest(text=text):
                self.path.write_text(text)
                self.assert_policy_error()

    def test_schema_requires_exact_keys_and_types(self):
        cases = [None, [], 1, True, "policy"]
        for key in EMPTY:
            missing = dict(EMPTY)
            del missing[key]
            cases.append(missing)
        cases.append(dict(EMPTY, extra=[]))
        cases.extend(dict(EMPTY, version=value) for value in (True, False, 0, 2, 1.0, "1", None))
        for key in ("allow", "block"):
            cases.extend(dict(EMPTY, **{key: value}) for value in (None, {}, "git", True, 1))
        for policy in cases:
            with self.subTest(policy=policy):
                self.write_policy(policy)
                self.assert_policy_error()

    def test_duplicate_keys_and_nonfinite_numbers_are_errors(self):
        for text in (
            '{"version":1,"version":1,"allow":[],"block":[]}',
            '{"version":1,"allow":[],"allow":[],"block":[]}',
            '{"version":NaN,"allow":[],"block":[]}',
            '{"version":Infinity,"allow":[],"block":[]}',
            '{"version":-Infinity,"allow":[],"block":[]}',
        ):
            with self.subTest(text=text):
                self.path.write_text(text)
                self.assert_policy_error()

    def test_rules_require_nonempty_arrays_and_literal_executable_names(self):
        for rule in (
            [], "git", None, [None], [True], [1], [""], ["/usr/bin/git"],
            ["./git"], ["git*"], ["**"], ["git", None], ["git", 1],
            ["git", True], ["git", []], ["git", {}],
        ):
            for target in ("allow", "block"):
                with self.subTest(rule=rule, target=target):
                    self.write_policy(dict(EMPTY, **{target: [rule]}))
                    self.assert_policy_error()

    def test_argument_patterns_preserve_empty_strings_and_literal_characters(self):
        policy = dict(EMPTY, allow=[["printf", "", "a*b", "**", "?[]{}$;", "日本語"]])
        self.write_policy(policy)
        self.assertEqual(gate.load_policy(), policy)

    def test_duplicate_rules_are_errors_in_each_list(self):
        for target in ("allow", "block"):
            with self.subTest(target=target):
                self.write_policy(dict(EMPTY, **{target: [["git"], ["git"]]}))
                self.assert_policy_error()

    def test_invalid_utf8_and_unpaired_unicode_surrogates_are_errors(self):
        for content in (
            b'{"version":1,"allow":[["git","\xff"]],"block":[]}',
            b'{"version":1,"allow":[["git","\\ud800"]],"block":[]}',
            b'{"version":1,"allow":[["git","\\udfff"]],"block":[]}',
            b'{"version":1,"allow":[["git","\xed\xa0\x80"]],"block":[]}',
        ):
            with self.subTest(content=content):
                self.path.write_bytes(content)
                self.assert_policy_error()

    def test_valid_unicode_surrogate_pair_decodes_to_scalar(self):
        self.path.write_bytes(b'{"version":1,"allow":[["git","\\ud83d\\ude00"]],"block":[]}')
        self.assertEqual(gate.load_policy()["allow"], [["git", "😀"]])

    def test_policy_size_limit_accepts_one_mib_and_rejects_one_extra_byte(self):
        data = json.dumps(EMPTY).encode()
        self.path.write_bytes(data + b" " * (1024 * 1024 - len(data)))
        self.assertEqual(gate.load_policy(), EMPTY)
        self.path.write_bytes(data + b" " * (1024 * 1024 + 1 - len(data)))
        self.assert_policy_error("EVALUATION_LIMIT")

    def test_total_rule_limit_is_shared_by_allow_and_block(self):
        policy = dict(EMPTY, allow=[["git", str(i)] for i in range(512)],
                      block=[["git", str(i)] for i in range(512, 1024)])
        self.write_policy(policy)
        self.assertEqual(gate.load_policy(), policy)
        policy["block"].append(["git", "1024"])
        self.write_policy(policy)
        self.assert_policy_error("EVALUATION_LIMIT")

    def test_rule_element_limit_includes_the_executable(self):
        policy = dict(EMPTY, allow=[["git"] + ["x"] * 127])
        self.write_policy(policy)
        self.assertEqual(gate.load_policy(), policy)
        policy["allow"][0].append("x")
        self.write_policy(policy)
        self.assert_policy_error("EVALUATION_LIMIT")

    def test_element_character_limit_uses_decoded_characters(self):
        for value in ("x" * 4096, "界" * 4096):
            with self.subTest(value=value[:1]):
                policy = dict(EMPTY, allow=[["git", value]])
                self.write_policy(policy)
                self.assertEqual(gate.load_policy(), policy)
                policy["allow"][0][1] += "x"
                self.write_policy(policy)
                self.assert_policy_error("EVALUATION_LIMIT")

    def test_excessive_nesting_denies_before_json_decode(self):
        self.path.write_text("[" * 10000 + "]" * 10000)
        self.assert_policy_error("EVALUATION_LIMIT")

    def test_missing_policy_is_explicit(self):
        self.assert_policy_error("POLICY_MISSING")

    def test_unreadable_policy_is_explicit(self):
        self.write_policy(EMPTY)
        self.path.chmod(0)
        self.addCleanup(self.path.chmod, 0o600)
        self.assert_policy_error()

    def test_regular_file_symlink_is_supported(self):
        target = self.home / "policy.json"
        target.write_text(json.dumps(EMPTY))
        self.path.symlink_to(target)
        self.assertEqual(gate.load_policy(), EMPTY)

    def test_directory_is_rejected(self):
        self.path.mkdir()
        self.assert_policy_error()

    def test_device_is_rejected(self):
        self.path.symlink_to("/dev/null")
        self.assert_policy_error()

    def test_socket_is_rejected(self):
        with socket.socket(socket.AF_UNIX) as endpoint:
            short_path = self.home / "socket"
            endpoint.bind(str(short_path))
            self.path.symlink_to(short_path)
            self.assert_policy_error()

    def test_fifo_is_rejected_promptly_without_a_writer(self):
        os.mkfifo(self.path)
        code = (
            "import sys\nsys.path.insert(0, sys.argv[1])\nimport validate_bash as gate\n"
            "try:\n    gate.load_policy()\n"
            "except ValueError as error:\n    print(error.code)\n    sys.exit(2)\n"
        )
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-c", code, str(ROOT / "bin")],
            capture_output=True, text=True, timeout=3,
        )
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.strip(), "POLICY_INVALID")
        self.assertEqual(result.stderr, "")

    def test_fixed_home_path_is_independent_of_working_directory(self):
        self.write_policy(EMPTY)
        project = self.home / "project"
        project.mkdir()
        (project / "accepts.jsonc").write_text("invalid")
        original = Path.cwd()
        try:
            os.chdir(project)
            self.assertEqual(gate.load_policy(), EMPTY)
        finally:
            os.chdir(original)

    def test_each_invocation_reads_the_current_policy(self):
        policy = copy.deepcopy(EMPTY)
        self.write_policy(policy)
        self.assertEqual(gate.load_policy(), policy)
        policy["allow"] = [["git", "status"]]
        self.write_policy(policy)
        self.assertEqual(gate.load_policy(), policy)
        self.path.write_text("invalid")
        self.assert_policy_error()
        self.path.unlink()
        self.assert_policy_error("POLICY_MISSING")


if __name__ == "__main__":
    unittest.main()
