import sqlite3
from pathlib import Path

from qualitybridge.models import RunResult


class HistoryStore:
    def __init__(self, path: Path):
        self.path = path

    def save(self, result: RunResult) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, started_at TEXT NOT NULL,
                payload TEXT NOT NULL)""")
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?)",
                (
                    result.id,
                    result.project,
                    result.started_at.isoformat(),
                    result.model_dump_json(),
                ),
            )

    def recent(self, project: str, limit: int = 10) -> list[RunResult]:
        if not self.path.exists():
            return []
        with sqlite3.connect(self.path, timeout=10) as connection:
            rows = connection.execute(
                "SELECT payload FROM runs WHERE project = ? ORDER BY started_at DESC LIMIT ?",
                (project, limit),
            ).fetchall()
        return [RunResult.model_validate_json(row[0]) for row in rows]
