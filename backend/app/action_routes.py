"""Action history routes (plan P4): what TalkBack changed, and undo."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from .actions import NotUndoable, UndoConflict
from .auth import session_claims
from .memory_routes import Ledger
from .protocol import ActionItem, ActionList, Id

router = APIRouter(prefix="/api/actions", dependencies=[Depends(session_claims)])


@router.get("", response_model=ActionList)
def list_actions(ledger: Ledger, limit: Annotated[int, Query(ge=1, le=100)] = 50) -> ActionList:
    return ActionList(items=ledger.list(limit))


@router.post("/{identifier}/undo", response_model=ActionItem)
def undo_action(identifier: Id, ledger: Ledger) -> ActionItem:
    try:
        return ledger.undo(identifier)
    except UndoConflict:
        raise HTTPException(409, "It changed since, so it can't be undone") from None
    except NotUndoable:
        raise HTTPException(404, "Nothing to undo") from None
