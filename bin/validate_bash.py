#!/usr/bin/env python3

"""POSIX-flavored shell command parser.

Public API:
    parse(command_string: str) -> list[dict]
        One dict per command. The input is split on '|', ';', '&&', '||';
        each piece becomes one segment. Each dict has keys:
            command     str
            positionals list[str]
            keywords    dict[str, str|bool|list]
            redirect    list[dict]   (operator + optional target)
            expansions  list[dict]   (token + reason; empty when safe)

Raises ValueError on malformed input or unsupported syntax ('<<', '<<<',
'&', subshells, etc.).

Each token (command, positionals, keyword keys/values, redirect targets)
is scanned for shell-expansion vectors, in three layers:
  1. Multi-char introducers: $(...), $((...)), $[...], ${...}, $'...',
     $"...", `...`, <(...), >(...).
  2. $VAR and special-variable expansion.
  3. Stray '$' (defense-in-depth catch-all).
Findings populate seg["expansions"] as [{"token": str, "reason": str}, ...].

Bare operators (<, >, >>, &&, ;) inside a token are NOT flagged at the
token level — they are detected structurally when unquoted (_tokenize,
_split_commands), and are inert as literal characters when quoted.

CLI subcommands (stdin: {"tool_input": {"command": "..."}}):
    parse     - print parsed result as JSON
    validate  - exit 2 if the command has multiple segments, any redirect,
                or any non-empty seg["expansions"]
    test      - run embedded unittest suite
"""

import json
import os
from pathlib import Path
import re
import shlex
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


_DIGITS = frozenset("0123456789")

_OOS_OPS = {
    "<<": "heredoc/here-string is not supported",
    "<<<": "heredoc/here-string is not supported",
    "&": "background execution is not supported",
}

_DIVIDERS = ("|", ";", "&&", "||")

_REDIR_OPS_NO_TARGET = ("2>&1", "1>&2")


def _shlex_tokens(s):
    lex = shlex.shlex(s, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    return list(lex)


def _try_digit_prefix(raw, i):
    """Return (op, advance) if a digit at i starts a redirect, else (None, 0)."""
    if i + 1 >= len(raw) or raw[i] not in _DIGITS:
        return None, 0
    fd, nxt = raw[i], raw[i + 1]
    if nxt in (">", ">>", "<"):
        return fd + nxt, 2
    if nxt != ">&":
        return None, 0
    if i + 2 >= len(raw) or raw[i + 2] not in _DIGITS:
        raise ValueError(f"fd-dup '{fd}>&' is missing single-digit target fd")
    op = f"{fd}>&{raw[i + 2]}"
    if op not in _REDIR_OPS_NO_TARGET:
        raise ValueError(f"unsupported fd-dup '{op}' (only 2>&1 and 1>&2 are allowed)")
    return op, 3


def _split_commands(raw):
    segments = [[]]
    last = None
    for t in raw:
        if t in _DIVIDERS:
            if not segments[-1]:
                raise ValueError(f"empty command before '{t}'")
            segments.append([])
            last = t
        else:
            segments[-1].append(t)
    if not segments[-1]:
        raise ValueError(f"empty command after '{last}'")
    return segments


def _tokenize(raw):
    out = []
    i = 0
    while i < len(raw):
        t = raw[i]
        if msg := _OOS_OPS.get(t):
            raise ValueError(msg)
        op, advance = _try_digit_prefix(raw, i)
        if op is not None:
            out.append(("REDIR", op))
            i += advance
            continue
        if t == ">&":
            raise ValueError("fd-dup requires explicit source fd; got '>&...'")
        if t in (">", ">>", "<", "&>"):
            out.append(("REDIR", t))
        elif t and all(c in "();<>|&" for c in t):
            raise ValueError(f"unsupported operator: '{t}'")
        else:
            out.append(("WORD", t))
        i += 1
    return out


def _extract_redirects(tokens):
    redirects = []
    words = []
    i = 0
    while i < len(tokens):
        kind, text = tokens[i]
        if kind == "WORD":
            words.append(text)
            i += 1
        elif text in _REDIR_OPS_NO_TARGET:
            redirects.append({"operator": text})
            i += 1
        elif i + 1 < len(tokens) and tokens[i + 1][0] == "WORD":
            redirects.append({"operator": text, "target": tokens[i + 1][1]})
            i += 2
        else:
            raise ValueError(f"redirect operator '{text}' has no target")
    return words, redirects


def _classify(words):
    command = None
    positionals = []
    keywords = {}
    positional_only = False
    i = 0
    while i < len(words):
        w = words[i]
        i += 1
        if positional_only:
            positionals.append(w)
        elif w == "--":
            positional_only = True
        elif w.startswith("--") and "=" in w:
            key, _, value = w.partition("=")
            if key == "--":
                raise ValueError(f"empty key in '{w}'")
            keywords.setdefault(key, []).append(value)
        elif w.startswith("-") and w not in ("--", "-"):
            if i < len(words) and not words[i].startswith("-"):
                keywords.setdefault(w, []).append(words[i])
                i += 1
            else:
                keywords.setdefault(w, []).append(True)
        elif command is None:
            command = w
        else:
            positionals.append(w)
    if command is None:
        raise ValueError("no command token in input")
    return command, positionals, {k: v[0] if len(v) == 1 else v for k, v in keywords.items()}


# Layer 1: multi-char introducers that begin (or wholly form) a shell-
# expansion vector. Order matters — '$((' must precede '$(' so the longer
# prefix wins.
_EXPANSION_PATTERNS = (
    ("$((", "arithmetic expansion '$((...))'"),
    ("$(", "command substitution '$(...)'"),
    ("${", "variable expansion '${...}'"),
    ("$[", "arithmetic expansion '$[...]'"),
    ("$'", "ANSI-C quoting \"$'...'\""),
    ('$"', "locale-aware string '$\"...\"'"),
    ("`", "backtick command substitution"),
    ("<(", "process substitution '<(...)'"),
    (">(", "process substitution '>(...)'"),
)

# Layer 2: $VAR, $_x, $1, $@, $*, $#, $?, $!, $$, $- — names, positional
# and special vars. ('-' must be last in the char class to avoid being
# parsed as a range.)
_VAR_RE = re.compile(r"\$[A-Za-z0-9_@*#?!$-]")


def _scan_injection(s):
    """Return rejection reason if s embeds a shell-expansion vector, else None.

    Detection layers, in order:
      1. Multi-char introducers (_EXPANSION_PATTERNS).
      2. $VAR / special-variable expansion (_VAR_RE).
      3. Stray '$' fallback — defense-in-depth for any '$' that escaped
         layers 1 and 2.

    Bare operators (<, >, >>, &&, ;) inside a token are NOT scanned here:
    they are detected structurally by _tokenize and _split_commands when
    unquoted, and are inert literal characters when quoted into a token
    (bash does not re-parse them at runtime).
    """
    for needle, msg in _EXPANSION_PATTERNS:
        if needle in s:
            return msg
    if _VAR_RE.search(s):
        return "variable expansion '$VAR'"
    if "$" in s:
        return "stray '$'"
    return None


def _segment_words(seg):
    """Yield every user-supplied word in a parsed segment.

    Both keyword keys and values are scanned: a payload like
    `cmd --"$VAR"=foo` parses to key '--$VAR', which would re-evaluate
    if reassembled into a shell command.
    """
    yield seg["command"]
    yield from seg["positionals"]
    for k, v in seg["keywords"].items():
        yield k
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, str):
                yield x
    for r in seg["redirect"]:
        if "target" in r:
            yield r["target"]


def _find_expansions(seg):
    """Return [{token, reason}, ...] for every expansion in seg's words.

    Order follows _segment_words: command, positionals, keyword keys/values,
    redirect targets. One entry per occurrence — duplicates are recorded
    twice. Each reason is _scan_injection's first match within the token.
    """
    return [{"token": w, "reason": reason}
            for w in _segment_words(seg)
            if (reason := _scan_injection(w))]


def _parse_segment(raw):
    words, redirects = _extract_redirects(_tokenize(raw))
    command, positionals, keywords = _classify(words)
    seg = {"command": command, "positionals": positionals,
           "keywords": keywords, "redirect": redirects}
    seg["expansions"] = _find_expansions(seg)
    return seg


def parse(command_string):
    if not isinstance(command_string, str):
        raise ValueError(f"command must be a string, got {type(command_string).__name__}")
    if not command_string.strip():
        raise ValueError("empty input")

    return [_parse_segment(seg) for seg in _split_commands(_shlex_tokens(command_string))]


def _check_safe(result):
    """Return rejection reason string, or None if the command is safe."""
    if len(result) > 1:
        return "multiple commands are not allowed"
    for seg in result:
        if seg["redirect"]:
            return "redirects are not allowed"
        if seg["expansions"]:
            return seg["expansions"][0]["reason"]
    return None


# Optional remediation hints appended to BLOCKED: messages, keyed by the
# reason string that _check_safe (or _scan_injection) returns. Add an entry
# here when a rejection has a clear, single-line "do this instead" suggestion.
_REASON_HINTS = {
    "multiple commands are not allowed":
        "Use separate Bash calls when chaining is needed.",
}


def _format_blocked_message(reason):
    hint = _REASON_HINTS.get(reason)
    return f"BLOCKED: {reason}. {hint}" if hint else f"BLOCKED: {reason}"


def _run_tests():
    import unittest

    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent / "tests"))
    return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(prog="parser.py")
    ap.add_argument("subcommand", choices=("parse", "validate", "test"))
    subcmd = ap.parse_args().subcommand

    if subcmd == "test":
        sys.exit(0 if _run_tests() else 1)

    try:
        result = parse(json.load(sys.stdin)["tool_input"]["command"])
    except (ValueError, KeyError, TypeError) as e:
        print(f"parse error: {e}", file=sys.stderr)
        sys.exit(2)

    if subcmd == "parse":
        print(json.dumps(result))
    elif reason := _check_safe(result):
        print(_format_blocked_message(reason), file=sys.stderr)
        sys.exit(2)
