#!/usr/bin/env python3

"""Literal command parsing and shared command policy evaluation."""

import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time


MAX_POLICY_BYTES = 1024 * 1024


class PolicyError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class EvaluationBudget:
    def __init__(self, limit=8_000_000, deadline=None):
        self.remaining = limit
        self.deadline = deadline
        self.until_clock_check = 1024

    def charge(self, units=1):
        self.remaining -= units
        self.until_clock_check -= units
        if self.remaining < 0:
            raise PolicyError("EVALUATION_LIMIT", "Evaluation work limit exceeded")
        if self.until_clock_check <= 0:
            self.check_deadline()
            self.until_clock_check = 1024

    def check_deadline(self):
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise PolicyError("EVALUATION_LIMIT", "Evaluation deadline exceeded")


def _invalid_policy(message):
    raise PolicyError("POLICY_INVALID", message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _invalid_policy("Duplicate object key")
        result[key] = value
    return result


def _jsonc_text(text, budget):
    cleaned = list(text)
    state = "plain"
    depth = 0
    escaped = False
    i = 0
    while i < len(text):
        budget.charge()
        char = text[i]
        following = text[i + 1] if i + 1 < len(text) else ""
        if state == "string":
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                state = "plain"
        elif state in ("line", "block"):
            cleaned[i] = char if char in "\r\n" else " "
            if state == "line" and char in "\r\n":
                state = "plain"
            elif state == "block" and char == "/" and following == "*":
                _invalid_policy("Nested comments are unsupported")
            elif state == "block" and char == "*" and following == "/":
                budget.charge()
                cleaned[i + 1] = " "
                i += 1
                state = "plain"
        elif char == '"':
            state = "string"
        elif char == "/" and following in ("/", "*"):
            budget.charge()
            cleaned[i] = cleaned[i + 1] = " "
            i += 1
            state = "line" if following == "/" else "block"
        elif char in "[{":
            depth += 1
            if depth > 8:
                raise PolicyError("EVALUATION_LIMIT", "JSON nesting limit exceeded")
        elif char in "]}":
            depth -= 1
        i += 1
    if state in ("string", "block"):
        _invalid_policy("Unterminated string or comment")

    in_string = False
    escaped = False
    previous = None
    before_comma = None
    comma_index = None
    for i, char in enumerate(cleaned):
        budget.charge()
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                previous = '"'
            continue
        if char in " \t\r\n":
            continue
        if char in "]}" and previous == "," and before_comma not in (None, "[", "{", ",", ":"):
            cleaned[comma_index] = " "
        if char == ",":
            comma_index = i
            before_comma = previous
        if char == '"':
            in_string = True
        previous = char
    return "".join(cleaned)


def validate_policy(policy, budget=None):
    if budget is None:
        budget = EvaluationBudget()
    if not isinstance(policy, dict) or set(policy) != {"version", "allow", "block"}:
        _invalid_policy("Policy requires version, allow, and block")
    if type(policy["version"]) is not int or policy["version"] != 1:
        _invalid_policy("Policy version must be integer 1")
    for category in ("allow", "block"):
        if not isinstance(policy[category], list):
            _invalid_policy("Policy rule collections must be arrays")
    if len(policy["allow"]) + len(policy["block"]) > 1024:
        raise PolicyError("EVALUATION_LIMIT", "Policy rule limit exceeded")
    for category in ("allow", "block"):
        seen = set()
        for rule in policy[category]:
            budget.charge()
            if not isinstance(rule, list) or not rule:
                _invalid_policy("Rules must be nonempty arrays")
            if len(rule) > 128:
                raise PolicyError("EVALUATION_LIMIT", "Rule element limit exceeded")
            for element in rule:
                if not isinstance(element, str):
                    _invalid_policy("Rule elements must be strings")
                if len(element) > 4096:
                    raise PolicyError("EVALUATION_LIMIT", "Rule character limit exceeded")
                for char in element:
                    budget.charge()
                    if 0xD800 <= ord(char) <= 0xDFFF:
                        _invalid_policy("Policy contains invalid Unicode")
            if not rule[0] or "/" in rule[0] or "*" in rule[0]:
                _invalid_policy("Executable must be a literal name without slashes")
            identity = tuple(rule)
            budget.charge(sum(map(len, rule)))
            if identity in seen:
                _invalid_policy("Duplicate policy rule")
            seen.add(identity)
    return policy


def load_policy(budget=None):
    if budget is None:
        budget = EvaluationBudget()
    path = Path.home() / ".config/himkt/accepts.jsonc"
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                _invalid_policy("Policy must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                content = stream.read(MAX_POLICY_BYTES + 1)
        finally:
            os.close(descriptor)
        if len(content) > MAX_POLICY_BYTES:
            raise PolicyError("EVALUATION_LIMIT", "Policy byte limit exceeded")
        budget.charge(len(content))
        text = content.decode("utf-8", errors="strict")
        policy = json.loads(
            _jsonc_text(text, budget), object_pairs_hook=_unique_object,
            parse_constant=lambda value: _invalid_policy("Nonfinite JSON number"),
        )
        return validate_policy(policy, budget)
    except FileNotFoundError as error:
        raise PolicyError("POLICY_MISSING", f"Repair policy at {path}: file missing") from error
    except PolicyError as error:
        raise PolicyError(error.code, f"Repair policy at {path}: {error}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PolicyError("POLICY_INVALID", f"Repair policy at {path}: unreadable or invalid policy") from error


def translate_seed(settings):
    if not isinstance(settings, dict) or not isinstance(settings.get("permissions"), dict):
        raise ValueError("Seed requires permissions")
    policy = {"version": 1, "allow": [], "block": []}
    exceptions = {
        "cafleet member prompt * --shell *",
        "cafleet member prompt * --shell",
        "cafleet member prompt --shell *",
    }
    for category in ("allow", "deny", "ask"):
        entries = settings["permissions"].get(category)
        if not isinstance(entries, list) or any(not isinstance(entry, str) for entry in entries):
            raise ValueError("Seed permission categories must be string arrays")
        target = "allow" if category == "allow" else "block"
        for entry in entries:
            if not entry.startswith("Bash("):
                continue
            if not entry.endswith(")"):
                raise ValueError("Incomplete Bash seed entry")
            source = entry[5:-1]
            if not re.fullmatch(r"[A-Za-z0-9_.*= /-]+", source):
                raise ValueError("Unsupported Bash seed syntax")
            tokens = source.split(" ")
            if any(not token for token in tokens):
                raise ValueError("Seed requires single-space argument separators")
            if source in exceptions and target == "block":
                rules = [["cafleet", "member", "prompt", "**", flag, "**"]
                         for flag in ("--shell", "--shell=*")]
            else:
                rules = [["**" if token == "*" else token for token in tokens]]
            for rule in rules:
                if rule not in policy[target]:
                    policy[target].append(rule)
    return validate_policy(policy)


_RESERVED_WORDS = frozenset((
    "if", "then", "else", "elif", "fi", "for", "while", "until", "do",
    "done", "case", "esac", "in", "select", "function", "time", "coproc",
    "{", "}", "!", "[[", "]]",
))


def _shell_error(message):
    raise PolicyError("SHELL_UNSUPPORTED", message)


def _check_character(char):
    if (ord(char) < 32 and char not in "\t\r\n") or ord(char) == 127:
        _shell_error("Unsupported control character")
    if 0xD800 <= ord(char) <= 0xDFFF:
        _shell_error("Invalid Unicode")


def parse(command_string, budget=None):
    if budget is None:
        budget = EvaluationBudget()
    if not isinstance(command_string, str):
        _shell_error("Command must be a string")
    if len(command_string) > 65536:
        raise PolicyError("EVALUATION_LIMIT", "Command byte limit exceeded")
    budget.charge(len(command_string))
    try:
        command_bytes = len(command_string.encode("utf-8"))
    except UnicodeError as error:
        raise PolicyError("SHELL_UNSUPPORTED", "Invalid Unicode") from error
    if command_bytes > 65536:
        raise PolicyError("EVALUATION_LIMIT", "Command byte limit exceeded")
    argv = []
    word = []
    started = False
    quote = None
    i = 0

    def finish_word():
        nonlocal started
        if started:
            if len(argv) >= 1024:
                raise PolicyError("EVALUATION_LIMIT", "Argument count limit exceeded")
            argv.append("".join(word))
            word.clear()
            started = False

    while i < len(command_string):
        budget.charge()
        char = command_string[i]
        _check_character(char)
        if quote == "'":
            if char == "'":
                quote = None
            else:
                word.append(char)
        elif char == "\\":
            if i + 1 == len(command_string):
                _shell_error("Incomplete escape")
            budget.charge()
            following = command_string[i + 1]
            _check_character(following)
            if following in "\r\n":
                _shell_error("Line continuation is unsupported")
            if quote == '"' and following not in '$`"\\':
                word.append("\\")
            word.append(following)
            started = True
            i += 1
        elif quote == '"':
            if char == '"':
                quote = None
            elif char in "$`":
                _shell_error("Use quoted or escaped literal arguments")
            else:
                word.append(char)
        elif char in " \t":
            finish_word()
        elif char in "'\"":
            quote = char
            started = True
        elif char in "\r\n;|&<>()$`*?[]{}~!#":
            _shell_error("Use one command with literal arguments")
        elif char == "=" and not word:
            _shell_error("Quote a leading equals sign")
        else:
            word.append(char)
            started = True
        i += 1
    if quote is not None:
        _shell_error("Unterminated quote")
    finish_word()
    if not argv or not argv[0]:
        _shell_error("Executable is required")
    budget.charge(len(argv[0]))
    if argv[0] in _RESERVED_WORDS or re.match(r"[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
        _shell_error("Use an executable followed by literal arguments")
    return argv


def _compile_rule(rule, budget):
    compiled = []
    for pattern in rule:
        characters = []
        has_star = False
        for char in pattern:
            budget.charge()
            if char == "*":
                has_star = True
                if characters and characters[-1] == "*":
                    continue
            characters.append(char)
        compiled.append((pattern == "**", "".join(characters), has_star))
    return compiled


def _match_argument(argument, pattern, has_star, budget):
    if not has_star:
        budget.charge()
        if len(argument) != len(pattern):
            return False
        for left, right in zip(argument, pattern):
            budget.charge()
            if left != right:
                return False
        return True
    previous = bytearray(len(pattern) + 1)
    current = bytearray(len(pattern) + 1)
    previous[0] = 1
    for j, char in enumerate(pattern, 1):
        budget.charge()
        previous[j] = previous[j - 1] if char == "*" else 0
    for char in argument:
        current[0] = 0
        for j, expected in enumerate(pattern, 1):
            budget.charge()
            if expected == "*":
                current[j] = current[j - 1] | previous[j]
            else:
                budget.charge()
                current[j] = previous[j - 1] & (char == expected)
        previous, current = current, previous
    return bool(previous[-1])


def match_argv(argv, rule, budget=None):
    if budget is None:
        budget = EvaluationBudget()
    if not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv):
        raise ValueError("argv must be a nonempty string array")
    if len(argv) > 1024 or sum(len(arg) for arg in argv) > 65536:
        raise PolicyError("EVALUATION_LIMIT", "Argument limits exceeded")
    validate_policy({"version": 1, "allow": [rule], "block": []}, budget)
    compiled = _compile_rule(rule, budget)
    previous = bytearray(len(argv) + 1)
    current = bytearray(len(argv) + 1)
    previous[0] = 1
    for whole_arguments, pattern, has_star in compiled:
        budget.charge()
        current[0] = previous[0] if whole_arguments else 0
        for j, argument in enumerate(argv, 1):
            budget.charge()
            if whole_arguments:
                current[j] = previous[j] | current[j - 1]
            elif previous[j - 1]:
                current[j] = _match_argument(argument, pattern, has_star, budget)
            else:
                current[j] = 0
        previous, current = current, previous
    return bool(previous[-1])


def evaluate(command, policy, budget=None):
    if budget is None:
        budget = EvaluationBudget()
    validate_policy(policy, budget)
    argv = parse(command, budget)
    for rule in policy["block"]:
        if match_argv(argv, rule, budget):
            raise PolicyError("RULE_BLOCK", "Command matches a block rule")
    for rule in policy["allow"]:
        if match_argv(argv, rule, budget):
            if argv[:2] == ["gh", "api"]:
                from validate_gh_api import check_argv

                check_argv(argv, budget)
            return "allow"
    raise PolicyError("RULE_UNMATCHED", f"Review shared policy for executable {argv[0][:80]!r}")


class EvaluationTimeout(PolicyError):
    def __init__(self):
        super().__init__("EVALUATION_LIMIT", "Evaluation deadline exceeded")


def _timeout_handler(signum, frame):
    raise EvaluationTimeout()


def _read_envelope(budget):
    content = sys.stdin.buffer.read(MAX_POLICY_BYTES + 1)
    if len(content) > MAX_POLICY_BYTES:
        raise PolicyError("EVALUATION_LIMIT", "Hook input byte limit exceeded")
    budget.charge(len(content))
    try:
        text = content.decode("utf-8")
        _jsonc_text(text, budget)
        envelope = json.loads(text, object_pairs_hook=_unique_object,
                              parse_constant=lambda value: _invalid_policy("Nonfinite number"))
    except PolicyError as error:
        if error.code == "EVALUATION_LIMIT":
            raise
        raise PolicyError("INPUT_INVALID", "Expected a JSON hook envelope") from error
    except (ValueError, UnicodeError) as error:
        raise PolicyError("INPUT_INVALID", "Expected a JSON hook envelope") from error
    if (not isinstance(envelope, dict)
            or envelope.get("hook_event_name") != "PreToolUse"
            or envelope.get("tool_name") != "Bash"
            or not isinstance(envelope.get("tool_input"), dict)
            or not isinstance(envelope["tool_input"].get("command"), str)
            or not envelope["tool_input"]["command"]):
        raise PolicyError("INPUT_INVALID", "Expected PreToolUse Bash command")
    return envelope["tool_input"]["command"]


def _validate_cli(client=None, github_only=False):
    timer_installed = False
    try:
        deadline = time.monotonic() + 2
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, 2)
        timer_installed = True
        if (github_only and client is not None) or (not github_only and client not in ("codex", "claude")):
            raise ValueError("Select one explicit client or standalone GitHub validation")
        budget = EvaluationBudget(deadline=deadline)
        command = _read_envelope(budget)
        if github_only:
            from validate_gh_api import check_argv

            argv = parse(command, budget)
            if argv[:2] == ["gh", "api"]:
                check_argv(argv, budget)
        else:
            policy = load_policy(budget)
            evaluate(command, policy, budget)
        if client == "claude":
            output = json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "allow",
                "permissionDecisionReason": "Matched shared command policy",
            }}) + "\n"
        else:
            output = ""
        budget.check_deadline()
        signal.setitimer(signal.ITIMER_REAL, 0)
        timer_installed = False
        sys.stdout.write(output)
        return 0
    except PolicyError as error:
        code, message = error.code, str(error)
    except Exception:
        code, message = "INTERNAL_ERROR", "Command evaluation failed"
    finally:
        if timer_installed:
            signal.setitimer(signal.ITIMER_REAL, 0)
    sys.stderr.write(f"BLOCKED [{code}]: {message}"[:1023] + "\n")
    return 2


def _run_tests():
    import copy
    import socket
    import subprocess
    import tempfile
    import tracemalloc
    import unittest
    from unittest.mock import patch

    gate = sys.modules[__name__]
    SCRIPT_DIR = Path(__file__).resolve().parent

    expected_policy = {
        "version": 1,
        "allow": [
            ["gh","api","**"],
            ["gh","auth","status"],
            ["gh","issue","list","**"],
            ["gh","issue","view","**"],
            ["gh","pr","checks","**"],
            ["gh","pr","diff","**"],
            ["gh","pr","list"],
            ["gh","pr","list","**"],
            ["gh","pr","view","**"],
            ["gh","repo","view","**"],
            ["gh","run","list","**"],
            ["gh","run","view","**"],
            ["gh","search","**"],
            ["git","add","**"],
            ["git","branch","**"],
            ["git","commit","**"],
            ["git","diff","**"],
            ["git","grep","**"],
            ["git","log","**"],
            ["git","ls-tree","**"],
            ["git","ls-files","**"],
            ["git","mv","**"],
            ["git","rm","**"],
            ["git","status"],
            ["grep","**"],
            ["ls"],
            ["ls","**"],
            ["printf","**"],
            ["rg"],
            ["rg","**"],
            ["sleep"],
            ["sleep","**"],
            ["stat","**"],
            ["tree"],
            ["tree","**"],
            ["uv","run","pytest","**"],
            ["uv","run","ruff","check","**"],
            ["uv","run","ruff","format","**"],
            ["uv","sync","--frozen"],
            ["uv","sync","--frozen","**"],
            ["wc","**"],
            ["wget","**"],
            ["cafleet","**"]
        ],
        "block": [
            ["awk","**"],
            ["cat","**"],
            ["curl","**"],
            ["echo","**"],
            ["find","**"],
            ["git","-C","**"],
            ["git","-c","**"],
            ["kill","**"],
            ["mkdir","**"],
            ["python","**"],
            ["python3","**"],
            ["touch","**"],
            ["xargs","**"],
            ["git","push"],
            ["git","push","**"],
            ["uv","sync"],
            ["cafleet","member","prompt","**","--shell","**"],
            ["cafleet","member","prompt","**","--shell=*","**"]
        ],
    }
    source_rules = [
        ["allow","Bash(gh api *)",[0]],
        ["allow","Bash(gh auth status)",[1]],
        ["allow","Bash(gh issue list *)",[2]],
        ["allow","Bash(gh issue view *)",[3]],
        ["allow","Bash(gh pr checks *)",[4]],
        ["allow","Bash(gh pr diff *)",[5]],
        ["allow","Bash(gh pr list)",[6]],
        ["allow","Bash(gh pr list *)",[7]],
        ["allow","Bash(gh pr view *)",[8]],
        ["allow","Bash(gh repo view *)",[9]],
        ["allow","Bash(gh run list *)",[10]],
        ["allow","Bash(gh run view *)",[11]],
        ["allow","Bash(gh search *)",[12]],
        ["allow","Bash(git add *)",[13]],
        ["allow","Bash(git branch *)",[14]],
        ["allow","Bash(git commit *)",[15]],
        ["allow","Bash(git diff *)",[16]],
        ["allow","Bash(git grep *)",[17]],
        ["allow","Bash(git log *)",[18]],
        ["allow","Bash(git ls-tree *)",[19]],
        ["allow","Bash(git ls-files *)",[20]],
        ["allow","Bash(git mv *)",[21]],
        ["allow","Bash(git rm *)",[22]],
        ["allow","Bash(git status)",[23]],
        ["allow","Bash(grep *)",[24]],
        ["allow","Bash(ls)",[25]],
        ["allow","Bash(ls *)",[26]],
        ["allow","Bash(printf *)",[27]],
        ["allow","Bash(rg)",[28]],
        ["allow","Bash(rg *)",[29]],
        ["allow","Bash(sleep)",[30]],
        ["allow","Bash(sleep *)",[31]],
        ["allow","Bash(stat *)",[32]],
        ["allow","Bash(tree)",[33]],
        ["allow","Bash(tree *)",[34]],
        ["allow","Bash(uv run pytest *)",[35]],
        ["allow","Bash(uv run ruff check *)",[36]],
        ["allow","Bash(uv run ruff format *)",[37]],
        ["allow","Bash(uv sync --frozen)",[38]],
        ["allow","Bash(uv sync --frozen *)",[39]],
        ["allow","Bash(wc *)",[40]],
        ["allow","Bash(wget *)",[41]],
        ["allow","Bash(cafleet *)",[42]],
        ["deny","Bash(awk *)",[0]],
        ["deny","Bash(cat *)",[1]],
        ["deny","Bash(curl *)",[2]],
        ["deny","Bash(echo *)",[3]],
        ["deny","Bash(find *)",[4]],
        ["deny","Bash(git -C *)",[5]],
        ["deny","Bash(git -c *)",[6]],
        ["deny","Bash(kill *)",[7]],
        ["deny","Bash(mkdir *)",[8]],
        ["deny","Bash(python *)",[9]],
        ["deny","Bash(python3 *)",[10]],
        ["deny","Bash(touch *)",[11]],
        ["deny","Bash(xargs *)",[12]],
        ["ask","Bash(git push)",[13]],
        ["ask","Bash(git push *)",[14]],
        ["ask","Bash(uv sync)",[15]],
        ["ask","Bash(cafleet member prompt * --shell *)",[16,17]],
        ["ask","Bash(cafleet member prompt * --shell)",[16,17]],
        ["ask","Bash(cafleet member prompt --shell *)",[16,17]]
    ]
    FIXTURE = {
        "expected": expected_policy,
        "entries": [
            {"category": category, "source": source,
             "target": "allow" if category == "allow" else "block",
             "rules": [expected_policy["allow" if category == "allow" else "block"][index]
                       for index in indexes]}
            for category, source, indexes in source_rules
        ],
        "command_cases": [
            {"argv":["cafleet","message","poll","312"],"decision":"allow"},
            {"argv":["cafleet","member","prompt","313","--shell","git status"],"decision":"RULE_BLOCK"},
            {"argv":["cafleet","member","prompt","313","--shell"],"decision":"RULE_BLOCK"},
            {"argv":["cafleet","member","prompt","--shell","git status"],"decision":"RULE_BLOCK"},
            {"argv":["cafleet","member","prompt","313","--shell=git status"],"decision":"RULE_BLOCK"},
            {"argv":["cafleet","member","prompt","313","--shell=false","extra"],"decision":"RULE_BLOCK"},
            {"argv":["cafleet","member","prompt","313","hello"],"decision":"allow"},
            {"argv":["git","push"],"decision":"RULE_BLOCK"},
            {"argv":["git","push","origin","main"],"decision":"RULE_BLOCK"},
            {"argv":["herdr","pane","read","1"],"decision":"RULE_UNMATCHED"},
            {"argv":["git","add"],"decision":"allow"},
            {"argv":["git","status","--short"],"decision":"RULE_UNMATCHED"}
        ],
    }
    seed_settings = {"permissions": {
        category: [source for origin, source, indexes in source_rules if origin == category]
        for category in ("allow", "deny", "ask")
    }}
    EMPTY = {"version": 1, "allow": [], "block": []}
    CLAUDE_SUCCESS = {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "allow",
        "permissionDecisionReason": "Matched shared command policy",
    }}
    ENVELOPE = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": "git status"}}

    class SeedContractTests(unittest.TestCase):
        def test_fixture_accounts_for_every_source_bash_entry(self):
            source = SCRIPT_DIR.parent / "claude/settings.json"
            if not source.is_file():
                self.skipTest("Repository source settings are not present beside installed helpers")
            settings = json.loads(source.read_text())
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
            settings = seed_settings
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
            scratch = Path.cwd() / ".test-scratch" / "command-policy"
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
                [sys.executable, "-c", code, str(SCRIPT_DIR)],
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
            fixture = FIXTURE
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
                [sys.executable, str(SCRIPT_DIR / "validate_bash.py"), "validate", "--client", "codex"],
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
            scratch = Path.cwd() / ".test-scratch" / "command-policy"
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
                    [sys.executable, str(SCRIPT_DIR / "validate_bash.py"), "validate", "--client", "codex"],
                    input=json.dumps(envelope), capture_output=True, text=True, timeout=3,
                    env=dict(os.environ, HOME=home),
                )
                self.assertLess(time.monotonic() - started, 3)
                self.assert_limit_denial(result)


    class HookAdapterTests(unittest.TestCase):
        def setUp(self):
            scratch = Path.cwd() / ".test-scratch" / "adapters"
            scratch.mkdir(parents=True, exist_ok=True)
            self.directory = tempfile.TemporaryDirectory(dir=scratch)
            self.addCleanup(self.directory.cleanup)
            self.home = Path(self.directory.name)
            self.policy_path = self.home / ".config/himkt/accepts.jsonc"
            self.policy_path.parent.mkdir(parents=True)
            self.policy_path.write_text(json.dumps({
                "version": 1, "allow": [["git", "status"], ["gh", "api", "**"]],
                "block": [["git", "push", "**"]],
            }))
            self.environment = dict(os.environ, HOME=str(self.home))
            self.environment.pop("GH_HOST", None)

        def invoke(self, client="codex", envelope=ENVELOPE, raw=None, module="validate_bash.py", injection=None):
            arguments = [sys.executable, str(SCRIPT_DIR / module), "validate"]
            if injection is not None:
                code = (
                    "import sys\nfrom unittest.mock import patch\n"
                    "sys.path.insert(0, sys.argv.pop(1))\nimport validate_bash as gate\n"
                    + injection + "\n"
                )
                arguments = [sys.executable, "-c", code, str(SCRIPT_DIR), "validate"]
            if module == "validate_bash.py":
                arguments += ["--client", client]
            content = json.dumps(envelope).encode() if raw is None else raw
            return subprocess.run(arguments, input=content, capture_output=True,
                                  env=self.environment, timeout=3)

        def assert_denied(self, result, code):
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(result.stdout, b"")
            message = result.stderr.decode()
            self.assertTrue(message.startswith(f"BLOCKED [{code}]: "), message)
            self.assertLessEqual(len(message), 1024)
            self.assertNotIn("Traceback", message)
            return message

        def assert_success(self, result, client):
            self.assertIn(client, ("codex", "claude"))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, b"")
            if client == "codex":
                self.assertEqual(result.stdout, b"")
            else:
                self.assertEqual(json.loads(result.stdout), CLAUDE_SUCCESS)

        def test_clients_emit_their_respective_success_responses(self):
            for client in ("codex", "claude"):
                with self.subTest(client=client):
                    result = self.invoke(client)
                    self.assert_success(result, client)

        def test_additional_envelope_fields_are_supported_without_rewriting_input(self):
            envelope = copy.deepcopy(ENVELOPE)
            envelope.update(session_id="test", cwd="/anywhere")
            envelope["tool_input"].update(timeout=1000, description="test")
            for client in ("codex", "claude"):
                with self.subTest(client=client):
                    result = self.invoke(client, envelope)
                    self.assert_success(result, client)

        def test_missing_or_invalid_required_envelope_fields_are_input_denials(self):
            cases = [None, [], 1, True, "command", {}]
            for key in ENVELOPE:
                value = copy.deepcopy(ENVELOPE)
                del value[key]
                cases.append(value)
            for key, invalid in (("hook_event_name", "PostToolUse"), ("tool_name", "Read"),
                                 ("tool_input", None), ("tool_input", []),
                                 ("tool_input", {}), ("tool_input", {"command": ""}),
                                 ("tool_input", {"command": None}), ("tool_input", {"command": 1})):
                cases.append(dict(ENVELOPE, **{key: invalid}))
            for client in ("codex", "claude"):
                for envelope in cases:
                    with self.subTest(client=client, envelope=envelope):
                        self.assert_denied(self.invoke(client, envelope), "INPUT_INVALID")

        def test_malformed_json_duplicate_keys_and_invalid_utf8_are_denied(self):
            for raw in (b"", b"{", b"null true", b"\xff", b'{"tool_name":"Bash","tool_name":"Read"}',
                        b'{"hook_event_name":NaN}', b'/*comment*/{}'):
                with self.subTest(raw=raw):
                    self.assert_denied(self.invoke(raw=raw), "INPUT_INVALID")

        def test_hook_input_size_and_nesting_limits_are_denials(self):
            self.assert_denied(self.invoke(raw=b" " * (1024 * 1024 + 1)), "EVALUATION_LIMIT")
            self.assert_denied(self.invoke(raw=b"[" * 9 + b"]" * 9), "EVALUATION_LIMIT")

        def test_missing_policy_names_the_fixed_path_and_requests_repair(self):
            self.policy_path.unlink()
            for client in ("codex", "claude"):
                message = self.assert_denied(self.invoke(client), "POLICY_MISSING")
                self.assertIn(str(self.policy_path), message)
                self.assertIn("repair", message.lower())
            self.assertFalse(self.policy_path.exists())

        def test_policy_syntax_schema_and_encoding_failures_are_explicit(self):
            for content in (b"{", b"{}", b"[]", b"\xff",
                            b'{"version":true,"allow":[],"block":[]}',
                            b'{"version":1,"allow":[],"block":[],"extra":1}'):
                for client in ("codex", "claude"):
                    with self.subTest(content=content, client=client):
                        self.policy_path.write_bytes(content)
                        message = self.assert_denied(self.invoke(client), "POLICY_INVALID")
                        self.assertIn(str(self.policy_path), message)
                        self.assertIn("repair", message.lower())

        def test_unreadable_policy_is_a_denial(self):
            self.policy_path.chmod(0)
            try:
                self.assert_denied(self.invoke(), "POLICY_INVALID")
            finally:
                self.policy_path.chmod(0o600)

        def test_nonregular_policy_denies_promptly(self):
            self.policy_path.unlink()
            os.mkfifo(self.policy_path)
            self.assert_denied(self.invoke(), "POLICY_INVALID")

        def test_envelope_is_checked_before_policy_and_policy_before_command(self):
            self.policy_path.unlink()
            self.assert_denied(self.invoke(envelope={}), "INPUT_INVALID")
            envelope = dict(ENVELOPE, tool_input={"command": "git; git"})
            self.assert_denied(self.invoke(envelope=envelope), "POLICY_MISSING")

        def test_block_unmatched_and_unsupported_shell_have_distinct_codes(self):
            for command, code in (("git push", "RULE_BLOCK"), ("herdr pane read", "RULE_UNMATCHED"),
                                  ("git status --short", "RULE_UNMATCHED"), ("git status | git status", "SHELL_UNSUPPORTED")):
                for client in ("codex", "claude"):
                    with self.subTest(command=command, client=client):
                        envelope = dict(ENVELOPE, tool_input={"command": command})
                        message = self.assert_denied(self.invoke(client, envelope), code)
                        if code == "RULE_UNMATCHED":
                            self.assertIn(command.split()[0], message)
                            self.assertIn("review", message.lower())

        def test_allowed_shell_rule_still_requires_github_endpoint_authorization(self):
            for client in ("codex", "claude"):
                for command in ("gh api user", "gh api repos/himkt/config/contents/x -XDELETE"):
                    with self.subTest(client=client, command=command):
                        envelope = dict(ENVELOPE, tool_input={"command": command})
                        self.assert_denied(self.invoke(client, envelope), "GH_API_BLOCK")
                envelope = dict(ENVELOPE, tool_input={"command": "gh api repos/himkt/config/contents/x"})
                result = self.invoke(client, envelope)
                self.assert_success(result, client)

        def test_shell_block_precedes_github_gate(self):
            self.policy_path.write_text(json.dumps({"version": 1, "allow": [["gh", "api", "**"]],
                                                  "block": [["gh", "api", "**"]]}))
            envelope = dict(ENVELOPE, tool_input={"command": "gh api user"})
            self.assert_denied(self.invoke(envelope=envelope), "RULE_BLOCK")

        def test_runtime_host_conflict_denies_after_a_shell_allow(self):
            self.environment["GH_HOST"] = "enterprise.example"
            envelope = dict(ENVELOPE, tool_input={"command": "gh api repos/himkt/config/contents/x"})
            self.assert_denied(self.invoke(envelope=envelope), "GH_API_BLOCK")

        def test_unexpected_exceptions_deny_without_leaking_details(self):
            for client in ("codex", "claude"):
                for target in ("evaluate", "load_policy"):
                    with self.subTest(client=client, target=target):
                        injection = (
                            f'with patch("validate_bash.{target}", side_effect=RuntimeError("SECRET_BODY")):\n'
                            "    sys.exit(gate.main())"
                        )
                        message = self.assert_denied(self.invoke(client, injection=injection), "INTERNAL_ERROR")
                        self.assertNotIn("SECRET_BODY", message)

        def test_claude_serialization_failure_denies_without_leaking_details(self):
            injection = (
                'with patch("validate_bash.json.dumps", side_effect=RuntimeError("SECRET_BODY")):\n'
                "    sys.exit(gate.main())"
            )
            message = self.assert_denied(self.invoke("claude", injection=injection), "INTERNAL_ERROR")
            self.assertNotIn("SECRET_BODY", message)

        def test_deadline_setup_failure_is_an_explicit_denial(self):
            injection = (
                'with patch("validate_bash.signal.setitimer", side_effect=OSError("Unavailable")):\n'
                "    sys.exit(gate.main())"
            )
            self.assert_denied(self.invoke(injection=injection), "INTERNAL_ERROR")

        def test_denial_messages_are_bounded_and_omit_request_body(self):
            secret = "SECRET_BODY_" * 3000
            envelope = dict(ENVELOPE, tool_input={"command": "gh api user -f 'body=" + secret + "'"})
            message = self.assert_denied(self.invoke(envelope=envelope), "GH_API_BLOCK")
            self.assertNotIn("SECRET_BODY", message)

        def test_parse_diagnostic_returns_literal_argv_without_a_policy(self):
            self.policy_path.unlink()
            result = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "validate_bash.py"), "parse"],
                input=json.dumps({"tool_input": {"command": "git '' --name=value"}}).encode(),
                capture_output=True, env=self.environment, timeout=3,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), ["git", "", "--name=value"])

        def test_validate_requires_an_explicit_supported_client(self):
            for options in ([], ["--client", "unknown"]):
                with self.subTest(options=options):
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT_DIR / "validate_bash.py"), "validate", *options],
                        input=json.dumps(ENVELOPE).encode(), capture_output=True, env=self.environment, timeout=3,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, b"")

        def test_standalone_github_validator_uses_explicit_input_denial(self):
            for envelope in ({}, None, dict(ENVELOPE, tool_input={"command": None})):
                with self.subTest(envelope=envelope):
                    self.assert_denied(self.invoke(envelope=envelope, module="validate_gh_api.py"), "INPUT_INVALID")

        def test_standalone_allowed_github_success_has_empty_stdout_without_shared_policy(self):
            self.policy_path.unlink()
            envelope = dict(ENVELOPE, tool_input={"command": "gh api repos/himkt/config/contents/x"})
            result = self.invoke(envelope=envelope, module="validate_gh_api.py")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, b"")
            self.assertEqual(result.stderr, b"")

        def test_standalone_literal_non_github_success_has_empty_stdout_without_shared_policy(self):
            self.policy_path.unlink()
            for command in ("git status", "herdr pane read 1", "printf 'price $'"):
                with self.subTest(command=command):
                    envelope = dict(ENVELOPE, tool_input={"command": command})
                    result = self.invoke(envelope=envelope, module="validate_gh_api.py")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, b"")
                    self.assertEqual(result.stderr, b"")

        def test_standalone_github_validator_shares_literal_parsing_and_endpoint_denial(self):
            for command, code in (("gh api user", "GH_API_BLOCK"),
                                  ("gh api repos/himkt/config/contents/x | git status", "SHELL_UNSUPPORTED"),
                                  ("gh api 'unclosed", "SHELL_UNSUPPORTED")):
                with self.subTest(command=command):
                    self.assert_denied(self.invoke(envelope=dict(ENVELOPE, tool_input={"command": command}),
                                                   module="validate_gh_api.py"), code)

        def test_standalone_stalled_stdin_denies_within_three_seconds(self):
            started = time.monotonic()
            process = subprocess.Popen(
                [sys.executable, str(SCRIPT_DIR / "validate_gh_api.py"), "validate"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=self.environment,
            )
            try:
                process.wait(timeout=3)
                output, error = process.communicate()
                self.assertLess(time.monotonic() - started, 3)
                self.assert_denied(
                    subprocess.CompletedProcess(process.args, process.returncode, output, error),
                    "EVALUATION_LIMIT",
                )
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

        def invoke_standalone_with_patch(self, target):
            code = (
                "import runpy, sys\nfrom unittest.mock import patch\n"
                "sys.path.insert(0, sys.argv.pop(1))\n"
                "import validate_gh_api\n"
                f'with patch("{target}", side_effect=RuntimeError("SECRET_BODY")):\n'
                '    runpy.run_module("validate_gh_api", run_name="__main__")\n'
            )
            envelope = dict(ENVELOPE, tool_input={"command": "gh api repos/himkt/config/contents/x"})
            return subprocess.run(
                [sys.executable, "-c", code, str(SCRIPT_DIR), "validate"],
                input=json.dumps(envelope).encode(), capture_output=True,
                env=self.environment, timeout=3,
            )

        def test_standalone_deadline_setup_failure_is_an_explicit_denial(self):
            result = self.invoke_standalone_with_patch("signal.setitimer")
            message = self.assert_denied(result, "INTERNAL_ERROR")
            self.assertNotIn("SECRET_BODY", message)

        def test_standalone_unexpected_evaluation_failure_is_an_explicit_denial(self):
            result = self.invoke_standalone_with_patch("validate_bash.parse")
            message = self.assert_denied(result, "INTERNAL_ERROR")
            self.assertNotIn("SECRET_BODY", message)

    suite = unittest.TestSuite(
        unittest.TestLoader().loadTestsFromTestCase(case)
        for case in (SeedContractTests, PolicyLoadingTests, LiteralParserTests,
                     MatchingTests, ShellConformanceTests, EvaluationDeadlineTests,
                     HookAdapterTests)
    )
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()


def main():
    import argparse

    parser = argparse.ArgumentParser(prog="validate_bash.py")
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    subcommands.add_parser("parse")
    validate = subcommands.add_parser("validate")
    validate.add_argument("--client", choices=("codex", "claude"), required=True)
    subcommands.add_parser("test")
    arguments = parser.parse_args()
    if arguments.subcommand == "test":
        return 0 if _run_tests() else 1
    if arguments.subcommand == "validate":
        return _validate_cli(client=arguments.client)
    try:
        result = parse(json.load(sys.stdin)["tool_input"]["command"])
        print(json.dumps(result))
        return 0
    except (ValueError, KeyError, TypeError):
        sys.stderr.write("BLOCKED [INPUT_INVALID]: Expected a literal command\n")
        return 2


if __name__ == "__main__":
    sys.modules["validate_bash"] = sys.modules[__name__]
    sys.exit(main())
