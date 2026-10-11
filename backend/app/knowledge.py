"""Documents and research projects (plan P8).

A user uploads PDF, TXT or MD files; their text is split into passages of
about 800 characters (100 overlapping), each with its page, and embedded
with NVIDIA embeddings. Research projects hold notes saved by voice, with
links that came from that conversation's web results only.

Searches rank passages by meaning (cosine) and words (keywords). Locally
that is a scan of the user's passages; on Supabase, the match_chunks
function. Everything found is untrusted data (SECURITY.md T1): the bridge
wraps it, the model may quote it, and the turn may not then write memory or
change anything without the user's button press.
"""

import array
import asyncio
import base64
import io
import logging
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePath

from .db.repo import In, IsNull, Repo
from .embeddings import Embedder
from .protocol import DocumentItem, ProjectDetail, ProjectItem, ProjectNote, Source
from .tool_results import plain_text

log = logging.getLogger("talkback.knowledge")

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 50
MAX_DOCUMENTS = 20
MAX_PROJECTS = 50
CHUNK = 800
OVERLAP = 100
SCAN_LIMIT = 5000  # local search reads at most this many passages
KINDS = {".pdf": "pdf", ".txt": "txt", ".md": "md", ".markdown": "md"}


class DocumentProblem(Exception):
    """A file TalkBack will not keep, with a plain reason and an HTTP status."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass(frozen=True)
class Hit:
    kind: str  # document | project_note
    source_id: str  # the document or the project
    note_id: str | None
    locator: str | None
    text: str
    score: float
    title: str = ""


def file_kind(filename: str, data: bytes) -> str:
    """pdf, txt or md, checked by content as well as by name."""
    kind = KINDS.get(PurePath(filename).suffix.lower())
    if kind is None:
        raise DocumentProblem(415, "Only PDF, TXT and Markdown files can be added.")
    if kind == "pdf" and not data.startswith(b"%PDF-"):
        raise DocumentProblem(415, "This file is not a PDF.")
    if kind != "pdf" and (b"\x00" in data[:4096]):
        raise DocumentProblem(415, "This file is not plain text.")
    return kind


def extract(kind: str, data: bytes) -> list[tuple[str | None, str]]:
    """(locator, text) per page; plain text is one part. Slow: run in a thread."""
    if kind != "pdf":
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise DocumentProblem(415, "This file is not UTF-8 text.") from None
        return [(None, " ".join(text.split()))]
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentProblem(422, "This PDF is password-protected.")
        if len(reader.pages) > MAX_PAGES:
            raise DocumentProblem(413, f"This PDF has more than {MAX_PAGES} pages.")
        return [(f"page {number}", " ".join((page.extract_text() or "").split()))
                for number, page in enumerate(reader.pages, start=1)]
    except DocumentProblem:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError):
        raise DocumentProblem(422, "This PDF could not be read.") from None


def passages(parts: list[tuple[str | None, str]]) -> list[tuple[str | None, str]]:
    """About 800 characters each, 100 shared with the next, cut at a space."""
    out = []
    for locator, text in parts:
        start = 0
        while start < len(text):
            end = min(start + CHUNK, len(text))
            if end < len(text):
                space = text.rfind(" ", start + CHUNK // 2, end)
                end = space if space > 0 else end
            piece = text[start:end].strip()
            if piece:
                out.append((locator, piece))
            if end >= len(text):
                break
            start = max(end - OVERLAP, start + 1)
    return out


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w{3,}", text.lower())}


def pack(vector: list[float]) -> str:
    """Local storage: float32, base64 (a quarter of the size of JSON)."""
    return base64.b64encode(array.array("f", vector).tobytes()).decode("ascii")


def unpack(value: str | None) -> list[float] | None:
    if not value:
        return None
    vector = array.array("f")
    vector.frombytes(base64.b64decode(value))
    return vector.tolist()


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def score(query_vec: list[float] | None, terms: set[str], text: str, vec: list[float] | None) -> float | None:
    """0.75 meaning + 0.25 words, or words alone; None: not a match."""
    found = len(terms & words(text)) / len(terms) if terms else 0.0
    if query_vec is not None and vec is not None:
        similarity = cosine(query_vec, vec)
        return 0.75 * similarity + 0.25 * found if similarity >= 0.2 or found else None
    return 0.25 * found if found else None


class Knowledge:
    """One user's documents and projects. `rpc` searches on Supabase."""

    def __init__(
        self, tables: Callable[[str], Repo], user_id: str, embedder: Embedder,
        rpc: Callable[[dict], list[dict]] | None = None,
    ) -> None:
        self.tables = tables
        self.user_id = user_id
        self.embedder = embedder
        self.rpc = rpc

    # Documents

    @staticmethod
    def document(row: dict) -> DocumentItem:
        return DocumentItem(**{k: row.get(k) for k in DocumentItem.model_fields if k in row})

    def documents(self) -> list[DocumentItem]:
        return [self.document(r) for r in self.tables("documents").select(order="created_at.desc", limit=MAX_DOCUMENTS)]

    def add_document(self, filename: str, data: bytes) -> tuple[DocumentItem, str]:
        """Checks the file and keeps a 'processing' row; ingest() reads it."""
        if len(data) > MAX_BYTES:
            raise DocumentProblem(413, "Files can be up to 5 MB.")
        if not data:
            raise DocumentProblem(422, "This file is empty.")
        kind = file_kind(filename, data)
        repo = self.tables("documents")
        if len(repo.select(limit=MAX_DOCUMENTS)) >= MAX_DOCUMENTS:
            raise DocumentProblem(409, f"You can keep up to {MAX_DOCUMENTS} documents. Delete one to add another.")
        name = plain_text(PurePath(filename).name)[:200] or f"document.{kind}"
        title = plain_text(PurePath(name).stem)[:200] or name
        row = repo.insert({
            "title": title, "filename": name, "kind": kind, "size_bytes": len(data), "status": "processing", "chunks": 0,
        })
        return self.document(row), kind

    async def ingest(self, document_id: str, kind: str, data: bytes) -> None:
        """Read, split and embed a document. Never raises: a failure is its status."""
        repo = self.tables("documents")
        try:
            parts = await asyncio.to_thread(extract, kind, data)
            pieces = passages(parts)
            if not pieces:
                raise DocumentProblem(422, "No text found. Is it a scan?")
            await self._index("document", document_id, None, pieces)
            pages = len(parts) if kind == "pdf" else None
            if await asyncio.to_thread(repo.update, document_id, {"status": "ready", "chunks": len(pieces), "pages": pages}) is None:
                # Deleted while it was being read: drop what was just indexed.
                await asyncio.to_thread(
                    self.tables("knowledge_chunks").delete_where, {"kind": "document", "source_id": document_id})
        except DocumentProblem as problem:
            await asyncio.to_thread(repo.update, document_id, {"status": "failed", "error": problem.message})
        except Exception as exc:
            log.warning("document not indexed", extra={"event": type(exc).__name__})
            try:
                await asyncio.to_thread(repo.update, document_id, {"status": "failed", "error": "This file could not be read."})
            except Exception:
                pass

    def delete_document(self, document_id: str) -> bool:
        repo = self.tables("documents")
        if repo.get(document_id) is None:
            return False
        self.tables("knowledge_chunks").delete_where({"kind": "document", "source_id": document_id})
        return repo.delete(document_id)

    async def _index(self, kind: str, source_id: str, note_id: str | None, pieces, timeout: float = 30) -> None:
        vectors = await self.embedder.embed([text for _, text in pieces], "passage", timeout=timeout)
        rows = [{
            "kind": kind, "source_id": source_id, "note_id": note_id, "ord": index, "locator": locator,
            "text": text, "embedding": self._stored(vectors[index]) if vectors else None,
        } for index, (locator, text) in enumerate(pieces)]
        await asyncio.to_thread(self.tables("knowledge_chunks").insert_many, rows)

    def _stored(self, vector: list[float]):
        return vector if self.rpc is not None else pack(vector)  # Supabase: a pgvector

    # Search

    async def search(self, kind: str, query: str, limit: int = 4, timeout: float = 2.5) -> list[Hit]:
        query_vec = None
        vectors = await self.embedder.embed([query], "query", timeout=timeout)
        if vectors:
            query_vec = vectors[0]
        hits = await asyncio.to_thread(self._search, kind, query, query_vec, limit)
        return await asyncio.to_thread(self._titled, kind, hits)

    def _search(self, kind: str, query: str, query_vec, limit: int) -> list[Hit]:
        if self.rpc is not None:
            rows = self.rpc({
                "p_user_id": self.user_id, "p_kind": kind, "p_query": query_vec, "p_text": query, "p_count": limit * 2,
            })
            return [Hit(kind, r["source_id"], r.get("note_id"), r.get("locator"), r["text"], float(r["score"]))
                    for r in rows]
        terms = words(query)
        found = []
        for row in self.tables("knowledge_chunks").select({"kind": kind}, limit=SCAN_LIMIT):
            value = score(query_vec, terms, row["text"], unpack(row.get("embedding")))
            if value is not None:
                found.append(Hit(kind, row["source_id"], row.get("note_id"), row.get("locator"), row["text"], value))
        return sorted(found, key=lambda hit: hit.score, reverse=True)[:limit * 2]

    def _titled(self, kind: str, hits: list[Hit], limit: int = 4) -> list[Hit]:
        """Names for the hits; passages of deleted notes or documents drop out."""
        if not hits:
            return []
        ids = tuple({hit.source_id for hit in hits})
        if kind == "document":
            titles = {r["id"]: r["title"] for r in self.tables("documents").select({"id": In(ids), "status": "ready"})}
            live = None
        else:
            titles = {r["id"]: r["name"] for r in self.tables("projects").select({"id": In(ids)})}
            notes = tuple({hit.note_id for hit in hits if hit.note_id})
            live = {r["id"] for r in self.tables("project_notes").select({"id": In(notes), "deleted_at": IsNull()})}
        kept = [Hit(h.kind, h.source_id, h.note_id, h.locator, h.text, h.score, titles[h.source_id])
                for h in hits if h.source_id in titles and (live is None or h.note_id in live)]
        return kept[:limit]

    # Projects

    def _project(self, row: dict) -> ProjectItem:
        notes = self.tables("project_notes").select({"project_id": row["id"], "deleted_at": IsNull()}, limit=500)
        return ProjectItem(
            id=row["id"], name=row["name"], description=row.get("description"), notes=len(notes),
            created_at=row["created_at"], updated_at=row.get("updated_at"),
        )

    def projects(self) -> list[ProjectItem]:
        return [self._project(r) for r in self.tables("projects").select(order="updated_at.desc", limit=MAX_PROJECTS)]

    def find_project(self, name: str) -> dict | None:
        wanted = " ".join(name.lower().split())
        for row in self.tables("projects").select(limit=MAX_PROJECTS):
            if " ".join(row["name"].lower().split()) == wanted:
                return row
        return None

    def create_project(self, name: str, description: str | None = None) -> ProjectItem:
        if self.find_project(name) is not None:
            raise DocumentProblem(409, "You already have a project with that name.")
        repo = self.tables("projects")
        if len(repo.select(limit=MAX_PROJECTS)) >= MAX_PROJECTS:
            raise DocumentProblem(409, f"You can keep up to {MAX_PROJECTS} projects.")
        return self._project(repo.insert({"name": name.strip(), "description": description}))

    def project(self, project_id: str) -> ProjectDetail | None:
        row = self.tables("projects").get(project_id)
        if row is None:
            return None
        notes = self.tables("project_notes").select(
            {"project_id": project_id, "deleted_at": IsNull()}, order="created_at.desc", limit=500)
        return ProjectDetail(project=self._project(row), notes=[
            ProjectNote(id=n["id"], text=n["text"], sources=n.get("sources") or [], created_at=n["created_at"])
            for n in notes
        ])

    def delete_project(self, project_id: str) -> bool:
        if self.tables("projects").get(project_id) is None:
            return False
        self.tables("knowledge_chunks").delete_where({"kind": "project_note", "source_id": project_id})
        self.tables("project_notes").delete_where({"project_id": project_id})
        return self.tables("projects").delete(project_id)

    def delete_note(self, project_id: str, note_id: str) -> bool:
        removed = self.tables("project_notes").delete(note_id, {"project_id": project_id})
        if removed:
            self.tables("knowledge_chunks").delete_where({"kind": "project_note", "note_id": note_id})
        return removed

    async def save_note(
        self, project_name: str, text: str, sources: list[Source], ledger=None, key: str | None = None,
    ) -> tuple[dict, dict, str | None]:
        """(project, note, action id). A new name starts a project."""
        project = await asyncio.to_thread(self.find_project, project_name)
        if project is None:
            item = await asyncio.to_thread(self.create_project, project_name)
            project = {"id": item.id, "name": item.name}
        note = await asyncio.to_thread(self.tables("project_notes").insert, {
            "project_id": project["id"], "text": text, "sources": [s.model_dump(mode="json") for s in sources],
        })
        await asyncio.to_thread(self.tables("projects").update, project["id"], {})  # newest first in the panel
        action_id = None
        if ledger is not None:
            undo = {"op": "row.unadd", "table": "project_notes", "id": note["id"],
                    "after": {"deleted_at": None, "text": note["text"]}}
            action = await asyncio.to_thread(
                ledger.record, "project_save", "done", f"Saved a note to “{project['name']}”",
                target_kind="project_notes", target_id=note["id"], undo=undo, key=key,
            )
            action_id = action["id"]
        try:
            # Short: the voice turn waits. Without an embedding, words still find it.
            await self._index("project_note", project["id"], note["id"], passages([(None, text)]), timeout=1.5)
        except Exception as exc:
            log.warning("note not indexed", extra={"event": type(exc).__name__})
        return project, note, action_id
