"""Local SQLite storage: numbered migrations and the per-user Repo."""

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path

from .repo import Conflict, Gte, In, IsNull, Lte, Row, Table, Where, check_columns, now, parse_order


class SqliteDatabase:
    """One SQLite file. Migrations run once each, in order (PRAGMA user_version)."""

    _lock = threading.Lock()

    def __init__(self, path: str | Path, migrations: list[str]) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            for number, script in enumerate(migrations[version:], start=version + 1):
                db.executescript(script)
                # PRAGMA takes no parameters; number is an int we computed.
                db.execute(f"PRAGMA user_version = {int(number)}")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete = ON")
        try:
            with db:
                yield db
        finally:
            db.close()


class SqliteRepo:
    def __init__(self, database: SqliteDatabase, table: Table, user_id: str | None) -> None:
        self.database = database
        self.table = table
        self.user_id = user_id

    # Rows

    def _encode(self, row: Row) -> Row:
        return {k: json.dumps(v) if k in self.table.json_columns and v is not None else v for k, v in row.items()}

    def _decode(self, row: sqlite3.Row) -> Row:
        data = dict(row)
        for name in self.table.json_columns & data.keys():
            if data[name] is not None:
                data[name] = json.loads(data[name])
        return data

    def _scope(self, where: Where | None) -> tuple[str, list]:
        """WHERE text and its parameters, always limited to this repo's user."""
        where = dict(where or {})
        check_columns(self.table, where)
        if self.user_id is not None:
            where["user_id"] = self.user_id
        clauses, params = [], []
        for name, value in where.items():
            if isinstance(value, In):
                clauses.append(f"{name} IN ({','.join('?' * len(value.values))})" if value.values else "0")
                params.extend(self._encode({name: v})[name] for v in value.values)
            elif isinstance(value, Gte):
                clauses.append(f"{name} >= ?")
                params.append(value.value)
            elif isinstance(value, Lte):
                clauses.append(f"{name} <= ?")
                params.append(value.value)
            elif isinstance(value, IsNull):
                clauses.append(f"{name} IS {'' if value.null else 'NOT '}NULL")
            else:
                clauses.append(f"{name} = ?")
                params.append(self._encode({name: value})[name])
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    # Repo interface

    def insert(self, row: Row) -> Row:
        row = dict(row)
        check_columns(self.table, row)
        row.setdefault("id", uuid.uuid4().hex)
        if self.user_id is not None:
            row["user_id"] = self.user_id
        elif "user_id" not in row:
            raise ValueError("an unscoped insert must name the user")
        if self.table.timestamps:
            row.setdefault("created_at", now())
            row.setdefault("updated_at", row["created_at"])
        encoded = self._encode(row)
        names = ", ".join(encoded)
        with self.database.connect() as db:
            db.execute(
                f"INSERT INTO {self.table.name} ({names}) VALUES ({','.join('?' * len(encoded))})",
                list(encoded.values()),
            )
        return row

    def get(self, identifier: str) -> Row | None:
        rows = self.select({"id": identifier}, limit=1)
        return rows[0] if rows else None

    def select(self, where: Where | None = None, order: str | None = None, limit: int | None = None) -> list[Row]:
        clause, params = self._scope(where)
        sql = f"SELECT * FROM {self.table.name}{clause}"
        ordering = parse_order(self.table, order)
        if ordering:
            sql += " ORDER BY " + ", ".join(f"{name} {'DESC' if desc else 'ASC'}" for name, desc in ordering)
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self.database.connect() as db:
            return [self._decode(row) for row in db.execute(sql, params).fetchall()]

    def update(self, identifier: str, changes: Row, expect_updated_at: str | None = None) -> Row | None:
        changes = {k: v for k, v in changes.items() if k not in ("id", "user_id", "created_at")}
        check_columns(self.table, changes)
        if self.table.timestamps:
            changes["updated_at"] = now()
        where: Where = {"id": identifier}
        if expect_updated_at is not None:
            where["updated_at"] = expect_updated_at
        clause, params = self._scope(where)
        encoded = self._encode(changes)
        if encoded:
            with self.database.connect() as db:
                cursor = db.execute(
                    f"UPDATE {self.table.name} SET {', '.join(f'{k} = ?' for k in encoded)}{clause}",
                    [*encoded.values(), *params],
                )
            if cursor.rowcount == 0 and expect_updated_at is not None and self.get(identifier) is not None:
                raise Conflict(identifier)
        return self.get(identifier)

    def delete(self, identifier: str, where: Where | None = None) -> bool:
        clause, params = self._scope({**(where or {}), "id": identifier})
        with self.database.connect() as db:
            return db.execute(f"DELETE FROM {self.table.name}{clause}", params).rowcount == 1
