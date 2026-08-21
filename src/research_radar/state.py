"""SQLite persistence for project snapshots and later radar runs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .project import ProjectSnapshot


SCHEMA_VERSION = 1


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
"""


def state_path(project: str | Path) -> Path:
    return Path(project).expanduser().resolve() / ".research-radar" / "state.sqlite"


def connect(project: str | Path) -> sqlite3.Connection:
    path = state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    return connection


def save_snapshot(snapshot: ProjectSnapshot) -> Path:
    now = datetime.now(timezone.utc).isoformat()
    root = snapshot.project_root
    path = state_path(root)
    with connect(root) as connection:
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
                json.dumps(asdict(snapshot.profile), ensure_ascii=False, sort_keys=True),
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
                venue, doi, url, entry_type, source_file, cited_in_manuscript
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            for table in ("projects", "source_files", "seed_papers", "runs", "candidates", "feedback")
        }
