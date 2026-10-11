"""Memory panel routes. Each request reaches only the token's user's memories."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from .auth import Claims, session_claims
from .config import Settings, get_settings
from .memory import MemoryStore
from .protocol import Id, MemoryItem, MemoryList, MemoryUpdate
from .stores import memory_store

router = APIRouter(prefix="/api/memories", dependencies=[Depends(session_claims)])


def get_memory_store(settings: Annotated[Settings, Depends(get_settings)], claims: Claims) -> MemoryStore:
    return memory_store(settings, claims.user_id)  # Supabase when configured, else local SQLite


Store = Annotated[MemoryStore, Depends(get_memory_store)]


@router.get("", response_model=MemoryList)
def list_memories(store: Store, q: Annotated[str, Query(max_length=500)] = "") -> MemoryList:
    return MemoryList(items=store.list(q))


@router.patch("/{identifier}", response_model=MemoryItem)
def edit_memory(identifier: Id, update: MemoryUpdate, store: Store) -> MemoryItem:
    item = store.update(identifier, update)
    if item is None:
        raise HTTPException(404, "Memory not found")
    return item


@router.delete("/{identifier}", status_code=204)
def delete_memory(identifier: Id, store: Store) -> Response:
    if not store.delete(identifier):
        raise HTTPException(404, "Memory not found")
    return Response(status_code=204)


@router.delete("", status_code=204)
def forget_everything(store: Store) -> Response:
    store.delete_all()
    return Response(status_code=204)
