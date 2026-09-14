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
            if not rule[0] or "*" in rule[0]:
                _invalid_policy("Executable must be a nonempty literal name or path")
            identity = tuple(rule)
            budget.charge(sum(map(len, rule)))
            if identity in seen:
                _invalid_policy("Duplicate policy rule")
            seen.add(identity)
    return policy


def _load_policy_file(path, budget, optional=False):
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
        if optional and not path.is_symlink():
            return {"version": 1, "allow": [], "block": []}
        raise PolicyError("POLICY_MISSING", f"Repair policy at {path}: file missing") from error
    except PolicyError as error:
        raise PolicyError(error.code, f"Repair policy at {path}: {error}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PolicyError("POLICY_INVALID", f"Repair policy at {path}: unreadable or invalid policy") from error


def project_directory(cwd):
    try:
        directory = Path(cwd).resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise PolicyError("INPUT_INVALID", "Working directory must be accessible") from error
    if not directory.is_dir():
        raise PolicyError("INPUT_INVALID", "Working directory must be a directory")
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            return candidate
    return directory


def load_policy(budget=None, cwd=None):
    if budget is None:
        budget = EvaluationBudget()
    global_policy = _load_policy_file(Path.home() / ".config/himkt/accepts.jsonc", budget)
    local_path = project_directory(Path.cwd() if cwd is None else cwd) / ".rules/accepts.jsonc"
    local_policy = _load_policy_file(local_path, budget, optional=True)
    merged = {"version": 1}
    for category in ("allow", "block"):
        merged[category] = [list(rule) for rule in dict.fromkeys(
            tuple(rule) for rule in global_policy[category] + local_policy[category]
        )]
    return validate_policy(merged, budget)


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
    if Path(argv[0]).name == "gh" and argv[1:2] == ["api"]:
        from validate_gh_api import check_argv

        check_argv(["gh", *argv[1:]], budget)
    for rule in policy["allow"]:
        if match_argv(argv, rule, budget):
            return "allow"
    return "defer"


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
    if "cwd" in envelope and (not isinstance(envelope["cwd"], str)
                               or not Path(envelope["cwd"]).is_absolute()):
        raise PolicyError("INPUT_INVALID", "Hook cwd must be an absolute directory path")
    return envelope


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
        envelope = _read_envelope(budget)
        command = envelope["tool_input"]["command"]
        decision = "defer"
        if github_only:
            from validate_gh_api import check_argv

            argv = parse(command, budget)
            if Path(argv[0]).name == "gh" and argv[1:2] == ["api"]:
                check_argv(["gh", *argv[1:]], budget)
        else:
            policy = load_policy(budget, cwd=envelope.get("cwd"))
            decision = evaluate(command, policy, budget)
        if client == "claude" and decision == "allow":
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
    import contextlib
    import io
    import subprocess
    import tempfile
    import unittest
    from unittest.mock import patch

    policy = {"version": 1, "allow": [["git", "**"], ["gh", "api", "**"]],
              "block": [["git", "push", "**"]]}
    script = Path(__file__).resolve()

    class ValidatorTests(unittest.TestCase):
        @contextlib.contextmanager
        def policy_files(self):
            with tempfile.TemporaryDirectory(prefix=".validate-", dir=Path.cwd()) as home, patch.dict(os.environ, HOME=home):
                root = Path(home).resolve()
                global_path = root / ".config/himkt/accepts.jsonc"
                global_path.parent.mkdir(parents=True)
                global_path.write_text(json.dumps(policy))
                project = root / "project"
                (project / ".git").mkdir(parents=True)
                local_path = project / ".rules/accepts.jsonc"
                local_path.parent.mkdir()
                yield global_path, local_path, project

        def assert_error(self, code, function, *args):
            with self.assertRaises(PolicyError) as caught:
                function(*args)
            self.assertEqual(caught.exception.code, code)

        def test_literal_arguments(self):
            for command, argv in (
                ("git -x value --name=value -- -z", ["git", "-x", "value", "--name=value", "--", "-z"]),
                ("g'it' a\"b\" ''", ["git", "ab", ""]),
                (r"git foo\ bar", ["git", "foo bar"]),
                ("git '$HOME' 'a|b' '='sh", ["git", "$HOME", "a|b", "=sh"]),
                (r'git "\q" "\$HOME"', ["git", "\\q", "$HOME"]),
                ("gh api x --jq '.[] | select(.x > 0)'", ["gh", "api", "x", "--jq", ".[] | select(.x > 0)"]),
            ):
                with self.subTest(command=command):
                    self.assertEqual(parse(command), argv)

        def test_shell_syntax_rejected(self):
            for command in (
                "git;id", "git | id", "git && id", "git || id", "git &",
                "git >out", "git 2>&1", "git <in", "git\nid", "git\\\nid",
                "git $HOME", 'git "$HOME"', "git $(id)", "git " + chr(96) + "id" + chr(96),
                "git $'x'", "git *", "git {a,b}", "git ~", "git #x", "git =sh",
                "X=x git", "(git)", "if", "git 'unclosed", "git \\",
            ):
                with self.subTest(command=command):
                    self.assert_error("SHELL_UNSUPPORTED", parse, command)

        def test_argument_matching(self):
            for argv, rule, expected in (
                (["git", "status"], ["git", "status"], True),
                (["git", "status", "-s"], ["git", "status"], False),
                (["git", "status -s"], ["git", "status", "**"], False),
                (["git", "add"], ["git", "add", "**"], True),
                (["git", "a", "b", "end"], ["git", "**", "end"], True),
                (["git", "end", "extra"], ["git", "**", "end"], False),
                (["git", ""], ["git", "*"], True),
                (["git", "a", "b"], ["git", "*"], False),
                (["git", "abMIDcd"], ["git", "ab*cd"], True),
                (["git", "a"], ["git", "[ab]"], False),
            ):
                with self.subTest(argv=argv, rule=rule):
                    self.assertIs(match_argv(argv, rule), expected)
            self.assertEqual(evaluate("git status", policy), "allow")
            self.assert_error("RULE_BLOCK", evaluate, "git push origin main", policy)
            for command in ("/usr/bin/git status", "env git status", "Git status"):
                self.assertEqual(evaluate(command, policy), "defer")
            self.assertEqual(evaluate("git status", {"version": 1, "allow": [], "block": []}), "defer")

        def test_executable_paths(self):
            paths = {"version": 1, "allow": [["/usr/bin/git", "status"], ["./tool", "**"]],
                     "block": [["./tool", "delete"]]}
            self.assertEqual(evaluate("/usr/bin/git status", paths), "allow")
            self.assertEqual(evaluate("git status", paths), "defer")
            self.assertEqual(evaluate("./tool list", paths), "allow")
            self.assert_error("RULE_BLOCK", evaluate, "./tool delete", paths)

        def test_github_gate_before_defer(self):
            empty = {"version": 1, "allow": [], "block": []}
            for executable in ("gh", "/usr/bin/gh", "./gh"):
                self.assert_error("GH_API_BLOCK", evaluate, executable + " api user", empty)
                self.assertEqual(evaluate(executable + " api repos/himkt/config/contents/x", empty), "defer")

        def test_schema(self):
            self.assertEqual(validate_policy(policy), policy)
            for invalid in (
                None, {}, dict(policy, version=True), dict(policy, version=2),
                dict(policy, extra=1), dict(policy, allow="git"),
                dict(policy, allow=[[]]), dict(policy, allow=[[""]]),
                dict(policy, allow=[["g*"]]), dict(policy, allow=[["git", 1]]),
                dict(policy, allow=[["git"], ["git"]]),
            ):
                with self.subTest(policy=invalid):
                    self.assert_error("POLICY_INVALID", validate_policy, invalid)

        def test_policy_file_and_jsonc(self):
            with tempfile.TemporaryDirectory(prefix=".validate-", dir=Path.cwd()) as home, patch.dict(os.environ, HOME=home):
                path = Path(home) / ".config/himkt/accepts.jsonc"
                path.parent.mkdir(parents=True)
                self.assert_error("POLICY_MISSING", load_policy)
                path.mkdir()
                self.assert_error("POLICY_INVALID", load_policy)
                path.rmdir()
                path.write_text('/* comment */ {"version":1,"allow":[["git",],],'
                                '"block":[],} // comment')
                self.assertEqual(load_policy(), {"version": 1, "allow": [["git"]], "block": []})
                path.write_text('{"version":1,"allow":[["git","https://x/*y*/"]],"block":[]}')
                self.assertEqual(load_policy()["allow"][0][1], "https://x/*y*/")
                for content in (
                    b'{', b'\xff', b'{"version":1,"version":1,"allow":[],"block":[]}',
                    b'{"version":1/*x*/0,"allow":[],"block":[]}',
                    b'{"version":1,"allow":[,],"block":[]}', b'/* unfinished',
                ):
                    path.write_bytes(content)
                    self.assert_error("POLICY_INVALID", load_policy)
                path.write_bytes(b" " * (MAX_POLICY_BYTES + 1))
                self.assert_error("EVALUATION_LIMIT", load_policy)

        def test_project_policy_merge(self):
            with tempfile.TemporaryDirectory(prefix=".validate-", dir=Path.cwd()) as home, patch.dict(os.environ, HOME=home):
                global_path = Path(home) / ".config/himkt/accepts.jsonc"
                global_path.parent.mkdir(parents=True)
                global_path.write_text(json.dumps(policy))
                root = Path(home) / "project"
                child = root / "src"
                child.mkdir(parents=True)
                (root / ".git").write_text("gitdir: ../worktree-metadata")
                local_path = root / ".rules/accepts.jsonc"
                local_path.parent.mkdir()
                self.assertEqual(load_policy(cwd=child), policy)
                local_path.write_text(json.dumps({"version": 1,
                    "allow": [["git", "**"], ["git", "push", "**"], ["./tool", "**"]],
                    "block": [["git", "status"]]}))
                merged = load_policy(cwd=child)
                self.assertEqual(merged["allow"].count(["git", "**"]), 1)
                self.assertEqual(evaluate("./tool list", merged), "allow")
                self.assert_error("RULE_BLOCK", evaluate, "git status", merged)
                self.assert_error("RULE_BLOCK", evaluate, "git push", merged)
                local_path.write_text("{")
                with self.assertRaises(PolicyError) as caught:
                    load_policy(cwd=child)
                self.assertEqual(caught.exception.code, "POLICY_INVALID")
                self.assertIn(str(local_path), str(caught.exception))
                local_path.unlink()
                local_path.symlink_to(root / "missing.jsonc")
                self.assert_error("POLICY_MISSING", load_policy, None, child)

        def test_project_discovery(self):
            with tempfile.TemporaryDirectory(prefix=".validate-", dir=Path.cwd()) as temporary:
                root = Path(temporary)
                child = root / "src"
                child.mkdir()
                (root / ".git").mkdir()
                self.assertEqual(project_directory(child), root.resolve())
                (child / ".git").mkdir()
                self.assertEqual(project_directory(child), child.resolve())

        def test_evaluation_limits(self):
            self.assert_error("EVALUATION_LIMIT", parse, "git status", EvaluationBudget(limit=0))
            self.assert_error("EVALUATION_LIMIT", match_argv, ["git", "x" * 100],
                              ["git", "*a*b*"], EvaluationBudget(limit=1))
            self.assert_error("EVALUATION_LIMIT", EvaluationBudget(deadline=0).check_deadline)
            self.assert_error("EVALUATION_LIMIT", parse, "git " + "x" * 65536)

        def test_non_git_directory_uses_only_starting_policy(self):
            with self.policy_files() as (global_path, local_path, project):
                child = project / "src"
                (child / ".rules").mkdir(parents=True)
                local_path.write_text(json.dumps({"version": 1, "allow": [], "block": [["git", "status"]]}))
                child_policy = child / ".rules/accepts.jsonc"
                child_policy.write_text(json.dumps({"version": 1, "allow": [["./child"]], "block": []}))
                path_exists = Path.exists
                with patch.object(Path, "exists", lambda path: path.name != ".git" and path_exists(path)):
                    self.assertEqual(project_directory(child), child)
                    merged = load_policy(cwd=child)
                self.assertEqual(merged["allow"], policy["allow"] + [["./child"]])
                self.assertEqual(merged["block"], policy["block"])
                self.assertEqual(evaluate("git status", merged), "allow")

        def test_missing_local_policy_contributes_empty_rules(self):
            with self.policy_files() as (global_path, local_path, project):
                local_path.parent.rmdir()
                self.assertEqual(load_policy(cwd=project), policy)
                local_path.parent.mkdir()
                self.assertEqual(load_policy(cwd=project), policy)

        def test_each_file_rejects_duplicate_rules_in_each_category(self):
            with self.policy_files() as (global_path, local_path, project):
                for target in (global_path, local_path):
                    for category in ("allow", "block"):
                        with self.subTest(target=target, category=category):
                            global_path.write_text(json.dumps(policy))
                            local_path.write_text(json.dumps({"version": 1, "allow": [], "block": []}))
                            invalid = {"version": 1, "allow": [], "block": []}
                            invalid[category] = [["git", "status"], ["git", "status"]]
                            target.write_text(json.dumps(invalid))
                            with self.assertRaises(PolicyError) as caught:
                                load_policy(cwd=project)
                            self.assertEqual(caught.exception.code, "POLICY_INVALID")
                            self.assertIn(str(target), str(caught.exception))

        def test_merge_deduplicates_each_category_in_scope_order(self):
            with self.policy_files() as (global_path, local_path, project):
                global_path.write_text(json.dumps({"version": 1,
                    "allow": [["global"], ["shared"]], "block": [["blocked"], ["shared"]]}))
                local_path.write_text(json.dumps({"version": 1,
                    "allow": [["shared"], ["local"]], "block": [["shared"], ["local-block"]]}))
                merged = load_policy(cwd=project)
                self.assertEqual(merged, {"version": 1,
                    "allow": [["global"], ["shared"], ["local"]],
                    "block": [["blocked"], ["shared"], ["local-block"]]})
                self.assert_error("RULE_BLOCK", evaluate, "shared", merged)

        def test_merged_rule_limit_counts_both_categories_after_deduplication(self):
            with self.policy_files() as (global_path, local_path, project):
                allowed = [["tool", str(index)] for index in range(512)]
                blocked = [["blocked", str(index)] for index in range(512)]
                global_path.write_text(json.dumps({"version": 1, "allow": allowed, "block": blocked}))
                local_path.write_text(json.dumps({"version": 1, "allow": allowed, "block": blocked}))
                self.assertEqual(load_policy(cwd=project), {"version": 1, "allow": allowed, "block": blocked})
                local_path.write_text(json.dumps({"version": 1, "allow": [["extra"]], "block": []}))
                self.assert_error("EVALUATION_LIMIT", load_policy, None, project)

        def test_policy_files_are_reloaded_on_each_call(self):
            with self.policy_files() as (global_path, local_path, project):
                self.assertEqual(evaluate("git status", load_policy(cwd=project)), "allow")
                global_path.write_text(json.dumps({"version": 1, "allow": [], "block": []}))
                self.assertEqual(evaluate("git status", load_policy(cwd=project)), "defer")
                local_path.write_text(json.dumps({"version": 1, "allow": [["git", "status"]], "block": []}))
                self.assertEqual(evaluate("git status", load_policy(cwd=project)), "allow")
                local_path.write_text(json.dumps({"version": 1, "allow": [], "block": [["git", "status"]]}))
                self.assert_error("RULE_BLOCK", evaluate, "git status", load_policy(cwd=project))
                global_path.unlink()
                self.assert_error("POLICY_MISSING", load_policy, None, project)

        def test_nested_repository_and_worktree_use_only_their_root_policy(self):
            with self.policy_files() as (global_path, local_path, project):
                local_path.write_text(json.dumps({"version": 1, "allow": [], "block": [["git", "status"]]}))
                for name, worktree in (("nested", False), ("worktree", True)):
                    with self.subTest(worktree=worktree):
                        nested = project / name
                        child = nested / "src"
                        (child / ".rules").mkdir(parents=True)
                        (child / ".rules/accepts.jsonc").write_text("{")
                        if worktree:
                            (nested / ".git").write_text("gitdir: ../metadata")
                        else:
                            (nested / ".git").mkdir()
                        self.assertEqual(project_directory(child), nested)
                        self.assertEqual(load_policy(cwd=child), policy)
                        (nested / ".rules").mkdir()
                        (nested / ".rules/accepts.jsonc").write_text(json.dumps({"version": 1,
                            "allow": [["./nested"]], "block": []}))
                        self.assertEqual(load_policy(cwd=child)["allow"], policy["allow"] + [["./nested"]])

        def test_symlink_cwd_uses_resolved_repository(self):
            with self.policy_files() as (global_path, local_path, project):
                target = project / "nested"
                (target / ".git").mkdir(parents=True)
                alias = project / "alias"
                alias.symlink_to(target, target_is_directory=True)
                local_path.write_text("{")
                self.assertEqual(project_directory(alias), target)
                self.assertEqual(load_policy(cwd=alias), policy)

        def test_local_policy_file_errors_include_repair_path(self):
            with self.policy_files() as (global_path, local_path, project):
                for content, code in ((b"\xff", "POLICY_INVALID"),
                                      (b'{"version":1,"allow":[],"block":[],"block":[]}', "POLICY_INVALID"),
                                      (b" " * (MAX_POLICY_BYTES + 1), "EVALUATION_LIMIT")):
                    with self.subTest(code=code, size=len(content)):
                        local_path.write_bytes(content)
                        with self.assertRaises(PolicyError) as caught:
                            load_policy(cwd=project)
                        self.assertEqual(caught.exception.code, code)
                        self.assertIn(str(local_path), str(caught.exception))
                local_path.unlink()
                local_path.mkdir()
                self.assert_error("POLICY_INVALID", load_policy, None, project)

        def test_unmatched_syntax_and_path_github_calls_are_checked(self):
            empty = {"version": 1, "allow": [], "block": []}
            for command in ("unknown | cat", "unknown > output", "unknown $HOME"):
                with self.subTest(command=command):
                    self.assert_error("SHELL_UNSUPPORTED", evaluate, command, empty)
            for executable in ("gh", "/usr/bin/gh", "./gh"):
                with self.subTest(executable=executable):
                    allowed = {"version": 1, "allow": [[executable, "api", "**"]], "block": []}
                    self.assert_error("GH_API_BLOCK", evaluate, executable + " api user", allowed)
                    blocked = dict(allowed, block=[[executable, "api", "**"]])
                    self.assert_error("RULE_BLOCK", evaluate, executable + " api user", blocked)

        def test_clients_validate_cwd_and_use_process_cwd_when_omitted(self):
            with self.policy_files() as (global_path, local_path, project):
                local_path.write_text(json.dumps({"version": 1, "allow": [], "block": [["git", "status"]]}))
                ordinary_file = project / "file"
                ordinary_file.write_text("file")
                for client in ("codex", "claude"):
                    for cwd in (None, "", "relative", 1, str(project / "missing"), str(ordinary_file)):
                        with self.subTest(client=client, cwd=cwd):
                            envelope = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                        "cwd": cwd, "tool_input": {"command": "git status"}}
                            result = subprocess.run([sys.executable, str(script), "validate", "--client", client],
                                                    input=json.dumps(envelope), text=True, capture_output=True,
                                                    cwd=project, timeout=3)
                            self.assertEqual(result.returncode, 2)
                            self.assertEqual(result.stdout, "")
                            self.assertTrue(result.stderr.startswith("BLOCKED [INPUT_INVALID]:"), result.stderr)
                    del envelope["cwd"]
                    result = subprocess.run([sys.executable, str(script), "validate", "--client", client],
                                            input=json.dumps(envelope), text=True, capture_output=True,
                                            cwd=project, timeout=3)
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(result.stdout, "")
                    self.assertTrue(result.stderr.startswith("BLOCKED [RULE_BLOCK]:"), result.stderr)

        def test_client_contracts(self):
            with tempfile.TemporaryDirectory(prefix=".validate-", dir=Path.cwd()) as home:
                path = Path(home) / ".config/himkt/accepts.jsonc"
                path.parent.mkdir(parents=True)
                environment = dict(os.environ, HOME=home)
                environment.pop("GH_HOST", None)
                for client in ("codex", "claude", None):
                    arguments = [sys.executable, str(script if client else script.with_name("validate_gh_api.py")), "validate"]
                    if client:
                        arguments += ["--client", client]
                    for command, expected in (
                        ("git status", None),
                        ("git push", "RULE_BLOCK" if client else None),
                        ("unknown", None),
                        ("git | id", "SHELL_UNSUPPORTED"),
                        ("gh api user", "GH_API_BLOCK"),
                        ("gh api 'repos/himkt/config#/pulls/1/reviews/1' -XDELETE", "GH_API_BLOCK"),
                        ("gh api 'repos/himkt/config/contents/x?ref=main'", None),
                        (None, "INPUT_INVALID"),
                    ):
                        with self.subTest(client=client, command=command):
                            path.write_text(json.dumps(policy))
                            envelope = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                        "tool_input": {"command": command}}
                            result = subprocess.run(arguments, input=json.dumps(envelope),
                                                    text=True, capture_output=True, env=environment, timeout=3)
                            if expected:
                                self.assertEqual(result.returncode, 2)
                                self.assertEqual(result.stdout, "")
                                self.assertTrue(result.stderr.startswith(f"BLOCKED [{expected}]:"))
                            else:
                                self.assertEqual(result.returncode, 0, result.stderr)
                                self.assertEqual(result.stderr, "")
                                if client == "claude" and command != "unknown":
                                    self.assertEqual(json.loads(result.stdout), {"hookSpecificOutput": {
                                        "hookEventName": "PreToolUse", "permissionDecision": "allow",
                                        "permissionDecisionReason": "Matched shared command policy"}})
                                else:
                                    self.assertEqual(result.stdout, "")
                    if client:
                        for content, code in ((None, "POLICY_MISSING"), ("{", "POLICY_INVALID")):
                            if content is None:
                                path.unlink()
                            else:
                                path.write_text(content)
                            envelope["tool_input"]["command"] = "git status"
                            result = subprocess.run(arguments, input=json.dumps(envelope),
                                                    text=True, capture_output=True, env=environment, timeout=3)
                            self.assertEqual(result.returncode, 2)
                            self.assertEqual(result.stdout, "")
                            self.assertIn(code, result.stderr)

        def test_client_project_cwd(self):
            with tempfile.TemporaryDirectory(prefix=".validate-", dir=Path.cwd()) as home:
                global_path = Path(home) / ".config/himkt/accepts.jsonc"
                global_path.parent.mkdir(parents=True)
                global_path.write_text(json.dumps(policy))
                project = Path(home) / "project"
                (project / ".rules").mkdir(parents=True)
                (project / ".git").mkdir()
                child = project / "src"
                child.mkdir()
                (project / ".rules/accepts.jsonc").write_text(json.dumps({"version": 1,
                    "allow": [["./tool", "**"]], "block": [["git", "status"]]}))
                for client in ("codex", "claude"):
                    for command, expected in (("./tool list", "allow"), ("git status", "RULE_BLOCK"),
                                              ("unknown", "defer")):
                        envelope = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
                                    "cwd": str(child.resolve()), "tool_input": {"command": command}}
                        result = subprocess.run([sys.executable, str(script), "validate", "--client", client],
                                                input=json.dumps(envelope), text=True, capture_output=True,
                                                env=dict(os.environ, HOME=home), timeout=3)
                        self.assertEqual(result.returncode, 2 if expected == "RULE_BLOCK" else 0, result.stderr)
                        if expected == "RULE_BLOCK":
                            self.assertIn("RULE_BLOCK", result.stderr)
                        else:
                            self.assertEqual(result.stderr, "")
                        if client == "claude" and expected == "allow":
                            self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "allow")
                        else:
                            self.assertEqual(result.stdout, "")

        def test_internal_failure_denies(self):
            output, error = io.StringIO(), io.StringIO()
            with patch.object(sys.modules[__name__], "_read_envelope", side_effect=RuntimeError("secret")):
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                    self.assertEqual(_validate_cli(client="codex"), 2)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("INTERNAL_ERROR", error.getvalue())
            self.assertNotIn("secret", error.getvalue())

    suite = unittest.TestLoader().loadTestsFromTestCase(ValidatorTests)
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
