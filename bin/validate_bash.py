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
    import unittest

    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent / "tests"))
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
