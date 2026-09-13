import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tracemalloc
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bin"))
import validate_bash as gate


class LiteralParserTests(unittest.TestCase):
    def assert_rejected(self, command, code="SHELL_UNSUPPORTED"):
        with self.assertRaises(ValueError) as caught:
            gate.parse(command)
        self.assertEqual(caught.exception.code, code)

    def test_ordered_arguments_include_options_and_the_option_separator(self):
        self.assertEqual(gate.parse("git -x value --name=value -- -z tail"),
                         ["git", "-x", "value", "--name=value", "--", "-z", "tail"])

    def test_space_and_tab_separate_words(self):
        self.assertEqual(gate.parse(" \tgit\t status  "), ["git", "status"])

    def test_empty_arguments_and_adjacent_quote_fragments(self):
        for command, expected in (
            ("git '' \"\"", ["git", "", ""]),
            ("g'it' st\"at\"us", ["git", "status"]),
            ("git a''b\"\"c", ["git", "abc"]),
            ("git ''\"\"", ["git", ""]),
        ):
            with self.subTest(command=command):
                self.assertEqual(gate.parse(command), expected)

    def test_quoted_and_escaped_operator_arguments_are_literal(self):
        for operator in (";", "|", "&", "<", ">", "(", ")"):
            for argument in (f"'{operator}'", f'"{operator}"', "\\" + operator):
                with self.subTest(argument=argument):
                    self.assertEqual(gate.parse("git " + argument), ["git", operator])

    def test_posix_backslash_rules(self):
        for source, expected in (
            (r"git foo\ bar", ["git", "foo bar"]),
            (r"git a\\b", ["git", "a\\b"]),
            (r'''git "a\"b\\c"''', ["git", 'a"b\\c']),
            (r'''git "\q"''', ["git", "\\q"]),
            (r"git 'a\b'", ["git", "a\\b"]),
        ):
            with self.subTest(source=source):
                self.assertEqual(gate.parse(source), expected)

    def test_single_quoted_and_escaped_dollar_and_backticks_are_literal(self):
        for source, value in (
            ("'$HOME'", "$HOME"), (r"\$HOME", "$HOME"),
            (r'''"\$HOME"''', "$HOME"), ("'`id`'", "`id`"),
            (r"\`id\`", "`id`"), (r'''"\`id\`"''', "`id`"),
            ("'$(id)'", "$(id)"), ("'${HOME}'", "${HOME}"),
        ):
            with self.subTest(source=source):
                self.assertEqual(gate.parse("git " + source), ["git", value])

    def test_active_expansions_are_rejected(self):
        for value in ("$HOME", '"$HOME"', "`id`", '"`id`"', "$(id)",
                      '"$(id)"', "${HOME}", "$((1+1))", "$'x'", '$"x"', "$", "$$"):
            with self.subTest(value=value):
                self.assert_rejected("git " + value)

    def test_all_unquoted_command_operators_are_rejected(self):
        for source in ("git;git", "git | git", "git && git", "git || git",
                       "git &", "git >out", "git 2>&1", "git <in", "(git)",
                       "git <<EOF", "git <<<x", "git <(git)", "git >(git)"):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_redirect_spellings_and_missing_targets_are_rejected(self):
        for source in ("git >>out", "git 1>out", "git 2>>err", "git 0<in",
                       "git &>all", "git 1>&2", "git >", "git > >",
                       "git >&1", "git 3>&1", "git 2>&", "git 2>&x",
                       "git <>file", "git >>>file", "git >|file"):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_embedded_operator_text_in_filter_arguments_remains_literal(self):
        for command, expected in (
            ("gh api repo --jq '.x > 0'", ["gh", "api", "repo", "--jq", ".x > 0"]),
            ("jq '[.[] | select(.n >= 5)]'", ["jq", "[.[] | select(.n >= 5)]"]),
            ("git '<div>' 'a&&b' 'a>>b' 'a||b'", ["git", "<div>", "a&&b", "a>>b", "a||b"]),
        ):
            with self.subTest(command=command):
                self.assertEqual(gate.parse(command), expected)

    def test_unquoted_newlines_carriage_returns_and_continuations_are_rejected(self):
        for source in ("git\nstatus", "git\rstatus", "\ngit", "git\n", "git\r",
                       "git \\\nstatus", 'git "a\\\nb"', "git \\\rstatus"):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_quoted_newline_and_carriage_return_are_literal(self):
        for quote in ("'", '"'):
            self.assertEqual(gate.parse("git " + quote + "a\nb\rc" + quote),
                             ["git", "a\nb\rc"])

    def test_unquoted_globs_braces_tilde_hash_and_history_expansion_are_rejected(self):
        for value in ("*", "a?b", "[ab]", "a]", "{a,b}", "~", "a~b", "!", "a!b", "#", "a#b"):
            with self.subTest(value=value):
                self.assert_rejected("git " + value)
                self.assertEqual(gate.parse("git '" + value + "'"), ["git", value])

    def test_equals_expansion_tracks_the_first_decoded_character(self):
        for value in ("=sh", "=s'h'", "''=sh", '""=sh', "''\"\"=sh"):
            with self.subTest(value=value):
                self.assert_rejected("git " + value)
        for value in ("'=sh'", '"=sh"', r"\=sh", "'='sh", "''\\=sh"):
            with self.subTest(value=value):
                self.assertEqual(gate.parse("git " + value), ["git", "=sh"])
        self.assertEqual(gate.parse("git x=sh --name=value a''=sh"),
                         ["git", "x=sh", "--name=value", "a=sh"])

    def test_assignment_commands_and_prefixes_are_rejected(self):
        for source in ("FOO=x git status", "FOO=x", "_A1=x git", "'FOO=x' git", "A= git"):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_shell_reserved_words_are_rejected_as_the_executable(self):
        for word in ("if", "then", "else", "elif", "fi", "for", "while", "until",
                     "do", "done", "case", "esac", "in", "select", "function",
                     "time", "coproc", "{", "}", "!", "[[", "]]"):
            with self.subTest(word=word):
                self.assert_rejected("'" + word + "'")

    def test_paths_and_wrappers_keep_their_own_executable_identity(self):
        self.assertEqual(gate.parse("/usr/bin/git status"), ["/usr/bin/git", "status"])
        self.assertEqual(gate.parse("env git status"), ["env", "git", "status"])

    def test_malformed_empty_and_control_character_input_is_rejected(self):
        for source in ("", " \t", "''", "git 'x", 'git "x', "git x\\", "git\x00x",
                       "git\x01x", "git\x0bx", "git\x0cx", "git\x7fx"):
            with self.subTest(source=source):
                self.assert_rejected(source)
        for value in (None, 1, [], {}):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    gate.parse(value)

    def test_command_byte_limit_and_argument_limit_include_the_executable(self):
        command = "git " + "x" * (65536 - 4)
        self.assertEqual(gate.parse(command), ["git", command[4:]])
        self.assert_rejected(command + "x", "EVALUATION_LIMIT")
        self.assert_rejected("git " + "界" * 21845, "EVALUATION_LIMIT")
        self.assertEqual(len(gate.parse("git" + " x" * 1023)), 1024)
        self.assert_rejected("git" + " x" * 1024, "EVALUATION_LIMIT")


class MatchingTests(unittest.TestCase):
    def test_exact_rules_match_the_entire_argument_vector(self):
        rule = ["git", "status"]
        for argv, expected in ((["git", "status"], True), (["git"], False),
                               (["git", "status", "--short"], False),
                               (["git", "statusx"], False), (["git", "status --short"], False),
                               (["Git", "status"], False)):
            with self.subTest(argv=argv):
                self.assertIs(gate.match_argv(argv, rule), expected)

    def test_double_star_matches_zero_or_more_whole_arguments(self):
        for argv in (["git", "add"], ["git", "add", ""], ["git", "add", "a", "b"]):
            self.assertTrue(gate.match_argv(argv, ["git", "add", "**"]))
        self.assertTrue(gate.match_argv(["git", "end"], ["git", "**", "end"]))
        self.assertTrue(gate.match_argv(["git", "a", "end"], ["git", "**", "**", "end"]))
        self.assertFalse(gate.match_argv(["git", "end", "extra"], ["git", "**", "end"]))

    def test_single_star_matches_within_one_argument_including_empty(self):
        for value in ("", "abc", "a b"):
            self.assertTrue(gate.match_argv(["git", value], ["git", "*"]))
        self.assertFalse(gate.match_argv(["git"], ["git", "*"]))
        self.assertFalse(gate.match_argv(["git", "a", "b"], ["git", "*"]))
        self.assertTrue(gate.match_argv(["git", "abMIDcd"], ["git", "ab*cd"]))
        self.assertFalse(gate.match_argv(["git", "abMIDce"], ["git", "ab*cd"]))

    def test_nonstar_metacharacters_are_literal(self):
        for value in ("?", "[ab]", "{a,b}", ".+", "^x$", "a\\b", "", "界"):
            with self.subTest(value=value):
                self.assertTrue(gate.match_argv(["git", value], ["git", value]))
                self.assertFalse(gate.match_argv(["git", value + "x"], ["git", value]))

    def test_embedded_repeated_stars_are_character_patterns(self):
        self.assertTrue(gate.match_argv(["git", "ab"], ["git", "a**b"]))
        self.assertFalse(gate.match_argv(["git", "a", "b"], ["git", "a**b"]))

    def test_seed_overlap_and_native_only_cases(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/command_policy_seed.json").read_text())
        for case in fixture["command_cases"]:
            with self.subTest(argv=case["argv"]):
                command = " ".join("'" + arg + "'" for arg in case["argv"])
                if case["decision"] == "allow":
                    self.assertEqual(gate.evaluate(command, fixture["expected"]), "allow")
                else:
                    with self.assertRaises(gate.PolicyError) as caught:
                        gate.evaluate(command, fixture["expected"])
                    self.assertEqual(caught.exception.code, case["decision"])

    def test_block_precedes_allow_and_empty_allow_blocks_every_command(self):
        for policy, expected in (
            ({"version": 1, "allow": [["git", "**"]], "block": [["git", "status"]]}, "RULE_BLOCK"),
            ({"version": 1, "allow": [], "block": []}, "RULE_UNMATCHED"),
        ):
            with self.subTest(policy=policy):
                with self.assertRaises(gate.PolicyError) as caught:
                    gate.evaluate("git status", policy)
                self.assertEqual(caught.exception.code, expected)

    def test_executable_paths_wrappers_and_case_receive_no_inherited_authority(self):
        policy = {"version": 1, "allow": [["git", "status"]], "block": []}
        for command in ("/usr/bin/git status", "env git status", "Git status"):
            with self.subTest(command=command):
                with self.assertRaises(gate.PolicyError) as caught:
                    gate.evaluate(command, policy)
                self.assertEqual(caught.exception.code, "RULE_UNMATCHED")

    def test_parser_and_matcher_consume_the_supplied_shared_budget(self):
        budget = gate.EvaluationBudget()
        before = budget.remaining
        argv = gate.parse("git status", budget=budget)
        after_parse = budget.remaining
        self.assertLess(after_parse, before)
        self.assertTrue(gate.match_argv(argv, ["git", "status"], budget=budget))
        self.assertLess(budget.remaining, after_parse)

    def test_exhausted_budget_stops_parser_and_matcher(self):
        for operation in (
            lambda budget: gate.parse("git status", budget=budget),
            lambda budget: gate.match_argv(["git", "status"], ["git", "**"], budget=budget),
        ):
            with self.subTest(operation=operation):
                with self.assertRaises(gate.PolicyError) as caught:
                    operation(gate.EvaluationBudget(limit=0))
                self.assertEqual(caught.exception.code, "EVALUATION_LIMIT")

    def test_adversarial_character_and_argument_products_exhaust_budget(self):
        for argv, rule in (
            (["git", "a" * 4096], ["git", "*a" * 2047 + "b"]),
            (["git"] + ["a"] * 1023, ["git"] + ["**", "a"] * 63 + ["b"]),
        ):
            with self.subTest(kind=len(argv)):
                with self.assertRaises(gate.PolicyError) as caught:
                    gate.match_argv(argv, rule, budget=gate.EvaluationBudget(limit=5000))
                self.assertEqual(caught.exception.code, "EVALUATION_LIMIT")

    def test_failed_comparisons_across_rules_share_the_budget(self):
        policy = {"version": 1, "allow": [["git", "*" + str(i)] for i in range(500)], "block": []}
        with self.assertRaises(gate.PolicyError) as caught:
            gate.evaluate("git " + "a" * 1000, policy, budget=gate.EvaluationBudget(limit=20000))
        self.assertEqual(caught.exception.code, "EVALUATION_LIMIT")

    def test_matching_scratch_space_is_bounded(self):
        argv = ["git"] + ["a"] * 1023
        rule = ["git"] + ["**", "a"] * 63 + ["**"]
        budget = gate.EvaluationBudget()
        tracemalloc.start()
        try:
            self.assertTrue(gate.match_argv(argv, rule, budget=budget))
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLessEqual(peak, 256 * 1024)

    def test_monotonic_deadline_is_checked_within_1024_units(self):
        budget = gate.EvaluationBudget(deadline=time.monotonic() - 1)
        with self.assertRaises(gate.PolicyError) as caught:
            gate.parse("git " + "a" * 2048, budget=budget)
        self.assertEqual(caught.exception.code, "EVALUATION_LIMIT")


class ShellConformanceTests(unittest.TestCase):
    def test_harmless_argv_fixtures_match_clean_bash_and_zsh(self):
        cases = [
            ("'' \"\"", ["", ""]),
            ("a'b'\"c\" 'x y'", ["abc", "x y"]),
            (r'''\; '|' "&" \< \>''', [";", "|", "&", "<", ">"]),
            (r'''"\$HOME" '`id`' "\q"''', ["$HOME", "`id`", "\\q"]),
            (r''' '=sh' "=sh" \=sh '='sh ''\=sh''', ["=sh"] * 5),
            ("x=sh --name=value a''=sh", ["x=sh", "--name=value", "a=sh"]),
            ("'a\nb'", ["a\nb"]),
        ]
        for shell in (["/bin/bash", "--noprofile", "--norc"], ["/bin/zsh", "-f"]):
            for arguments, expected in cases:
                with self.subTest(shell=shell[0], arguments=arguments):
                    command = "printf '%s\\0' " + arguments
                    result = subprocess.run(shell + ["-c", command], capture_output=True, timeout=3)
                    self.assertEqual(result.returncode, 0, result.stderr.decode())
                    self.assertEqual(result.stderr, b"")
                    actual = result.stdout.decode().split("\0")[:-1]
                    self.assertEqual(actual, expected)
                    self.assertEqual(gate.parse(command), ["printf", "%s\\0"] + actual)


class EvaluationDeadlineTests(unittest.TestCase):
    def assert_limit_denial(self, result):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.startswith("BLOCKED [EVALUATION_LIMIT]:"), result.stderr)

    def test_stalled_stdin_denies_within_three_seconds(self):
        started = time.monotonic()
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "bin/validate_bash.py"), "validate", "--client", "codex"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            process.wait(timeout=3)
            output, error = process.communicate()
            self.assertLess(time.monotonic() - started, 3)
            self.assert_limit_denial(subprocess.CompletedProcess(process.args, process.returncode, output, error))
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()

    def test_near_limit_wildcard_evaluation_denies_within_three_seconds(self):
        scratch = ROOT / ".test-scratch" / "command-policy"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as home:
            policy_path = Path(home) / ".config/himkt/accepts.jsonc"
            policy_path.parent.mkdir(parents=True)
            policy_path.write_text(json.dumps({
                "version": 1,
                "allow": [["git", "*a" * 2000 + str(i)] for i in range(100)],
                "block": [],
            }))
            envelope = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                        "tool_input": {"command": "git " + "a" * 4000}}
            started = time.monotonic()
            result = subprocess.run(
                [sys.executable, str(ROOT / "bin/validate_bash.py"), "validate", "--client", "codex"],
                input=json.dumps(envelope), capture_output=True, text=True, timeout=3,
                env=dict(os.environ, HOME=home),
            )
            self.assertLess(time.monotonic() - started, 3)
            self.assert_limit_denial(result)


if __name__ == "__main__":
    unittest.main()
