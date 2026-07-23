"""Modelos do Whisper: download local com progresso e checagem de estado.

Guardamos cada modelo em data/models/<nome>/ (um diretório por modelo, com
model.bin + arquivos de config). Assim conseguimos:
  - saber se um modelo já foi baixado (mostrar "baixado" na interface);
  - baixar com barra de progresso real (huggingface_hub + um tqdm próprio);
  - carregar o Whisper apontando direto para a pasta (offline depois do 1º download).
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

from core.config import DATA_DIR

MODELS_DIR = DATA_DIR / "models"

# nome do modelo -> (repositório no HuggingFace, tamanho aproximado em MB)
WHISPER_MODELS: dict[str, tuple[str, int]] = {
    "tiny": ("Systran/faster-whisper-tiny", 75),
    "base": ("Systran/faster-whisper-base", 145),
    "small": ("Systran/faster-whisper-small", 484),
    "medium": ("Systran/faster-whisper-medium", 1530),
    "large-v3": ("Systran/faster-whisper-large-v3", 3090),
}

# Callback de progresso: (fracao 0..1, bytes_baixados, bytes_totais).
ProgressCB = Callable[[float, int, int], None]


def model_dir(name: str) -> Path:
    return MODELS_DIR / name


def is_downloaded(name: str) -> bool:
    """True se o modelo já está baixado localmente (tem o model.bin)."""
    d = model_dir(name)
    return d.is_dir() and (d / "model.bin").exists()


class _NullWriter:
    """Descarta a saída do tqdm (não queremos barras poluindo o console/GUI)."""

    def write(self, *_a, **_k) -> None:  # noqa: D401
        pass

    def flush(self, *_a, **_k) -> None:
        pass


class _Aggregator:
    """Agrega o progresso de várias barras de bytes num único percentual.

    O huggingface_hub reporta bytes via tqdm, mas o COMO varia por versão/backend:
      - backend clássico: uma barra por arquivo (total fixo no construtor);
      - backend Xet (hf >= 1.x): barras persistentes cujo `total` só é definido
        DEPOIS da construção (começa em 0 e cresce), além de uma barra
        "Reconstructing" que duplicaria a contagem.
    Por isso não somamos no construtor: registramos as barras e lemos `.n`/`.total`
    ao vivo (polling), ignorando a barra de reconstrução para não contar em dobro.
    """

    def __init__(self, cb: Optional[ProgressCB]):
        self.cb = cb
        self._bars: list = []
        self._lock = threading.Lock()

    def register(self, bar) -> None:
        with self._lock:
            self._bars.append(bar)

    def snapshot(self) -> tuple[int, int]:
        with self._lock:
            bars = list(self._bars)
        done = total = 0
        for b in bars:
            t = int(getattr(b, "total", 0) or 0)
            if t <= 0:
                continue
            n = int(getattr(b, "n", 0) or 0)
            total += t
            done += min(n, t)
        return done, total

    def emit(self) -> None:
        if self.cb is None:
            return
        done, total = self.snapshot()
        frac = (done / total) if total else 0.0
        self.cb(min(1.0, frac), done, total)


def _tqdm_class(agg: "_Aggregator"):
    """tqdm silencioso que se registra no agregador para termos `.n`/`.total` ao vivo.

    Não usamos disable=True: uma barra desabilitada não atualiza `.n`, e é `.n` que
    precisamos ler no polling. Em vez disso mandamos a saída para o vão (NullWriter).
    Contamos só barras de bytes (unit="B") e ignoramos a de reconstrução do Xet.
    """
    from tqdm import tqdm as _tqdm

    class _T(_tqdm):
        def __init__(self, *a, **k):
            unit = k.get("unit", "")
            desc = str(k.get("desc") or "")
            k["file"] = _NullWriter()  # nada no console
            k["disable"] = False       # precisamos que .n/.total atualizem
            k["mininterval"] = 0
            super().__init__(*a, **k)
            is_bytes = unit == "B" and "reconstruct" not in desc.lower()
            if is_bytes:
                agg.register(self)

    return _T


_dl_lock = threading.Lock()


def download(name: str, on_progress: Optional[ProgressCB] = None) -> Path:
    """Baixa o modelo para data/models/<name>/, reportando progresso. Retorna a pasta."""
    if name not in WHISPER_MODELS:
        raise ValueError(f"Modelo desconhecido: {name}")
    repo, _ = WHISPER_MODELS[name]
    dest = model_dir(name)
    dest.mkdir(parents=True, exist_ok=True)

    from huggingface_hub import snapshot_download

    agg = _Aggregator(on_progress)

    # Thread de polling: lê o progresso das barras ao vivo (o total do Xet só
    # aparece depois da construção, então não dá para reportar só no update()).
    stop = threading.Event()

    def _poll() -> None:
        while not stop.wait(0.2):
            agg.emit()

    poller = threading.Thread(target=_poll, daemon=True)
    if on_progress is not None:
        poller.start()

    try:
        with _dl_lock:  # um download por vez
            snapshot_download(
                repo_id=repo,
                local_dir=str(dest),
                tqdm_class=_tqdm_class(agg),
            )
    finally:
        stop.set()
        if on_progress is not None:
            poller.join(timeout=1)

    if on_progress is not None:
        done, total = agg.snapshot()
        on_progress(1.0, done, total or done)
    return dest


def ensure(name: str) -> str:
    """Garante que o modelo exista localmente (baixa em silêncio se faltar).

    Retorna o caminho para carregar no WhisperModel. Para nomes fora da lista
    (id custom do HF ou caminho), devolve o próprio nome.
    """
    if name not in WHISPER_MODELS:
        return name
    if not is_downloaded(name):
        download(name)
    return str(model_dir(name))
