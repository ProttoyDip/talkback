"""Bearer-authenticated memory panel routes for the single-user deployment."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings
from .memory import MemoryStore
from .protocol import Id, MemoryItem, MemoryList, MemoryUpdate
from .tokens import verify_token

bearer = HTTPBearer(auto_error=False)


def require_session(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> None:
    if credentials is None or verify_token(settings.signing_key(), credentials.credentials) is None:
        raise HTTPException(401, "Invalid or expired session token", headers={"WWW-Authenticate": "Bearer"})


router = APIRouter(prefix="/api/memories", dependencies=[Depends(require_session)])


def get_memory_store(settings: Annotated[Settings, Depends(get_settings)]) -> MemoryStore:
    return MemoryStore(settings.memory_db_path)


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
