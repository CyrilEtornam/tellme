"""Offline neural text-to-speech using Piper.

The :class:`Speaker` owns a background worker thread that serializes utterances
through a queue so hourly and event announcements never overlap. The Piper voice
model is lazy-loaded on first use (and can be unloaded after idle) to keep the
resting memory footprint low.

Synthesis is deliberately defensive: the ``piper-tts`` Python API has changed
shape across releases, so we try the known in-process strategies and fall back
to the ``piper`` command-line tool if the library isn't importable.
"""

from __future__ import annotations

import io
import logging
import queue
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

from .config import VOICES_DIR

log = logging.getLogger(__name__)

# Unload the model from memory after this many seconds of inactivity.
_IDLE_UNLOAD_SECONDS = 300

# Sentinel pushed onto the queue to tell the worker to exit.
_STOP = object()


def _find_player() -> list[str] | None:
    """Return a command that plays a WAV file streamed on stdin, or None."""
    for exe in ("paplay", "aplay", "pw-play"):
        if path := shutil.which(exe):
            # paplay/pw-play read from stdin when given no file; aplay needs '-'.
            return [path] if exe != "aplay" else [path, "-"]
    return None


class Speaker:
    def __init__(
        self,
        model_name: str,
        voices_dir: Path = VOICES_DIR,
        mute: bool = False,
    ) -> None:
        self.model_name = model_name
        self.voices_dir = Path(voices_dir)
        self.mute = mute

        self._voice = None  # lazily-loaded PiperVoice
        self._voice_lock = threading.Lock()
        self._last_used = 0.0

        self._queue: "queue.Queue[object]" = queue.Queue()
        self._thread = threading.Thread(target=self._worker, name="tts-worker", daemon=True)
        self._started = False

    # --- public API --------------------------------------------------------
    def start(self) -> None:
        if not self._started:
            self._started = True
            self._thread.start()

    def say(self, text: str) -> None:
        """Enqueue text to be spoken. No-op when muted or text is empty."""
        text = (text or "").strip()
        if not text or self.mute:
            return
        self.start()
        self._queue.put(text)

    def speak_blocking(self, text: str) -> bool:
        """Synthesize and play synchronously. Returns True on success.

        Used by one-shot CLI commands (``tellme --say``) that must finish
        before the process exits.
        """
        text = (text or "").strip()
        if not text:
            return False
        try:
            wav = self._synthesize(text)
        except Exception:  # noqa: BLE001 - surface as a clean failure to the CLI
            log.exception("synthesis failed")
            return False
        return self._play(wav)

    def set_mute(self, mute: bool) -> None:
        self.mute = mute
        if mute:
            # Drop anything already queued so muting takes effect immediately.
            self._drain()

    def stop(self) -> None:
        if self._started:
            self._queue.put(_STOP)
            self._thread.join(timeout=2)

    @property
    def model_path(self) -> Path:
        return self.voices_dir / f"{self.model_name}.onnx"

    @property
    def config_path(self) -> Path:
        return self.voices_dir / f"{self.model_name}.onnx.json"

    def model_available(self) -> bool:
        return self.model_path.exists() and self.config_path.exists()

    # --- worker ------------------------------------------------------------
    def _worker(self) -> None:
        while True:
            try:
                item = self._queue.get(timeout=_IDLE_UNLOAD_SECONDS)
            except queue.Empty:
                self._maybe_unload()
                continue
            if item is _STOP:
                return
            if self.mute:
                continue
            try:
                wav = self._synthesize(str(item))
                self._play(wav)
            except Exception:  # noqa: BLE001 - one bad utterance shouldn't kill audio
                log.exception("failed to speak: %r", item)

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass

    def _maybe_unload(self) -> None:
        with self._voice_lock:
            if self._voice is not None and time.monotonic() - self._last_used > _IDLE_UNLOAD_SECONDS:
                log.debug("unloading idle voice model")
                self._voice = None

    # --- synthesis ---------------------------------------------------------
    def _load_voice(self):
        with self._voice_lock:
            if self._voice is None:
                from piper import PiperVoice  # imported lazily; heavy dependency

                if not self.model_available():
                    raise FileNotFoundError(
                        f"Voice model not found: {self.model_path}. "
                        f"Run scripts/get-voice.sh to download it."
                    )
                log.debug("loading voice model %s", self.model_path)
                self._voice = PiperVoice.load(
                    str(self.model_path), config_path=str(self.config_path)
                )
            self._last_used = time.monotonic()
            return self._voice

    def _synthesize(self, text: str) -> bytes:
        """Return WAV bytes for ``text``, trying in-process Piper then the CLI."""
        try:
            return self._synthesize_inprocess(text)
        except ImportError:
            log.debug("piper library unavailable; falling back to CLI")
            return self._synthesize_cli(text)

    def _synthesize_inprocess(self, text: str) -> bytes:
        voice = self._load_voice()
        buf = io.BytesIO()

        # Strategy A: older piper-tts writes directly into a wave.Wave_write.
        try:
            with wave.open(buf, "wb") as wav_file:
                voice.synthesize(text, wav_file)
            data = buf.getvalue()
            if data:
                return data
        except TypeError:
            pass  # Newer API — fall through to the streaming strategy.

        # Strategy B: newer piper-tts yields audio chunks we assemble ourselves.
        sample_rate = getattr(getattr(voice, "config", None), "sample_rate", 22050)
        pcm = bytearray()
        for chunk in voice.synthesize(text):
            pcm += _chunk_to_pcm(chunk)
            sr = getattr(chunk, "sample_rate", None)
            if sr:
                sample_rate = sr
        return _wrap_pcm_wav(bytes(pcm), sample_rate)

    def _synthesize_cli(self, text: str) -> bytes:
        piper = shutil.which("piper")
        if not piper or not self.model_available():
            raise RuntimeError("piper CLI or voice model unavailable")
        proc = subprocess.run(
            [piper, "--model", str(self.model_path), "--output_file", "-"],
            input=text.encode("utf-8"),
            capture_output=True,
            check=True,
        )
        self._last_used = time.monotonic()
        return proc.stdout

    # --- playback ----------------------------------------------------------
    def _play(self, wav_bytes: bytes) -> bool:
        if not wav_bytes:
            return False
        player = _find_player()
        if player is None:
            log.error("no audio player found (install pulseaudio-utils or alsa-utils)")
            return False
        try:
            subprocess.run(player, input=wav_bytes, check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as exc:
            log.error("playback failed: %s", exc.stderr.decode(errors="replace"))
            return False


def _chunk_to_pcm(chunk) -> bytes:
    """Extract int16 PCM bytes from a piper audio chunk across API variants."""
    for attr in ("audio_int16_bytes", "audio_int16", "audio"):
        value = getattr(chunk, attr, None)
        if value is None:
            continue
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        # numpy array of int16
        try:
            return value.astype("<i2").tobytes()  # type: ignore[attr-defined]
        except AttributeError:
            return bytes(value)
    if isinstance(chunk, (bytes, bytearray)):
        return bytes(chunk)
    raise TypeError(f"unrecognized piper audio chunk: {type(chunk)!r}")


def _wrap_pcm_wav(pcm: bytes, sample_rate: int, channels: int = 1, sampwidth: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sampwidth)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return buf.getvalue()
