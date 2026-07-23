"""Sink de gravação compatível com o sistema de recepção de voz da py-cord 2.8.x.

Por que este arquivo existe: na 2.8.0 os sinks embutidos (WaveSink etc.) estão
quebrados. O roteador novo (`voice/receive`) exige o atributo `__sink_listeners__`
e entrega o áudio chamando `sink.write(VoiceData, source)` — mas os sinks antigos
não têm esse atributo e o `write` deles espera *bytes*, não um `VoiceData`. Este sink
implementa o contrato novo: acumula o PCM já decodificado (`VoiceData.pcm`) por usuário
e salva um `.wav` por pessoa.
"""
from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Callable

from discord.opus import OPUS_SILENCE, PacketDecoder
from discord.sinks.core import Sink
from discord.voice.receive.reader import PacketDecryptor

_log = logging.getLogger(__name__)


# --- Patch DAVE: decriptar o E2EE corretamente na recepção ---------------------
# A recepção de voz da py-cord 2.8.0 entrega áudio como lixo quando a call usa
# DAVE (E2EE) — bug #3139. Investigando os bytes crus na marra, achei DOIS
# defeitos em `PacketDecryptor.decrypt_rtp`:
#   1. Ele só chama `dave.decrypt` quando `ssrc_user_map[ssrc]` já existe, mas
#      esse mapa (quem-fala -> ssrc) chega atrasado: os primeiros pacotes de cada
#      pessoa passam sem decriptar e viram ruído.
#   2. Mesmo quando decripta, ele ainda faz `update_extended_header` sobre o
#      resultado e corta bytes a mais — corrompendo o Opus já decriptado.
# A prova: capturando o frame após a criptografia de transporte, TODOS traziam o
# marcador DAVE (0xFAFA) e `dave.decrypt(uid, audio, frame)` devolvia Opus limpo
# em 475/490 frames. Então substituímos `decrypt_rtp` pela versão correta:
#   frame (sem transporte) -> dave.decrypt(uid) -> Opus  (sem cortes extras)
# com fallback: se o ssrc ainda não foi mapeado, tenta cada membro do grupo MLS
# (o decryptor de cada usuário só aceita os frames dele, então acerta sozinho).
#
# Obs.: anunciar "não suporto DAVE" para rebaixar a call (tática antiga do Craig)
# NÃO funciona mais — o servidor de voz do Discord derruba a conexão com o 4017.
try:
    import davey  # noqa: E402
except ImportError:  # sem davey não há calls E2EE para decriptar
    davey = None

# O py-cord emite um RuntimeWarning assustador ("Voice reception is currently
# broken...") em TODO start/stop de gravação, mesmo com o DAVE desligado acima.
# Como já aplicamos o contorno, o aviso só confunde — silencia.
import warnings  # noqa: E402

warnings.filterwarnings(
    "ignore", message="Voice reception is currently broken", category=RuntimeWarning
)

# `stop_recording` levanta RecordingException("You are not recording") se chamado
# duas vezes — e a thread do PacketRouter SEMPRE o chama de novo ao encerrar
# (router.py, bloco finally), estourando um traceback inofensivo porém feio no
# terminal. Substituímos por uma versão idempotente: parar já parado = no-op.
from discord.utils import MISSING  # noqa: E402
from discord.voice.client import VoiceClient  # noqa: E402


def _quiet_stop_recording(self) -> None:
    reader = getattr(self, "_reader", MISSING)
    if reader is MISSING:
        return  # já parado (ex.: 2ª chamada vinda da thread do router)
    reader.stop()
    self._reader = MISSING


VoiceClient.stop_recording = _quiet_stop_recording
VoiceClient.stop_listening = _quiet_stop_recording
# ------------------------------------------------------------------------------

# Formato do PCM que a py-cord entrega: 48 kHz, 2 canais, 16 bits little-endian.
_CHANNELS = 2
_SAMPLE_WIDTH = 2  # bytes por amostra (16 bits)
_SAMPLE_RATE = 48000


# Estatísticas do decode da gravação atual (uma gravação por vez).
decode_stats = {
    "ok": 0, "vazio": 0, "falhou": 0, "bytes_pcm": 0,
    "dave": 0, "claro": 0, "erro": "",
}


def reset_decode_stats() -> None:
    decode_stats.update(
        ok=0, vazio=0, falhou=0, bytes_pcm=0, dave=0, claro=0, erro=""
    )


# --- Conserto 1: decriptação DAVE correta no nível do RTP ----------------------
_orig_decrypt_rtp = PacketDecryptor.decrypt_rtp


def _fixed_decrypt_rtp(self, packet):
    """Decripta o transporte e, se a call for E2EE, o DAVE — na ordem certa."""
    frame = self._decryptor_rtp(packet)  # remove só a criptografia de transporte

    state = self.client._connection
    dave = getattr(state, "dave_session", None)
    if davey is None or dave is None or not getattr(dave, "ready", False):
        decode_stats["claro"] += 1
        return frame  # call sem E2EE: o frame já é Opus

    # Candidatos a "dono" do frame: o ssrc mapeado primeiro; senão, cada membro
    # do grupo MLS (o decryptor de cada usuário rejeita frames que não são dele).
    candidates = []
    uid = state.ssrc_user_map.get(packet.ssrc)
    if uid is not None:
        candidates.append(int(uid))
    for u in dave.get_user_ids():
        iu = int(u)
        if iu not in candidates and iu != getattr(dave, "user_id", None):
            candidates.append(iu)

    frame_em_claro = False  # davey confirmou que ESTE frame não é E2EE?
    for cand in candidates:
        try:
            opus = dave.decrypt(cand, davey.MediaType.audio, frame)
        except Exception as exc:  # noqa: BLE001 — chave errada/ frame em claro
            if "Unencrypted" in str(exc):
                frame_em_claro = True
            if not decode_stats["erro"]:
                decode_stats["erro"] = f"decrypt(uid {cand}): {exc!r}"[:80]
            continue
        decode_stats["dave"] += 1
        return opus  # Opus já pronto — SEM cortes extras (o bug do original)

    # Nenhum decryptor aceitou o frame.
    decode_stats["claro"] += 1
    if frame_em_claro:
        # davey garante que o frame não é E2EE (ex.: transição de época): é Opus
        # legítimo em claro, devolve como está.
        return frame
    # Frame E2EE que não conseguimos decriptar: são bytes cifrados que virariam
    # ruído/clique se fossem pro Opus. Troca por silêncio limpo.
    return OPUS_SILENCE


PacketDecryptor.decrypt_rtp = _fixed_decrypt_rtp


# --- Conserto 2: decode do Opus resiliente + contagem --------------------------
# `packet.decrypted_data` agora chega como Opus correto (graças ao conserto 1).
# Aqui só decodificamos com tolerância: um pacote ruim vira silêncio (b"") em vez
# de estourar OpusError e abortar a gravação inteira.
def _safe_decode_packet(self, packet):
    try:
        pcm = self._decoder.decode(packet.decrypted_data or None, fec=False)
    except Exception as exc:  # noqa: BLE001 — inclui OpusError e afins
        decode_stats["falhou"] += 1
        _log.debug("Pacote de voz corrompido ignorado: %s", exc)
        return packet, b""

    if pcm:
        decode_stats["ok"] += 1
        decode_stats["bytes_pcm"] += len(pcm)
    else:
        decode_stats["vazio"] += 1
    return packet, pcm


PacketDecoder._decode_packet = _safe_decode_packet


# --- Conserto 3: jitter buffer sem-perdas para gravação ------------------------
# O buffer de jitter do py-cord é feito para reprodução em tempo real: guarda no
# máximo `max_size=10` pacotes e DESCARTA os mais antigos quando enche
# (`_cleanup`), além de TRAVAR a drenagem quando há um buraco na sequência
# (`_update_has_item` só libera se o próximo pacote for sequencial). Numa
# gravação isso joga fora a maior parte do áudio (no teste: 472 frames viravam
# 119). Reescrevemos para NUNCA descartar e SEMPRE drenar em ordem — mesmo com
# buracos —, que é o que uma gravação precisa.
from discord.voice.utils.buffer import JitterBuffer  # noqa: E402

JitterBuffer._cleanup = lambda self: None  # nunca descarta pacote antigo


def _draining_update_has_item(self) -> None:
    # Libera a drenagem sempre que houver pacote (após o prefill), sem exigir
    # que o próximo seja sequencial — buracos de rede não travam mais a captura.
    if self._prefill == 0 and self._buffer:
        self._has_item.set()
    else:
        self._has_item.clear()


JitterBuffer._update_has_item = _draining_update_has_item
# ------------------------------------------------------------------------------


def dave_state_report(vc) -> str:
    """Estado da sessão DAVE do voice client, para diagnóstico no log."""
    try:
        conn = vc._connection
        sess = conn.dave_session
        if sess is None:
            return f"DAVE: sem sessão (protocolo da call = {conn.dave_protocol_version})"
        return (
            f"DAVE: protocolo={conn.dave_protocol_version}, ready={sess.ready}, "
            f"época={sess.epoch}, membros_mls={sess.get_user_ids()}"
        )
    except Exception as exc:  # noqa: BLE001
        return f"DAVE: estado indisponível ({exc})"


def _peak_amplitude(pcm: bytes) -> int:
    """Maior amplitude absoluta (0..32767) do PCM 16-bit. 0 = silêncio total."""
    if not pcm:
        return 0
    try:
        import audioop

        return audioop.max(pcm, _SAMPLE_WIDTH)
    except Exception:  # noqa: BLE001 — audioop ausente: varre manualmente
        import struct

        peak = 0
        for (s,) in struct.iter_unpack("<h", pcm[: len(pcm) - (len(pcm) % 2)]):
            peak = max(peak, abs(s))
        return peak
# ------------------------------------------------------------------------------


class PerUserPCMSink(Sink):
    """Guarda o áudio decodificado (PCM) separado por usuário."""

    # O roteador de eventos registra listeners a partir daqui. Não usamos os eventos
    # auxiliares (quem começou/parou de falar), então fica vazio — mas PRECISA existir,
    # senão `SinkEventRouter.register_events` estoura AttributeError.
    __sink_listeners__: list = []

    def __init__(self) -> None:
        super().__init__()
        self.pcm: dict[int, bytearray] = {}  # user_id -> bytes de PCM acumulados

    # A py-cord só decodifica Opus -> PCM quando isto é False.
    def is_opus(self) -> bool:
        return False

    # O roteador percorre os "filhos" do sink; não temos nenhum.
    def walk_children(self):
        return []

    def write(self, data, user) -> None:
        """Recebe um `VoiceData` (com `.pcm`) e o autor (`user`, o `data.source`)."""
        if user is None:
            return
        pcm = getattr(data, "pcm", None)
        if not pcm:
            return
        uid = getattr(user, "id", user)
        self.pcm.setdefault(uid, bytearray()).extend(pcm)

    def cleanup(self) -> None:
        # O áudio já está em memória; a gravação em .wav é feita por save_wavs().
        pass

    def signal_report(self, name_for: Callable[[int], str]) -> str:
        """Resumo do que foi capturado: pico de amplitude por usuário + stats do decode.

        Se `pico=0` em tudo mesmo com bytes capturados, o áudio veio zerado
        (assinatura do DAVE). Se `falhou` domina, os pacotes nem decodificaram.
        """
        linhas = [
            f"pacotes: {decode_stats['ok']} ok, {decode_stats['vazio']} vazios, "
            f"{decode_stats['falhou']} falharam ({decode_stats['bytes_pcm']}B PCM; "
            f"e2ee={decode_stats['dave']}, claro={decode_stats['claro']})"
        ]
        if decode_stats["erro"]:
            linhas.append(f"1º erro DAVE: {decode_stats['erro']}")
        for uid, pcm in self.pcm.items():
            linhas.append(
                f"{name_for(uid)}: {len(pcm)}B, pico={_peak_amplitude(bytes(pcm))}/32767"
            )
        if not self.pcm:
            linhas.append("nenhuma fonte de áudio recebida")
        return " | ".join(linhas)

    def save_wavs(self, out_dir: Path, name_for: Callable[[int], str]) -> dict[str, Path]:
        """Grava um .wav por usuário. `name_for(uid)` devolve o nome do arquivo (sem extensão)."""
        tracks: dict[str, Path] = {}
        for uid, pcm in self.pcm.items():
            if not pcm:
                continue
            speaker = name_for(uid)
            path = out_dir / f"{speaker}.wav"
            with wave.open(str(path), "wb") as f:
                f.setnchannels(_CHANNELS)
                f.setsampwidth(_SAMPLE_WIDTH)
                f.setframerate(_SAMPLE_RATE)
                f.writeframes(bytes(pcm))
            tracks[speaker] = path
        return tracks
