"""Persistência das reuniões: SQLite (metadados) + arquivos em disco.

Estruturado para o painel da fase 2 reaproveitar: liste reuniões pela tabela,
reprocesse a ata a partir do transcript.txt salvo, etc.

Layout em disco:
    data/
      meetings.db
      meetings/<meeting_id>/
        <speaker>.wav        (faixas por participante, cru)
        transcript.txt       (transcrição com falantes)
        minutes.md           (ata final)
"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from core.config import ROOT

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "meetings.db"


@dataclass
class Meeting:
    id: str
    guild_id: int
    channel_id: int
    started_at: str
    ended_at: str | None
    status: str  # recording | processing | done | error
    dir_path: str  # pasta onde esta reunião foi salva (fixada na criação)
    transcript_path: str | None
    minutes_path: str | None

    @property
    def dir(self) -> Path:
        return Path(self.dir_path)


def _connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL,
                dir_path TEXT,
                transcript_path TEXT,
                minutes_path TEXT
            )
            """
        )
        # Migração para bancos antigos (sem a coluna dir_path).
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(meetings)")}
        if "dir_path" not in cols:
            conn.execute("ALTER TABLE meetings ADD COLUMN dir_path TEXT")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_meeting(guild_id: int, channel_id: int) -> Meeting:
    # Import local para evitar dependência circular no topo do módulo.
    from core.config import Config

    meeting_id = uuid.uuid4().hex[:12]
    base_dir = Config.load().resolved_output_dir()
    meeting_dir = base_dir / meeting_id

    meeting = Meeting(
        id=meeting_id,
        guild_id=guild_id,
        channel_id=channel_id,
        started_at=_now(),
        ended_at=None,
        status="recording",
        dir_path=str(meeting_dir),
        transcript_path=None,
        minutes_path=None,
    )
    meeting_dir.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO meetings (id, guild_id, channel_id, started_at, "
            "ended_at, status, dir_path, transcript_path, minutes_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                meeting.id,
                meeting.guild_id,
                meeting.channel_id,
                meeting.started_at,
                None,
                meeting.status,
                meeting.dir_path,
                None,
                None,
            ),
        )
    return meeting


def update_meeting(
    meeting_id: str,
    *,
    status: str | None = None,
    ended_at: bool = False,
    transcript_path: str | None = None,
    minutes_path: str | None = None,
) -> None:
    sets, params = [], []
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if ended_at:
        sets.append("ended_at = ?")
        params.append(_now())
    if transcript_path is not None:
        sets.append("transcript_path = ?")
        params.append(transcript_path)
    if minutes_path is not None:
        sets.append("minutes_path = ?")
        params.append(minutes_path)
    if not sets:
        return
    params.append(meeting_id)
    with _connect() as conn:
        conn.execute(f"UPDATE meetings SET {', '.join(sets)} WHERE id = ?", params)


def get_meeting(meeting_id: str) -> Meeting | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
    return _row_to_meeting(row) if row else None


def list_meetings(limit: int = 50) -> list[Meeting]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM meetings ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_row_to_meeting(r) for r in rows]


def add_imported_meeting(
    *,
    id: str,
    guild_id: int,
    channel_id: int,
    started_at: str,
    ended_at: str | None,
    status: str,
    dir_path: str,
    transcript_path: str | None,
    minutes_path: str | None,
) -> None:
    """Insere (ou substitui) uma reunião vinda de um pacote importado."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meetings (id, guild_id, channel_id, started_at, "
            "ended_at, status, dir_path, transcript_path, minutes_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (id, guild_id, channel_id, started_at, ended_at, status,
             dir_path, transcript_path, minutes_path),
        )


def delete_meeting(meeting_id: str) -> bool:
    """Remove a reunião do índice e apaga a pasta em disco. True se existia."""
    import shutil

    meeting = get_meeting(meeting_id)
    if meeting is None:
        return False
    with _connect() as conn:
        conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
    # Só apaga a pasta se ela realmente for a desta reunião (evita acidentes).
    d = meeting.dir
    if d.exists() and d.name == meeting_id:
        shutil.rmtree(d, ignore_errors=True)
    return True


def _row_to_meeting(row: sqlite3.Row) -> Meeting:
    dir_path = row["dir_path"] or str(DATA_DIR / "meetings" / row["id"])
    return Meeting(
        id=row["id"],
        guild_id=row["guild_id"],
        channel_id=row["channel_id"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        status=row["status"],
        dir_path=dir_path,
        transcript_path=row["transcript_path"],
        minutes_path=row["minutes_path"],
    )
