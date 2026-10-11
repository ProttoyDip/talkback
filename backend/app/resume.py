"""Resume an unfinished conversation (plan P7).

When a conversation ends, the server keeps facts it can stand behind: the
user's goal (their own words), what was done (the action history of that
session), and what was still open (a plan or a question waiting for their
OK). No transcript, unless the user turned on "keep the last 6 turns"
(SECURITY.md T10). Next time, the user may continue; open items are asked
again, never run on their own.
"""

from datetime import timedelta

from .db.repo import IsNull, Lte, Repo
from .protocol import SessionResumable
from .timeutil import iso, now_utc

RESUME_WITHIN = timedelta(hours=24)
RECENT_TURNS = 6


def save_state(
    states: Repo, actions: Repo, proposals: Repo, *, session_id: str, goal: str | None,
    waiting_for: list[str], recent: list[dict] | None, since: str | None = None,
) -> dict | None:
    """Keep what is needed to continue; nothing when there is nothing to continue.

    `since` is when this conversation started: only its own plans count.
    """
    if not goal:
        return None
    latest = actions.select({"session_id": session_id}, order="created_at.desc", limit=10)
    done = [a["summary"] for a in reversed(latest) if a["status"] == "done"]
    tools = sorted({a["tool"] for a in latest if a["status"] == "done"})
    pending = list(waiting_for)
    for row in proposals.select({"status": "pending"}, limit=5):
        if row["expires_at"] > iso(now_utc()) and (since is None or row["created_at"] >= since):
            pending.append(f"A day plan for {row['date']} was waiting for your OK")
    existing = states.select({"session_id": session_id, "status": "open"}, limit=1)
    if not done and not pending:
        if existing:  # it was unfinished, and is not any more
            states.delete(existing[0]["id"])
        return None  # finished: nothing to pick up
    values = {
        "session_id": session_id, "goal": goal[:200], "decisions": done, "pending": pending[:10],
        # What the model may be told: tool names only, never model-written text (T1).
        "tools_used": tools,
        "recent_turns": recent[-RECENT_TURNS:] if recent else None, "status": "open",
    }
    # One row per conversation, updated as it goes.
    return states.update(existing[0]["id"], values) if existing else states.insert(values)


def offer(states: Repo, current_session: str) -> SessionResumable | None:
    """The newest open state from the last 24 hours, from another conversation."""
    cutoff = iso(now_utc() - RESUME_WITHIN)
    # Kept for a day only (Settings says so): older states are deleted.
    for old in states.select({"updated_at": Lte(cutoff)}, limit=50):
        states.delete(old["id"])
    for row in states.select({"status": "open", "closed_at": IsNull()}, order="updated_at.desc", limit=5):
        if row["session_id"] != current_session and row["updated_at"] >= cutoff:
            return SessionResumable(
                state_id=row["id"], goal=row["goal"], decisions=row["decisions"] or [],
                pending=row["pending"] or [], updated_at=row["updated_at"],
            )
    return None


def answer(states: Repo, state_id: str, accept: bool, current_session: str) -> dict | None:
    """Continue (resumed) or start fresh (dismissed): only what offer() would offer."""
    row = states.get(state_id)
    cutoff = iso(now_utc() - RESUME_WITHIN)
    if row is None or row["status"] != "open" or row["session_id"] == current_session or row["updated_at"] < cutoff:
        return None
    states.update(state_id, {"status": "resumed" if accept else "dismissed", "closed_at": iso(now_utc())})
    return row


def context_note(row: dict) -> str:
    """What the model is told when the user continues: data, not instructions."""
    # The goal is the user's own words. What was done and what is open come
    # from model-written tool arguments, so the model gets counts and tool
    # names only; it can list tasks or the calendar for details (T1).
    parts = [f'The user is continuing an earlier conversation. Their goal then, in their words: "{row["goal"]}".']
    if row.get("decisions"):
        tools = ", ".join(row.get("tools_used") or []) or "tools"
        parts.append(f"{len(row['decisions'])} change(s) were made then with: {tools}.")
    if row.get("pending"):
        parts.append(f"{len(row['pending'])} thing(s) were still waiting for their OK: ask what they want before doing any.")
    return "(" + " ".join(parts) + ")"


def forget(states: Repo, turns_only: bool = False) -> None:
    """Delete stored states (or just their kept turns): forgetting, or a switch turned off."""
    for row in states.select(limit=500):
        if turns_only:
            if row.get("recent_turns"):
                states.update(row["id"], {"recent_turns": None})
        else:
            states.delete(row["id"])
