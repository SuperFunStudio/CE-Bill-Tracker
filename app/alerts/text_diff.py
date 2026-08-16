"""Turn a bill-text change into something a reader can act on: the actual changed lines.

A "text_update" BillChange is born at ingest time from a source hash flip — at that moment the new
full text isn't in hand yet, so the change row carries only hashes. The text refresh cycle
(run_bill_text_refresh_cycle) is the one place both versions coexist: the old bill_texts row is
still stored when the new text arrives. It calls compute_text_diff there and stamps the payload
onto the pending change row, so by the time the dispatcher renders the email (the first dispatch
window opens after the refresh job) the alert can say WHAT changed, not just that something did.

Whitespace-only edits are the reason `empty` exists: sources re-render documents (spacing, line
wraps) without changing a word, and a "text changed" alert for that erodes trust in the channel.
Lines are normalized (collapsed internal whitespace, blank lines dropped) before diffing, and an
empty normalized diff marks the change as not alert-worthy (see detector.is_alert_worthy).
"""
from __future__ import annotations

import difflib
import re

# Caps keep the JSONB payload and the email bounded: an omnibus rewrite produces megabytes of diff
# nobody reads in an inbox — the first few hunks + the counts carry the signal, the bill page has
# the full text.
MAX_HUNKS = 5
MAX_HUNK_LINES = 12
MAX_LINE_CHARS = 240
MAX_TOTAL_CHARS = 4000

_WS = re.compile(r"\s+")


def _normalized_lines(text: str) -> list[str]:
    """Lines with collapsed internal whitespace, blanks dropped — the comparison alphabet."""
    out = []
    for line in text.splitlines():
        collapsed = _WS.sub(" ", line).strip()
        if collapsed:
            out.append(collapsed)
    return out


def compute_text_diff(old_text: str, new_text: str) -> dict:
    """Trimmed unified diff between two bill-text versions, as a JSONB-ready payload.

    Returns {"empty": bool, "added": n, "removed": n, "hunks": [str, ...], "truncated": bool}.
    `empty` True means the versions are identical after whitespace normalization — a formatting
    re-render, not an amendment. `hunks` are unified-diff fragments (with @@ headers) capped in
    count, lines and characters; `added`/`removed` count ALL changed lines, so the email can say
    "+120 / −85 lines" even when only the first hunks are shown.
    """
    old_lines = _normalized_lines(old_text or "")
    new_lines = _normalized_lines(new_text or "")
    if old_lines == new_lines:
        return {"empty": True, "added": 0, "removed": 0, "hunks": [], "truncated": False}

    diff_lines = list(
        difflib.unified_diff(old_lines, new_lines, lineterm="", n=1)
    )[2:]  # drop the ---/+++ file headers; there are no files here

    added = sum(1 for line in diff_lines if line.startswith("+"))
    removed = sum(1 for line in diff_lines if line.startswith("-"))

    # Regroup into hunks on the @@ markers, applying the caps.
    hunks: list[str] = []
    current: list[str] = []
    total_chars = 0
    truncated = False
    for line in diff_lines:
        if line.startswith("@@"):
            if current:
                hunks.append("\n".join(current))
            if len(hunks) >= MAX_HUNKS:
                truncated = True
                current = []
                break
            current = [line]
            continue
        if not current:
            continue
        if len(current) - 1 >= MAX_HUNK_LINES:
            truncated = True
            continue
        clipped = line if len(line) <= MAX_LINE_CHARS else line[: MAX_LINE_CHARS - 1] + "…"
        total_chars += len(clipped)
        if total_chars > MAX_TOTAL_CHARS:
            truncated = True
            break
        current.append(clipped)
    if current and len(hunks) < MAX_HUNKS:
        hunks.append("\n".join(current))

    return {
        "empty": False,
        "added": added,
        "removed": removed,
        "hunks": hunks,
        "truncated": truncated,
    }
