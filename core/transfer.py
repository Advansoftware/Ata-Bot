"""Import/export de reuniões como pacote portável (.atabot = zip).

Um pacote contém TUDO que foi gerado de cada reunião — áudio por participante,
transcrição, ata e o índice RAG — mais os metadados. Assim dá para exportar uma
(ou todas) as reuniões e importar noutra instalação do Ata Bot, em outro PC.

Estrutura do zip:
    manifest.json                 {format, version, meetings: [{id, guild_id, ...}]}
    meetings/<id>/<arquivos...>    (Bruno.wav, transcript.txt, minutes.md, rag_*.*)
"""
from __future__ import annotations

import json
import shutil
import uuid
import zipfile
from pathlib import Path

from core import storage
from core.config import Config

FORMAT = "atabot-bundle"
VERSION = 1


def bundle(meetings: list, out_path: str) -> int:
    """Escreve um pacote com as reuniões dadas. Devolve quantas entraram."""
    out = Path(out_path)
    manifest = {"format": FORMAT, "version": VERSION, "meetings": []}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for m in meetings:
            d = Path(m.dir_path)
            if not d.exists():
                continue
            manifest["meetings"].append(
                {
                    "id": m.id,
                    "guild_id": m.guild_id,
                    "channel_id": m.channel_id,
                    "started_at": m.started_at,
                    "ended_at": m.ended_at,
                    "status": m.status,
                }
            )
            for f in sorted(d.iterdir()):
                if f.is_file() and f.name != "progress.json":
                    z.write(f, f"meetings/{m.id}/{f.name}")
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return len(manifest["meetings"])


def unbundle(zip_path: str) -> list[str]:
    """Importa um pacote. Devolve os ids das reuniões importadas.

    Se o id já existir, cria um id novo (não sobrescreve o que já está aqui).
    """
    base = Config.load().resolved_output_dir()
    base.mkdir(parents=True, exist_ok=True)
    imported: list[str] = []

    with zipfile.ZipFile(zip_path) as z:
        try:
            manifest = json.loads(z.read("manifest.json"))
        except KeyError as e:
            raise ValueError("Pacote inválido: manifest.json ausente.") from e
        if manifest.get("format") != FORMAT:
            raise ValueError("Este arquivo não é um pacote do Ata Bot.")

        names = z.namelist()
        for meta in manifest.get("meetings", []):
            old_id = str(meta.get("id", "")).strip()
            if not old_id:
                continue
            new_id = old_id if storage.get_meeting(old_id) is None else uuid.uuid4().hex[:12]
            dest = base / new_id
            dest.mkdir(parents=True, exist_ok=True)

            prefix = f"meetings/{old_id}/"
            for name in names:
                if not name.startswith(prefix) or name.endswith("/"):
                    continue
                fname = name[len(prefix):]
                if not fname or "/" in fname or "\\" in fname or ".." in fname:
                    continue  # evita path traversal
                with z.open(name) as src, open(dest / fname, "wb") as dst:
                    shutil.copyfileobj(src, dst)

            tr = dest / "transcript.txt"
            mn = dest / "minutes.md"
            storage.add_imported_meeting(
                id=new_id,
                guild_id=int(meta.get("guild_id", 0) or 0),
                channel_id=int(meta.get("channel_id", 0) or 0),
                started_at=meta.get("started_at", ""),
                ended_at=meta.get("ended_at"),
                status=meta.get("status", "done"),
                dir_path=str(dest),
                transcript_path=str(tr) if tr.exists() else None,
                minutes_path=str(mn) if mn.exists() else None,
            )
            imported.append(new_id)
    return imported
