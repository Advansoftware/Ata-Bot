"""Servidor HTTP local mínimo para tocar os áudios das reuniões no player da UI.

A janela do app carrega a interface via file://; um elemento <audio> apontando
para um WAV grande via data-URI seria inviável (reuniões longas = dezenas de MB
em base64). Então servimos os arquivos por HTTP em 127.0.0.1, com suporte a
requisições Range — o que permite arrastar/buscar no player.

Segurança: escuta só em localhost, resolve o arquivo pela pasta REAL da reunião
(via storage) e recusa qualquer nome com separador de caminho ou `..`.
"""
from __future__ import annotations

import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from core import storage

_URL_RE = re.compile(r"^/audio/([A-Za-z0-9]+)/(.+)$")
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")

_server: ThreadingHTTPServer | None = None
_port: int | None = None
_lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silencia o log padrão no stderr
        pass

    def do_GET(self):  # noqa: N802
        m = _URL_RE.match(self.path)
        if not m:
            self.send_error(404)
            return
        meeting_id, filename = m.group(1), unquote(m.group(2))
        if "/" in filename or "\\" in filename or ".." in filename:
            self.send_error(403)
            return
        meeting = storage.get_meeting(meeting_id)
        if meeting is None:
            self.send_error(404)
            return
        base = Path(meeting.dir_path).resolve()
        path = (base / filename).resolve()
        try:
            path.relative_to(base)  # impede escapar da pasta da reunião
        except ValueError:
            self.send_error(403)
            return
        if not path.exists() or path.suffix.lower() != ".wav":
            self.send_error(404)
            return
        self._serve_file(path)

    def _serve_file(self, path: Path) -> None:
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            rm = _RANGE_RE.match(rng)
            if rm:
                if rm.group(1):
                    start = int(rm.group(1))
                if rm.group(2):
                    end = min(int(rm.group(2)), size - 1)
                if start > end or start >= size:
                    self.send_error(416)
                    return
                status = 206
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    do_HEAD = do_GET  # noqa: N815


def ensure_server() -> int:
    """Sobe o servidor (uma vez) e devolve a porta em 127.0.0.1."""
    global _server, _port
    with _lock:
        if _server is None:
            _server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            _port = _server.server_address[1]
            threading.Thread(target=_server.serve_forever, daemon=True).start()
        return int(_port)  # type: ignore[arg-type]
