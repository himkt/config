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
import re
import shlex
import sys


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

    class CommandParserTests(unittest.TestCase):
        def assertSingle(self, src):
            r = parse(src)
            self.assertEqual(len(r), 1, f"{src!r} parsed to {len(r)} segments")
            return r[0]

        def assertField(self, src, field, expected):
            self.assertEqual(self.assertSingle(src)[field], expected)

        def test_quoting(self):
            for src, pos in [
                ("echo 'a\\b\"c'", ["a\\b\"c"]),
                ('echo "a\\"b\\\\c"', ['a"b\\c']),
                ('echo "\\n"', ['\\n']),
                ("echo foo\\ bar", ["foo bar"]),
                ("echo a\\\\b", ["a\\b"]),
                ("echo ''", [""]),
                ('echo "a"\'b\'c', ["abc"]),
            ]:
                with self.subTest(src=src):
                    self.assertField(src, "positionals", pos)

        def test_whitespace(self):
            expected = {"command": "cmd", "positionals": ["arg"], "keywords": {},
                        "redirect": [], "expansions": []}
            for src in ("cmd\narg", "cmd\rarg", "cmd\targ", "  cmd  arg  "):
                with self.subTest(src=repr(src)):
                    self.assertEqual(self.assertSingle(src), expected)

        def test_keywords(self):
            for src, kw in [
                ("python3 -v", {"-v": True}),
                ("cmd -c hello", {"-c": "hello"}),
                ("cmd --name=foo", {"--name": "foo"}),
                ('cmd --path="my dir"', {"--path": "my dir"}),
                ("cmd --key=", {"--key": ""}),
                ("cmd -I a -I b", {"-I": ["a", "b"]}),
                ("cmd -v -v", {"-v": [True, True]}),
                ("cmd -x 1 -x", {"-x": ["1", True]}),
                ("cmd -- -v --foo bar", {}),  # -- ends flag parsing
            ]:
                with self.subTest(src=src):
                    self.assertField(src, "keywords", kw)

        def test_redirects(self):
            for src, redir in [
                ("cmd > out", [{"operator": ">", "target": "out"}]),
                ("cmd >> out", [{"operator": ">>", "target": "out"}]),
                ("cmd 1> out", [{"operator": "1>", "target": "out"}]),
                ("cmd 2> err", [{"operator": "2>", "target": "err"}]),
                ("cmd 2>> err", [{"operator": "2>>", "target": "err"}]),
                ("cmd 0< in", [{"operator": "0<", "target": "in"}]),
                ("cmd &> all", [{"operator": "&>", "target": "all"}]),
                ("cmd 2>&1", [{"operator": "2>&1"}]),
                ("cmd 1>&2", [{"operator": "1>&2"}]),
            ]:
                with self.subTest(src=src):
                    self.assertField(src, "redirect", redir)

        def test_dividers_split_segments(self):
            # |, ;, &&, || all split into separate segments uniformly.
            for src, n in [
                ("cmd", 1),
                ("a | b", 2),
                ("a ; b", 2),
                ("a && b", 2),
                ("a || b", 2),
                ("a | b ; c && d || e", 5),
                ('echo "a|b;c&&d"', 1),  # quoted: stays in one token
            ]:
                with self.subTest(src=src):
                    self.assertEqual(len(parse(src)), n)

        def test_errors(self):
            for src in [
                "", "   ",
                "cat 'foo", 'echo "foo', "echo foo\\",
                "echo >", "echo > >",
                "|", "| cmd", "cmd |", "a | | b",
                "; cmd", "cmd ;", "&& cmd", "cmd ||",
                "cmd &", "cat <<EOF", "cat <<<x",
                "-v", "> out", "--name=foo", "cmd --=value",
                "cmd >&1", "cmd 3>&1", "cmd 2>&", "cmd 2>&x",
                "cmd <>file", "cmd ()", "cmd >>>file", "cmd >|file",
                123, None, [], {},
            ]:
                with self.subTest(src=src):
                    with self.assertRaises(ValueError):
                        parse(src)

        def test_expansions(self):
            # (input, [(token, reason), ...]) — covers detection across all
            # word positions and all reason categories. Verified end-to-end
            # via parse().
            cases = [
                # Safe.
                ("echo hello", []),
                ("cmd --foo=bar", []),
                # Specific shell-expansion patterns.
                ('echo "$(x)"', [("$(x)", "command substitution '$(...)'")]),
                ('echo "${x}"', [("${x}", "variable expansion '${...}'")]),
                ('echo "$((1+1))"', [("$((1+1))", "arithmetic expansion '$((...))'")]),
                ('echo "$[1+1]"', [("$[1+1]", "arithmetic expansion '$[...]'")]),
                ('echo "$\'x\'"', [("$'x'", "ANSI-C quoting \"$'...'\"")]),
                ('echo "$\\"x\\""', [('$"x"', "locale-aware string '$\"...\"'")]),
                ("echo '`id`'", [("`id`", "backtick command substitution")]),
                ('echo "<(x)"', [("<(x)", "process substitution '<(...)'")]),
                ('echo ">(x)"', [(">(x)", "process substitution '>(...)'")]),
                # $VAR and special vars.
                ('echo "$X"', [("$X", "variable expansion '$VAR'")]),
                ('echo "$5"', [("$5", "variable expansion '$VAR'")]),
                ('echo "$@"', [("$@", "variable expansion '$VAR'")]),
                ('echo "$$"', [("$$", "variable expansion '$VAR'")]),
                ('echo "$-"', [("$-", "variable expansion '$VAR'")]),
                # Layer-3 catch-all: stray '$' that didn't form a recognized
                # expansion pattern.
                ("echo 'price $'", [("price $", "stray '$'")]),
                # Offender at command position.
                ('"$cmd" arg', [("$cmd", "variable expansion '$VAR'")]),
                # Offender in keyword value.
                ('cmd --opt="$x"', [("$x", "variable expansion '$VAR'")]),
                # Offender in keyword key (injected via quoting).
                ('cmd --"$VAR"=foo', [("--$VAR", "variable expansion '$VAR'")]),
                # Offender in redirect target.
                ('cmd > "$out"', [("$out", "variable expansion '$VAR'")]),
                # Multi-list keyword: each list element scanned.
                ('cmd -I a -I "$X"', [("$X", "variable expansion '$VAR'")]),
                # Multiple offenders preserve discovery order.
                ('echo "$X" "${Y}"', [
                    ("$X", "variable expansion '$VAR'"),
                    ("${Y}", "variable expansion '${...}'"),
                ]),
                # Duplicate offender recorded twice (per occurrence).
                ('echo "$X" "$X"', [
                    ("$X", "variable expansion '$VAR'"),
                    ("$X", "variable expansion '$VAR'"),
                ]),
                # Single token with multiple patterns: substring beats regex.
                ('echo "$VAR$(x)"', [("$VAR$(x)", "command substitution '$(...)'")]),
            ]
            for src, expected in cases:
                with self.subTest(src=src):
                    actual = self.assertSingle(src)["expansions"]
                    self.assertEqual(
                        [(e["token"], e["reason"]) for e in actual], expected,
                    )

        def test_quoted_operators_allowed(self):
            """Operators surviving into a token are inert; allowed.

            Redirects (<, >, >>) and command separators (;, &&, ||) are
            detected structurally when unquoted (see test_redirects,
            test_dividers_split_segments). When they appear inside a quoted
            token, bash treats them as literal characters at runtime, so
            _scan_injection lets them pass.
            """
            for src in [
                "echo 'a;b'",
                "echo '<div>'",
                "echo 'a&&b'",
                "echo 'a>>b'",
                "echo 'a>b'",
                "echo 'a||b'",
                # Motivating case: a jq comparison passed as a flag value.
                "gh api repo --jq '.x > 0'",
                "jq '[.[] | select(.n >= 5)]'",
            ]:
                with self.subTest(src=src):
                    self.assertField(src, "expansions", [])

        def test_unquoted_operators_still_rejected(self):
            """Structural detection of unquoted operators is unaffected by
            the token-level relaxation."""
            for src, reason in [
                ("cmd a > b", "redirects are not allowed"),
                ("cmd a >> b", "redirects are not allowed"),
                ("cmd a < b", "redirects are not allowed"),
                ("cmd a 2> b", "redirects are not allowed"),
                ("cmd a; cmd b", "multiple commands are not allowed"),
                ("cmd a && cmd b", "multiple commands are not allowed"),
                ("cmd a || cmd b", "multiple commands are not allowed"),
                ("cmd a | cmd b", "multiple commands are not allowed"),
            ]:
                with self.subTest(src=src):
                    self.assertEqual(_check_safe(parse(src)), reason)

        def test_blocked_message(self):
            """Reasons with a registered hint get an actionable suffix; others
            fall back to bare 'BLOCKED: <reason>'."""
            self.assertEqual(
                _format_blocked_message("multiple commands are not allowed"),
                "BLOCKED: multiple commands are not allowed. "
                "Use separate Bash calls when chaining is needed.",
            )
            for reason in [
                "redirects are not allowed",
                "command substitution '$(...)'",
                "variable expansion '$VAR'",
                "stray '$'",
            ]:
                with self.subTest(reason=reason):
                    self.assertEqual(
                        _format_blocked_message(reason), f"BLOCKED: {reason}",
                    )

        def test_check_safe(self):
            def seg(cmd="cmd", redir=()):
                s = {"command": cmd, "positionals": [], "keywords": {},
                     "redirect": list(redir)}
                s["expansions"] = _find_expansions(s)
                return s

            plain = seg()
            with_redir = seg(redir=[{"operator": ">", "target": "out"}])
            with_expansion = seg(cmd="$x")
            for result, expected in [
                ([plain], None),
                ([plain, plain], "multiple commands are not allowed"),
                ([with_redir], "redirects are not allowed"),
                ([with_expansion], "variable expansion '$VAR'"),
                # Multi-segment check fires before redirect/expansion checks.
                ([with_redir, plain], "multiple commands are not allowed"),
                # Validate end-to-end via parse(): real-world payloads.
                (parse('echo "$(x)"'), "command substitution '$(...)'"),
                (parse("cmd > out"), "redirects are not allowed"),
                (parse("a; b"), "multiple commands are not allowed"),
            ]:
                with self.subTest(result=result):
                    self.assertEqual(_check_safe(result), expected)

        def test_segment_words_yield_order(self):
            seg = {
                "command": "cmd",
                "positionals": ["a", "b"],
                "keywords": {"-x": "v1", "-I": ["v2", "v3"], "-flag": True},
                "redirect": [{"operator": ">", "target": "out"},
                             {"operator": "2>&1"}],
            }
            self.assertEqual(
                list(_segment_words(seg)),
                ["cmd", "a", "b", "-x", "v1", "-I", "v2", "v3", "-flag", "out"],
            )

    suite = unittest.TestLoader().loadTestsFromTestCase(CommandParserTests)
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
