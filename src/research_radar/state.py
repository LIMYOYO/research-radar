"""SQLite persistence for project snapshots and later radar runs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .project import ProjectSnapshot


SCHEMA_VERSION = 3


class ProfileChangePending(ValueError):
    """Raised when the normalized research profile changed without approval."""


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    project_root TEXT PRIMARY KEY,
    project_name TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    profile_source TEXT NOT NULL,
    profile_json TEXT NOT NULL,
    manuscript_text TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_files (
    project_root TEXT NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    PRIMARY KEY (project_root, path),
    FOREIGN KEY (project_root) REFERENCES projects(project_root) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS seed_papers (
    project_root TEXT NOT NULL,
    identity TEXT NOT NULL,
    citation_key TEXT NOT NULL,
    title TEXT,
    authors_json TEXT NOT NULL,
    year INTEGER,
    venue TEXT,
    doi TEXT,
    preprint_id TEXT,
    url TEXT,
    entry_type TEXT,
    source_file TEXT NOT NULL,
    cited_in_manuscript INTEGER NOT NULL,
    PRIMARY KEY (project_root, citation_key),
    FOREIGN KEY (project_root) REFERENCES projects(project_root) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS seed_papers_identity_idx
    ON seed_papers(project_root, identity);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_root TEXT NOT NULL,
    run_type TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    FOREIGN KEY (project_root) REFERENCES projects(project_root) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS candidates (
    project_root TEXT NOT NULL,
    identity TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (project_root, identity),
    FOREIGN KEY (project_root) REFERENCES projects(project_root) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS feedback (
    project_root TEXT NOT NULL,
    identity TEXT NOT NULL,
    label TEXT NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (project_root, identity, created_at),
    FOREIGN KEY (project_root) REFERENCES projects(project_root) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS distillations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_root TEXT NOT NULL,
    identity TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (project_root) REFERENCES projects(project_root) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS distillations_latest_idx
    ON distillations(project_root, identity, id DESC);
"""


def state_path(project: str | Path) -> Path:
    return Path(project).expanduser().resolve() / ".research-radar" / "state.sqlite"


def connect(project: str | Path) -> sqlite3.Connection:
    path = state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    seed_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(seed_papers)")
    }
    if "preprint_id" not in seed_columns:
        connection.execute("ALTER TABLE seed_papers ADD COLUMN preprint_id TEXT")
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    return connection


def save_snapshot(
    snapshot: ProjectSnapshot,
    *,
    approve_profile_change: bool = False,
) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    root = snapshot.project_root
    path = state_path(root)
    with connect(root) as connection:
        previous = connection.execute(
            "SELECT profile_json FROM projects WHERE project_root = ?", (root,)
        ).fetchone()
        new_profile_json = json.dumps(
            asdict(snapshot.profile), ensure_ascii=False, sort_keys=True
        )
        if (
            previous
            and previous["profile_json"] != new_profile_json
            and not approve_profile_change
        ):
            raise ProfileChangePending(
                "The research profile changed since the last approved snapshot. "
                "Review it, then run `research-radar profile --approve-change --project ...`."
            )
        connection.execute(
            """
            INSERT INTO projects(
                project_root, project_name, fingerprint, profile_source,
                profile_json, manuscript_text, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_root) DO UPDATE SET
                project_name=excluded.project_name,
                fingerprint=excluded.fingerprint,
                profile_source=excluded.profile_source,
                profile_json=excluded.profile_json,
                manuscript_text=excluded.manuscript_text,
                updated_at=excluded.updated_at
            """,
            (
                root,
                snapshot.profile.project_name,
                snapshot.fingerprint,
                snapshot.profile.source_file,
                new_profile_json,
                snapshot.manuscript_text,
                now,
            ),
        )
        connection.execute("DELETE FROM source_files WHERE project_root = ?", (root,))
        connection.executemany(
            """
            INSERT INTO source_files(project_root, path, kind, sha256, size_bytes)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (root, item.path, item.kind, item.sha256, item.size_bytes)
                for item in snapshot.source_files
            ],
        )
        connection.execute("DELETE FROM seed_papers WHERE project_root = ?", (root,))
        connection.executemany(
            """
            INSERT INTO seed_papers(
                project_root, identity, citation_key, title, authors_json, year,
                venue, doi, preprint_id, url, entry_type, source_file, cited_in_manuscript
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    root,
                    seed.identity,
                    seed.citation_key,
                    seed.title,
                    json.dumps(seed.authors, ensure_ascii=False),
                    seed.year,
                    seed.venue,
                    seed.doi,
                    seed.preprint_id,
                    seed.url,
                    seed.entry_type,
                    seed.source_file,
                    int(seed.cited_in_manuscript),
                )
                for seed in snapshot.seeds
            ],
        )
    return path


def state_counts(project: str | Path) -> dict[str, int]:
    with connect(project) as connection:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "projects",
                "source_files",
                "seed_papers",
                "runs",
                "candidates",
                "feedback",
                "distillations",
            )
        }


def save_discovery(
    project: str | Path,
    *,
    candidates: list[dict[str, object]],
    manifest: dict[str, object],
    status: str,
) -> tuple[int, int]:
    """Persist a discovery run and return (run_id, newly_seen_count)."""
    root = str(Path(project).expanduser().resolve())
    now = datetime.now(timezone.utc).isoformat()
    new_count = 0
    with connect(root) as connection:
        project_exists = connection.execute(
            "SELECT 1 FROM projects WHERE project_root = ?", (root,)
        ).fetchone()
        if not project_exists:
            raise ValueError("Project snapshot is missing; run `research-radar profile` first.")
        cursor = connection.execute(
            """
            INSERT INTO runs(project_root, run_type, started_at, completed_at, status, manifest_json)
            VALUES (?, 'discovery', ?, ?, ?, ?)
            """,
            (root, now, now, status, json.dumps(manifest, ensure_ascii=False, sort_keys=True)),
        )
        run_id = int(cursor.lastrowid)
        for candidate in candidates:
            identity = str(candidate["identity"])
            exists = connection.execute(
                "SELECT 1 FROM candidates WHERE project_root = ? AND identity = ?",
                (root, identity),
            ).fetchone()
            if not exists:
                new_count += 1
            connection.execute(
                """
                INSERT INTO candidates(project_root, identity, payload_json, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(project_root, identity) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    root,
                    identity,
                    json.dumps(candidate, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                ),
            )
    return run_id, new_count


def load_candidates(project: str | Path) -> list[dict[str, object]]:
    root = str(Path(project).expanduser().resolve())
    with connect(root) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM candidates WHERE project_root = ? ORDER BY last_seen_at DESC",
            (root,),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def load_candidate_records(
    project: str | Path,
    *,
    first_seen_since: str | None = None,
) -> list[dict[str, object]]:
    root = str(Path(project).expanduser().resolve())
    query = (
        "SELECT payload_json, first_seen_at, last_seen_at FROM candidates "
        "WHERE project_root = ?"
    )
    parameters: list[object] = [root]
    if first_seen_since:
        query += " AND first_seen_at >= ?"
        parameters.append(first_seen_since)
    query += " ORDER BY first_seen_at DESC, identity"
    with connect(root) as connection:
        rows = connection.execute(query, parameters).fetchall()
    return [
        {
            "candidate": json.loads(row["payload_json"]),
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
        }
        for row in rows
    ]


FEEDBACK_LABELS = {
    "read-now",
    "cite",
    "watch",
    "known",
    "off-topic",
    "weak",
    "duplicate",
}


def save_feedback(
    project: str | Path,
    *,
    identity: str,
    label: str,
    note: str | None = None,
) -> None:
    if label not in FEEDBACK_LABELS:
        raise ValueError(
            f"Unknown feedback label {label!r}; choose one of: {', '.join(sorted(FEEDBACK_LABELS))}"
        )
    root = str(Path(project).expanduser().resolve())
    now = datetime.now(timezone.utc).isoformat()
    with connect(root) as connection:
        exists = connection.execute(
            "SELECT 1 FROM candidates WHERE project_root = ? AND identity = ?",
            (root, identity),
        ).fetchone()
        if not exists:
            raise ValueError(f"Unknown candidate identity for this project: {identity}")
        connection.execute(
            "INSERT INTO feedback(project_root, identity, label, note, created_at) VALUES (?, ?, ?, ?, ?)",
            (root, identity, label, note, now),
        )


def latest_feedback(project: str | Path) -> dict[str, dict[str, object]]:
    root = str(Path(project).expanduser().resolve())
    with connect(root) as connection:
        rows = connection.execute(
            """
            SELECT identity, label, note, created_at
            FROM feedback
            WHERE project_root = ?
            ORDER BY created_at ASC
            """,
            (root,),
        ).fetchall()
    return {
        str(row["identity"]): {
            "label": row["label"],
            "note": row["note"],
            "created_at": row["created_at"],
        }
        for row in rows
    }


def save_distillation(
    project: str | Path,
    *,
    identity: str,
    payload: dict[str, object],
) -> int:
    """Append one validated distillation and return its immutable row id."""
    root = str(Path(project).expanduser().resolve())
    now = datetime.now(timezone.utc).isoformat()
    with connect(root) as connection:
        candidate = connection.execute(
            "SELECT 1 FROM candidates WHERE project_root = ? AND identity = ?",
            (root, identity),
        ).fetchone()
        if not candidate:
            raise ValueError(f"Unknown candidate identity for this project: {identity}")
        cursor = connection.execute(
            """
            INSERT INTO distillations(project_root, identity, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (root, identity, json.dumps(payload, ensure_ascii=False, sort_keys=True), now),
        )
        return int(cursor.lastrowid)


def latest_distillations(project: str | Path) -> dict[str, dict[str, object]]:
    root = str(Path(project).expanduser().resolve())
    with connect(root) as connection:
        rows = connection.execute(
            """
            SELECT identity, payload_json, created_at
            FROM distillations
            WHERE project_root = ?
            ORDER BY id ASC
            """,
            (root,),
        ).fetchall()
    return {
        str(row["identity"]): {
            **json.loads(row["payload_json"]),
            "stored_at": row["created_at"],
        }
        for row in rows
    }


def last_successful_search_to(project: str | Path) -> str | None:
    root = str(Path(project).expanduser().resolve())
    with connect(root) as connection:
        rows = connection.execute(
            """
            SELECT manifest_json
            FROM runs
            WHERE project_root = ? AND run_type = 'discovery' AND status = 'success'
            ORDER BY id DESC
            """,
            (root,),
        ).fetchall()
    for row in rows:
        try:
            manifest = json.loads(row["manifest_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        value = manifest.get("search_to")
        if isinstance(value, str) and value:
            return value
    return None
