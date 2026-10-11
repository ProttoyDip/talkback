"""Memory panel routes. Each request reaches only the token's user's memories."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .auth import Claims, session_claims
from .config import Settings, get_settings
from .memory import MemoryStore
from .protocol import Id, MemoryItem, MemoryList, MemoryUpdate
from .actions import ActionLedger
from .stores import memory_store, repo

router = APIRouter(prefix="/api/memories", dependencies=[Depends(session_claims)])


def get_memory_store(settings: Annotated[Settings, Depends(get_settings)], claims: Claims) -> MemoryStore:
    return memory_store(settings, claims.user_id)  # Supabase when configured, else local SQLite


Store = Annotated[MemoryStore, Depends(get_memory_store)]


def get_ledger(settings: Annotated[Settings, Depends(get_settings)], claims: Claims, store: Store) -> ActionLedger:
    return ActionLedger(
        repo(settings, "actions", claims.user_id), store, claims.session_id,
        tables=lambda table: repo(settings, table, claims.user_id),
    )


Ledger = Annotated[ActionLedger, Depends(get_ledger)]


@router.get("", response_model=MemoryList)
def list_memories(
    store: Store, q: Annotated[str, Query(max_length=500)] = "", history: bool = False,
) -> MemoryList:
    """Memories in use and suggestions; history=1 adds the ones corrections replaced."""
    return MemoryList(items=store.list(q, history=history))


@router.patch("/{identifier}", response_model=MemoryItem)
def edit_memory(identifier: Id, update: MemoryUpdate, store: Store, ledger: Ledger) -> MemoryItem:
    before = store.row(identifier)
    try:
        item = store.update(identifier, update)
    except ValueError:
        raise HTTPException(409, "Only a suggestion can be confirmed or dismissed") from None
    if item is None or before is None:
        raise HTTPException(404, "Memory not found")
    after = store.row(identifier)
    verb = {"confirmed": "Kept the suggestion", "dismissed": "Dismissed the suggestion"}.get(update.status or "", "Edited")
    ledger.record(
        "memory_write", "done", f"{verb} “{item.text}”", target_kind="memory", target_id=item.id,
        undo={
            "op": "memory.revert", "id": item.id, "after_updated_at": after["updated_at"],
            "before": {k: before[k] for k in ("text", "kind", "status", "updated_at")},
        },
    )
    return item


@router.delete("/{identifier}", status_code=204)
def delete_memory(identifier: Id, store: Store, ledger: Ledger) -> Response:
    row = store.row(identifier)
    if row is None or not store.delete(identifier):
        raise HTTPException(404, "Memory not found")
    ledger.record(
        "memory_delete", "done", f"Forgot “{row['text']}”", target_kind="memory", target_id=identifier,
        undo={"op": "memory.restore", "rows": [row]},
    )
    return Response(status_code=204)


@router.delete("", status_code=204)
def forget_everything(store: Store, ledger: Ledger) -> Response:
    rows = store.all_rows()
    store.delete_all()
    if rows:
        action = ledger.record(
            "memory_delete", "done", f"Forgot all {len(rows)} memories", target_kind="memory",
            undo={"op": "memory.restore", "rows": rows},
        )
        ledger.forget_history(keep=action["id"])  # only this undo keeps a copy, for 24 hours
    return Response(status_code=204)
