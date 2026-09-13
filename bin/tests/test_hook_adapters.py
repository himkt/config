import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
CLAUDE_SUCCESS = {"hookSpecificOutput": {
    "hookEventName": "PreToolUse", "permissionDecision": "allow",
    "permissionDecisionReason": "Matched shared command policy",
}}
ENVELOPE = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": "git status"}}


class HookAdapterTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".test-scratch" / "adapters"
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
        arguments = [sys.executable, str(ROOT / "bin" / module), "validate"]
        if injection is not None:
            code = (
                "import sys\nfrom unittest.mock import patch\n"
                "sys.path.insert(0, sys.argv.pop(1))\nimport validate_bash as gate\n"
                + injection + "\n"
            )
            arguments = [sys.executable, "-c", code, str(ROOT / "bin"), "validate"]
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
            [sys.executable, str(ROOT / "bin/validate_bash.py"), "parse"],
            input=json.dumps({"tool_input": {"command": "git '' --name=value"}}).encode(),
            capture_output=True, env=self.environment, timeout=3,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), ["git", "", "--name=value"])

    def test_validate_requires_an_explicit_supported_client(self):
        for options in ([], ["--client", "unknown"]):
            with self.subTest(options=options):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "bin/validate_bash.py"), "validate", *options],
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
            [sys.executable, str(ROOT / "bin/validate_gh_api.py"), "validate"],
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
            [sys.executable, "-c", code, str(ROOT / "bin"), "validate"],
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


if __name__ == "__main__":
    unittest.main()
