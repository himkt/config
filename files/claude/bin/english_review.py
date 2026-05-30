#!/usr/bin/env python3
"""English-review Stop hook. Samples sessions, scores newly-added user messages since the last watermark, and stores results in SQLite."""

import json
import os
import pathlib
import random
import re
import sqlite3
import subprocess
import sys
import traceback
from datetime import datetime

SAMPLE_RATE = 0.1
MODEL = "claude-opus-4-7"
DB_DIR = pathlib.Path.home() / ".local" / "share" / "claude-code" / "english-review"
DB_PATH = DB_DIR / "reviews.db"
FORMAT_SPEC_PATH = pathlib.Path(__file__).resolve().parent.parent / "skills" / "english-review" / "format.md"
NO_ENGLISH_SENTINEL = "NO_ENGLISH_CONTENT"

_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)

PROMPT_TEMPLATE = """\
Review the user's English writing from a chat transcript below. \
Ignore the assistant's replies; focus only on the user-authored text.

Follow the output format defined in the spec below exactly. Do not add \
preamble, commentary, or headers beyond what the spec allows.

--- FORMAT SPEC BEGINS ---
{format_spec}
--- FORMAT SPEC ENDS ---

Additional rule for this run: if the user text contains no English worth \
reviewing (entirely in another language, or only trivial greetings), output \
exactly this single line and nothing else:
{sentinel}

--- USER TEXT BEGINS ---
{user_text}
--- USER TEXT ENDS ---
"""

SYSTEM_PROMPT = (
    "You are a writing assistant that reviews English text. "
    "You have no tools available. Output only what the user asks for, in the format they specify."
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    last_user_message_uuid TEXT NOT NULL,
    review_markdown TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS session_progress (
    session_id TEXT PRIMARY KEY,
    last_scored_uuid TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    traceback TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def open_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.executescript(SCHEMA)
    return conn


def get_last_scored_uuid(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute(
        "SELECT last_scored_uuid FROM session_progress WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return row[0] if row else None


def extract_new_user_text(
    transcript_path: pathlib.Path,
    last_scored_uuid: str | None,
) -> tuple[str, str | None]:
    """Return (joined_user_text, last_uuid_seen) for user entries after the watermark."""
    parts: list[str] = []
    last_uuid: str | None = None
    skipping = last_scored_uuid is not None
    with transcript_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            uuid = rec.get("uuid")
            if skipping:
                if uuid == last_scored_uuid:
                    skipping = False
                continue
            if rec.get("type") != "user":
                continue
            if rec.get("isSidechain"):
                continue
            msg = rec.get("message") or {}
            content = msg.get("content")
            chunk: list[str] = []
            if isinstance(content, str):
                chunk.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text")
                        if isinstance(text, str):
                            chunk.append(text)
            if not chunk:
                continue
            parts.append("\n".join(chunk))
            if uuid:
                last_uuid = uuid
    if skipping:
        return "", None
    joined = "\n\n".join(p for p in parts if p)
    return _FENCE_RE.sub("[code omitted]", joined).strip(), last_uuid


def load_format_spec() -> str:
    return FORMAT_SPEC_PATH.read_text(encoding="utf-8").strip()


def run_review(user_text: str, format_spec: str) -> str:
    prompt = PROMPT_TEMPLATE.format(
        sentinel=NO_ENGLISH_SENTINEL,
        format_spec=format_spec,
        user_text=user_text,
    )
    env = {**os.environ, "ENGLISH_REVIEW_HOOK_IN_PROGRESS": "1"}
    result = subprocess.run(
        [
            "claude", "-p", prompt,
            "--model", MODEL,
            "--system-prompt", SYSTEM_PROMPT,
            "--no-session-persistence",
            "--tools", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--disable-slash-commands",
            "--settings", '{"disableAllHooks": true}',
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def insert_review(conn: sqlite3.Connection, session_id: str, last_uuid: str, review: str) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO reviews (session_id, last_user_message_uuid, review_markdown, created_at) VALUES (?, ?, ?, ?)",
        (session_id, last_uuid, review, now),
    )


def upsert_progress(conn: sqlite3.Connection, session_id: str, last_uuid: str) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO session_progress (session_id, last_scored_uuid, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET last_scored_uuid = excluded.last_scored_uuid, updated_at = excluded.updated_at",
        (session_id, last_uuid, now),
    )


def log_error(session_id: str | None) -> None:
    try:
        conn = open_db()
        try:
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            conn.execute(
                "INSERT INTO errors (session_id, traceback, created_at) VALUES (?, ?, ?)",
                (session_id, traceback.format_exc(), now),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass  # last-resort swallow; the hook must never break the parent session


def main() -> None:
    session_id: str | None = None
    try:
        if os.environ.get("ENGLISH_REVIEW_HOOK_IN_PROGRESS"):
            return  # spawned by our own claude -p call; break the recursion
        if random.random() >= SAMPLE_RATE:
            return
        data = json.load(sys.stdin)
        if data.get("stop_hook_active"):
            return
        transcript_path = pathlib.Path(data["transcript_path"])
        session_id = data["session_id"]

        conn = open_db()
        try:
            last_scored_uuid = get_last_scored_uuid(conn, session_id)
            user_text, last_uuid = extract_new_user_text(transcript_path, last_scored_uuid)
            if not user_text or not last_uuid:
                return
            format_spec = load_format_spec()
            if not format_spec:
                return
            review = run_review(user_text, format_spec)
            if review and review != NO_ENGLISH_SENTINEL:
                insert_review(conn, session_id, last_uuid, review)
            # Advance the watermark whether or not we produced a review,
            # so the same passages aren't re-scored on the next Stop.
            upsert_progress(conn, session_id, last_uuid)
            conn.commit()
        finally:
            conn.close()
    except Exception:
        log_error(session_id)
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
