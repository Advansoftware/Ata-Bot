"""Configuração do app, armazenada em data/settings.json.

Tudo que o usuário configura (token do Discord, provedor da ata, chaves de API,
modelo, idioma) vive aqui e é editado pela página web local (bot/webconfig.py).
Nada de .env nem de editar arquivos à mão. O painel da fase 2 edita o mesmo JSON.

O arquivo fica em data/ (gitignored), então as chaves não vão para o repositório.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _default_data_dir() -> Path:
    """Onde ficam settings.json, modelos e reuniões.

    Em dev: pasta data/ do projeto. Empacotado (PyInstaller/.app/.exe): uma pasta
    do usuário, gravável — o interior do bundle é somente-leitura.
    """
    if getattr(sys, "frozen", False):
        if sys.platform == "win32":
            return Path(os.environ.get("APPDATA", Path.home())) / "AtaBot"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "AtaBot"
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return Path(base) / "ata-bot"
    return ROOT / "data"


DATA_DIR = _default_data_dir()
SETTINGS_PATH = DATA_DIR / "settings.json"

_LOCK = threading.Lock()

# Provedores de ata suportados e suas chaves de ambiente/campos obrigatórios.
PROVIDERS = ("claude", "openai", "gemini", "ollama")

DEFAULTS = {
    "discord_token": "",
    "language": "pt",
    # Postar a ata (e o progresso) no canal do Discord ao terminar. Quando False,
    # o bot só salva o arquivo e mostra tudo no Log do app (útil para testes).
    "post_to_discord": True,
    # Pasta onde as reuniões são salvas. Vazio = data/meetings (dentro do projeto).
    "output_dir": "",
    # URL de webhook para enviar a ata ao terminar/compartilhar (Slack/Discord/Zapier).
    "webhook_url": "",
    # Índice do microfone para o teste rápido (None = dispositivo padrão do SO).
    "mic_device": None,
    "transcription": {"model": "small", "device": "cpu", "compute_type": "int8"},
    "minutes": {
        "provider": "claude",
        "claude": {"model": "claude-opus-4-8", "api_key": ""},
        "openai": {"model": "gpt-4o-mini", "api_key": ""},
        "gemini": {"model": "gemini-2.0-flash", "api_key": ""},
        "ollama": {"model": "llama3.1:8b", "host": "http://localhost:11434"},
    },
}


@dataclass
class TranscriptionConfig:
    model: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"


@dataclass
class MinutesConfig:
    provider: str = "claude"
    providers: dict = field(default_factory=dict)

    def options(self) -> dict:
        return dict(self.providers.get(self.provider, {}))


@dataclass
class Config:
    discord_token: str
    language: str
    output_dir: str
    transcription: TranscriptionConfig
    minutes: MinutesConfig
    post_to_discord: bool = True

    def resolved_output_dir(self) -> Path:
        """Pasta base das reuniões: a configurada, ou data/meetings por padrão."""
        if self.output_dir.strip():
            return Path(self.output_dir).expanduser()
        return DATA_DIR / "meetings"

    # --- Estado de configuração (usado pela página web e pelo launcher) ---

    def is_configured(self) -> bool:
        """Pronto para iniciar o bot? (token presente + provedor da ata utilizável)."""
        return bool(self.discord_token.strip()) and self.provider_ready()

    def provider_ready(self) -> bool:
        opts = self.minutes.options()
        if self.minutes.provider == "ollama":
            return True  # não precisa de chave
        return bool(opts.get("api_key", "").strip())

    # --- Carga / gravação ---

    @classmethod
    def load(cls) -> "Config":
        raw = _read_raw()
        mn = raw["minutes"]
        providers = {p: dict(mn.get(p, {})) for p in PROVIDERS}
        return cls(
            discord_token=raw.get("discord_token", ""),
            language=raw.get("language", "pt"),
            output_dir=raw.get("output_dir", ""),
            transcription=TranscriptionConfig(**raw.get("transcription", {})),
            minutes=MinutesConfig(provider=mn.get("provider", "claude"), providers=providers),
            post_to_discord=bool(raw.get("post_to_discord", True)),
        )


def _read_raw() -> dict:
    """Lê settings.json, criando com defaults na primeira vez."""
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not SETTINGS_PATH.exists():
            SETTINGS_PATH.write_text(
                json.dumps(DEFAULTS, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return json.loads(json.dumps(DEFAULTS))
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return _merge_defaults(data)


def _merge_defaults(data: dict) -> dict:
    """Garante que todas as chaves esperadas existam (para settings.json antigos)."""
    out = json.loads(json.dumps(DEFAULTS))
    out["discord_token"] = data.get("discord_token", "")
    out["language"] = data.get("language", "pt")
    out["post_to_discord"] = bool(data.get("post_to_discord", True))
    out["output_dir"] = data.get("output_dir", "")
    out["webhook_url"] = data.get("webhook_url", "")
    out["mic_device"] = data.get("mic_device", None)
    out["transcription"].update(data.get("transcription", {}))
    mn = data.get("minutes", {})
    out["minutes"]["provider"] = mn.get("provider", "claude")
    for p in PROVIDERS:
        out["minutes"][p].update(mn.get(p, {}))
    return out


def save_raw(new: dict) -> None:
    """Grava o dicionário completo de settings (usado pela página web)."""
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(
            json.dumps(new, indent=2, ensure_ascii=False), encoding="utf-8"
        )


def read_raw() -> dict:
    """Exposto para a página web (leitura do JSON já com defaults mesclados)."""
    return _read_raw()
