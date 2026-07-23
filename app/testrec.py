"""Gravador do microfone para o teste rápido (sem Discord).

Grava do microfone padrão para um WAV, que depois é transcrito e vira uma
mini-ata — validando o núcleo (transcrição + geração de ata) sem o bot.
"""
from __future__ import annotations

import array
import threading
import wave
from pathlib import Path

import sounddevice as sd


class TestRecorder:
    def __init__(self, samplerate: int = 16000, channels: int = 1, device=None):
        # device: índice do microfone (None = padrão do SO).
        self.device = device
        # 16 kHz mono é o ideal para o Whisper; se o dispositivo não suportar,
        # cai para a taxa padrão dele (o Whisper reamostra internamente).
        try:
            sd.check_input_settings(
                device=device, samplerate=samplerate, channels=channels, dtype="int16"
            )
        except Exception:
            samplerate = int(sd.query_devices(device, kind="input")["default_samplerate"])
        self.samplerate = samplerate
        self.channels = channels
        self._frames: list[bytes] = []
        self._stream: sd.RawInputStream | None = None
        self._lock = threading.Lock()
        self.recording = False
        self.level = 0.0  # nível de áudio atual (0..1) para o medidor visual

    def _callback(self, indata, frames, time_, status):  # noqa: ANN001
        b = bytes(indata)
        with self._lock:
            self._frames.append(b)
        # Pico do bloco (subamostrado) para o medidor de voz na interface.
        try:
            samples = array.array("h")
            samples.frombytes(b)
            n = len(samples)
            if n:
                step = max(1, n // 256)
                peak = max(abs(samples[i]) for i in range(0, n, step))
                self.level = peak / 32768.0
        except Exception:
            pass

    def start(self) -> None:
        self._frames = []
        self.level = 0.0
        self._stream = sd.RawInputStream(
            samplerate=self.samplerate,
            channels=self.channels,
            dtype="int16",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()
        self.recording = True

    def stop(self, path: Path) -> Path:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.recording = False
        with self._lock:
            data = b"".join(self._frames)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(self.channels)
            w.setsampwidth(2)  # int16 = 2 bytes
            w.setframerate(self.samplerate)
            w.writeframes(data)
        return path
