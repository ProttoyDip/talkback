"""Documents and research projects panel routes (plan P8).

Every request reaches only the token's user's rows. An upload is checked
(type by content, 5 MB, 20 documents) and stored as 'processing'; reading
and indexing run after the response, and the panel polls for the result.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, UploadFile

from .auth import Claims, session_claims
from .config import Settings, get_settings
from .knowledge import MAX_BYTES, DocumentProblem, Knowledge
from .protocol import DocumentItem, DocumentList, Id, ProjectCreate, ProjectDetail, ProjectItem, ProjectList
from .stores import stores_for

router = APIRouter(prefix="/api", dependencies=[Depends(session_claims)])


def get_knowledge(settings: Annotated[Settings, Depends(get_settings)], claims: Claims) -> Knowledge:
    return stores_for(settings, claims.user_id).knowledge()


Store = Annotated[Knowledge, Depends(get_knowledge)]


def _problem(problem: DocumentProblem):
    return HTTPException(problem.status, problem.message)


@router.get("/documents", response_model=DocumentList)
def list_documents(store: Store) -> DocumentList:
    return DocumentList(items=store.documents())


@router.post("/documents", response_model=DocumentItem, status_code=201)
async def add_document(request: Request, file: UploadFile, store: Store, tasks: BackgroundTasks) -> DocumentItem:
    length = request.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > MAX_BYTES + 64 * 1024:
        raise HTTPException(413, "Files can be up to 5 MB.")
    data = await file.read(MAX_BYTES + 1)
    try:
        item, kind = store.add_document(file.filename or "document", data)
    except DocumentProblem as problem:
        raise _problem(problem) from None
    tasks.add_task(store.ingest, item.id, kind, data)
    return item


@router.delete("/documents/{identifier}", status_code=204)
def delete_document(identifier: Id, store: Store) -> Response:
    if not store.delete_document(identifier):
        raise HTTPException(404, "Not found")
    return Response(status_code=204)


@router.get("/projects", response_model=ProjectList)
def list_projects(store: Store) -> ProjectList:
    return ProjectList(items=store.projects())


@router.post("/projects", response_model=ProjectItem, status_code=201)
def create_project(body: ProjectCreate, store: Store) -> ProjectItem:
    try:
        return store.create_project(body.name, body.description)
    except DocumentProblem as problem:
        raise _problem(problem) from None


@router.get("/projects/{identifier}", response_model=ProjectDetail)
def get_project(identifier: Id, store: Store) -> ProjectDetail:
    detail = store.project(identifier)
    if detail is None:
        raise HTTPException(404, "Not found")
    return detail


@router.delete("/projects/{identifier}", status_code=204)
def delete_project(identifier: Id, store: Store) -> Response:
    if not store.delete_project(identifier):
        raise HTTPException(404, "Not found")
    return Response(status_code=204)


@router.delete("/projects/{identifier}/notes/{note_id}", status_code=204)
def delete_note(identifier: Id, note_id: Id, store: Store) -> Response:
    if not store.delete_note(identifier, note_id):
        raise HTTPException(404, "Not found")
    return Response(status_code=204)
