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
    waiting_for: list[str], recent: list[dict] | None,
) -> dict | None:
    """Keep what is needed to continue; nothing when there is nothing to continue."""
    if not goal:
        return None
    done = [
        a["summary"] for a in actions.select({"session_id": session_id}, order="created_at.asc", limit=50)
        if a["status"] == "done"
    ][-10:]
    pending = list(waiting_for)
    for row in proposals.select({"status": "pending"}, limit=5):
        if row["expires_at"] > iso(now_utc()):
            pending.append(f"A day plan for {row['date']} was waiting for your OK")
    if not done and not pending:
        return None  # finished: nothing to pick up
    return states.insert({
        "session_id": session_id, "goal": goal[:200], "decisions": done, "pending": pending[:10],
        "recent_turns": recent[-RECENT_TURNS:] if recent else None, "status": "open",
    })


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


def answer(states: Repo, state_id: str, accept: bool) -> dict | None:
    """Continue (resumed) or start fresh (dismissed). Only an open state."""
    row = states.get(state_id)
    if row is None or row["status"] != "open":
        return None
    states.update(state_id, {"status": "resumed" if accept else "dismissed", "closed_at": iso(now_utc())})
    return row


def context_note(row: dict) -> str:
    """What the model is told when the user continues: data, not instructions."""
    parts = [f'The user is continuing an earlier conversation. Their goal then, in their words: "{row["goal"]}".']
    if row.get("decisions"):
        parts.append("Done then: " + "; ".join(row["decisions"]) + ".")
    if row.get("pending"):
        parts.append("Still open (ask again before doing any of it): " + "; ".join(row["pending"]) + ".")
    return "(" + " ".join(parts) + ")"
