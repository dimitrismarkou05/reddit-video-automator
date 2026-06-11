"""TTS engine with model registry, chunked synthesis, timeouts, and edge-tts fallback."""



import asyncio

import logging

import re

import subprocess

import tempfile

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from pathlib import Path

from typing import Optional, Callable, List



from sqlalchemy.orm import Session



from core.text_normalize import normalize_for_tts

from services.tts_service import TTSService

from video.engine.utils import get_audio_duration

import video.engine.tts_registry as tts_registry



logger = logging.getLogger(__name__)



# Per-sentence timeout: at least 60 s, plus 2 s per word.

_CHUNK_TIMEOUT_PER_WORD = 2.0

_MIN_CHUNK_TIMEOUT = 60.0

# Edge-tts default voice (online Microsoft TTS – requires internet)

_EDGE_FALLBACK_VOICE = "en-US-AriaNeural"

# Max characters in a single synthesis chunk.

_MAX_CHUNK_CHARS = 150



# Chunks that are only punctuation / too short to synthesize meaningfully.

_TRIVIAL_CHUNK = re.compile(r"^[\s.\-,;:!?…\"']+$")





class TTSProviderError(Exception):

    pass





# ---------------------------------------------------------------------------

# Sentence splitting

# ---------------------------------------------------------------------------



def _is_meaningful_chunk(chunk: str) -> bool:

    """Return False for empty or punctuation-only fragments."""

    stripped = chunk.strip()

    if not stripped:

        return False

    if _TRIVIAL_CHUNK.match(stripped):

        return False

    if len(stripped) <= 1 and not stripped.isalnum():

        return False

    return True





def _split_into_chunks(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> List[str]:

    """Split *text* into sentences, then group short sentences so no chunk

    exceeds *max_chars*.  Returns a non-empty list of non-empty strings."""

    text = normalize_for_tts(text)

    # Split on sentence boundaries (.!?) followed by whitespace or end.

    raw = re.split(r'(?<=[.!?])\s+', text.strip())

    sentences = [s.strip() for s in raw if s.strip() and _is_meaningful_chunk(s.strip())]

    if not sentences:

        normalized = text.strip()

        return [normalized] if normalized else [""]



    chunks: List[str] = []

    current = ""

    for s in sentences:

        if len(current) + len(s) + 1 <= max_chars:

            current = f"{current} {s}".strip() if current else s

        else:

            if current:

                chunks.append(current)

            if len(s) <= max_chars:

                current = s

            else:

                # Force-split very long sentence at word boundaries.

                words = s.split()

                current = ""

                for w in words:

                    if len(current) + len(w) + 1 <= max_chars:

                        current = f"{current} {w}".strip() if current else w

                    else:

                        if current:

                            chunks.append(current)

                        current = w

    if current:

        chunks.append(current)

    return [c for c in (chunks or [text.strip()]) if _is_meaningful_chunk(c)] or [text.strip()]





# ---------------------------------------------------------------------------

# WAV concatenation

# ---------------------------------------------------------------------------



def _concat_wavs(parts: List[Path], output: Path, ffmpeg_path: str = "ffmpeg") -> None:

    """Concatenate *parts* into *output* using FFmpeg concat demuxer."""

    with tempfile.NamedTemporaryFile(

        mode="w", suffix=".txt", delete=False, encoding="utf-8"

    ) as flist:

        for p in parts:

            # Forward slashes work on all platforms including Windows FFmpeg.

            fwd = str(p).replace("\\", "/")

            # Escape single quotes inside the path.

            fwd = fwd.replace("'", "\\'")

            flist.write(f"file '{fwd}'\n")

        list_path = flist.name



    cmd = [

        ffmpeg_path, "-y",

        "-f", "concat", "-safe", "0",

        "-i", list_path,

        "-c", "copy",

        str(output),

    ]

    try:

        result = subprocess.run(cmd, capture_output=True, timeout=60)

    except FileNotFoundError as exc:

        Path(list_path).unlink(missing_ok=True)

        raise TTSProviderError(

            f"FFmpeg not found at '{ffmpeg_path}'. Install FFmpeg in Settings."

        ) from exc

    except OSError as exc:

        Path(list_path).unlink(missing_ok=True)

        raise TTSProviderError(f"WAV concatenation failed: {exc}") from exc



    Path(list_path).unlink(missing_ok=True)

    if result.returncode != 0:

        raise TTSProviderError(

            f"WAV concatenation failed: {result.stderr.decode(errors='replace')}"

        )





# ---------------------------------------------------------------------------

# Coqui TTS provider (chunked, with registry)

# ---------------------------------------------------------------------------



class LocalTTSProvider:

    def __init__(self, model_name: str, ffmpeg_path: str = "ffmpeg"):

        self.model_name = model_name

        self.ffmpeg_path = ffmpeg_path



    def _chunk_timeout(self, chunk: str) -> float:

        words = len(chunk.split())

        return max(_MIN_CHUNK_TIMEOUT, words * _CHUNK_TIMEOUT_PER_WORD)



    def _synthesize_chunk(self, model, chunk: str, chunk_path: Path) -> None:

        model.tts_to_file(text=chunk, file_path=str(chunk_path))



    def synthesize(

        self,

        text: str,

        output_path: Path,

        progress_callback: Optional[Callable[[int, str], None]] = None,

    ) -> float:

        """Synthesize *text* in chunks.  Returns audio duration in seconds."""

        output_path.parent.mkdir(parents=True, exist_ok=True)

        chunks = _split_into_chunks(text)

        total = len(chunks)

        logger.info(

            f"[LocalTTS] Synthesizing {total} chunk(s) with model={self.model_name}"

        )



        # Load (or retrieve cached) model.

        try:

            model = tts_registry.get_model(self.model_name, progress_callback)

        except Exception as exc:

            raise TTSProviderError(f"Failed to load TTS model: {exc}")



        parts: List[Path] = []

        tmp_dir = output_path.parent / "_tts_chunks"

        tmp_dir.mkdir(exist_ok=True)

        try:

            for i, chunk in enumerate(chunks):

                chunk_path = tmp_dir / f"chunk_{i:04d}.wav"

                timeout = self._chunk_timeout(chunk)

                try:

                    with ThreadPoolExecutor(max_workers=1) as pool:

                        future = pool.submit(

                            self._synthesize_chunk, model, chunk, chunk_path

                        )

                        future.result(timeout=timeout)

                except FuturesTimeoutError:

                    tts_registry.evict(self.model_name)

                    raise TTSProviderError(

                        f"Coqui synthesis timed out on chunk {i} after {timeout:.0f}s"

                    )

                except Exception as exc:

                    tts_registry.evict(self.model_name)

                    raise TTSProviderError(

                        f"Coqui synthesis failed on chunk {i}: {exc}"

                    )



                if not chunk_path.exists() or chunk_path.stat().st_size == 0:

                    raise TTSProviderError(f"Empty output for chunk {i}")



                parts.append(chunk_path)



                if progress_callback:

                    sub_pct = int(((i + 1) / total) * 100)

                    progress_callback(sub_pct, "tts_synthesizing")



            if len(parts) == 1:

                import shutil

                shutil.copy2(str(parts[0]), str(output_path))

            elif len(parts) > 1:

                _concat_wavs(parts, output_path, self.ffmpeg_path)

            else:

                raise TTSProviderError("No audio chunks were synthesized")



        finally:

            # Clean up chunk temp files.

            for p in parts:

                p.unlink(missing_ok=True)

            try:

                tmp_dir.rmdir()

            except OSError:

                pass



        return _validated_duration(output_path, text)





# ---------------------------------------------------------------------------

# edge-tts provider (online, fast, always available)

# ---------------------------------------------------------------------------



class EdgeTTSProvider:

    """Microsoft Edge TTS via the edge-tts Python library (requires internet)."""



    def __init__(self, voice: str = _EDGE_FALLBACK_VOICE, ffmpeg_path: str = "ffmpeg"):

        self.voice = voice

        self.ffmpeg_path = ffmpeg_path



    def synthesize(

        self,

        text: str,

        output_path: Path,

        progress_callback: Optional[Callable[[int, str], None]] = None,

    ) -> float:

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if progress_callback:

            progress_callback(5, "tts_synthesizing")

        try:

            import edge_tts  # type: ignore[import-untyped]

        except ImportError:

            raise TTSProviderError(

                "edge-tts is not installed. "

                "Run: pip install edge-tts"

            )



        mp3_path = output_path.with_suffix(".edge.mp3")

        try:

            # asyncio.run() creates its own event loop, which is safe to call

            # from a worker thread (threads have no running loop of their own).

            loop = asyncio.new_event_loop()

            try:

                loop.run_until_complete(_edge_synthesize(text, str(mp3_path), self.voice))

            finally:

                loop.close()

        except Exception as exc:

            raise TTSProviderError(f"edge-tts synthesis failed: {exc}")



        if progress_callback:

            progress_callback(80, "tts_synthesizing")



        # Convert MP3 → WAV using FFmpeg so the rest of the pipeline is uniform.

        cmd = [

            self.ffmpeg_path, "-y",

            "-i", str(mp3_path),

            "-ar", "22050", "-ac", "1",

            str(output_path),

        ]

        try:

            result = subprocess.run(cmd, capture_output=True, timeout=60)

        except (FileNotFoundError, OSError) as exc:

            mp3_path.unlink(missing_ok=True)

            raise TTSProviderError(

                f"FFmpeg not found at '{self.ffmpeg_path}'. Install FFmpeg in Settings."

            ) from exc

        mp3_path.unlink(missing_ok=True)

        if result.returncode != 0:

            raise TTSProviderError(

                f"edge-tts MP3→WAV conversion failed: "

                f"{result.stderr.decode(errors='replace')}"

            )



        if progress_callback:

            progress_callback(100, "tts_synthesizing")



        return _validated_duration(output_path, text)





async def _edge_synthesize(text: str, output_path: str, voice: str) -> None:

    import edge_tts  # type: ignore[import-untyped]

    communicate = edge_tts.Communicate(text, voice)

    await communicate.save(output_path)





# ---------------------------------------------------------------------------

# Audio validation helper

# ---------------------------------------------------------------------------



def _validated_duration(output_path: Path, text: str) -> float:

    """Return audio duration or a word-count estimate on failure."""

    if not output_path.exists():

        raise TTSProviderError(f"TTS output not created: {output_path}")

    if output_path.stat().st_size == 0:

        raise TTSProviderError(f"TTS output is empty: {output_path}")

    try:

        return get_audio_duration(str(output_path))

    except Exception as dur_err:

        words = len(text.split())

        estimated = max(1.0, words / 2.5)

        logger.warning(

            f"[TTS] Could not determine duration ({dur_err}); "

            f"estimating {estimated:.1f}s from {words} words"

        )

        return estimated





# ---------------------------------------------------------------------------

# TTSEngine — orchestrates providers with fallback

# ---------------------------------------------------------------------------



class TTSEngine:

    def __init__(self, db: Session, ffmpeg_path: str = "ffmpeg"):

        self.db = db

        self.service = TTSService(db)

        self.ffmpeg_path = ffmpeg_path



    def get_provider(self, voice_id: str = "default") -> LocalTTSProvider:

        model_name = self.service.get_voice_model_name(voice_id)

        if not model_name:

            from tts_local.mirrors import get_default_model_name

            model_name = get_default_model_name()

        return LocalTTSProvider(model_name, self.ffmpeg_path)



    def synthesize(

        self,

        text: str,

        voice_id: str,

        output_path: Path,

        progress_callback: Optional[Callable[[int, str], None]] = None,

    ) -> float:

        """Synthesize with Coqui TTS; fall back to edge-tts on failure."""

        primary = self.get_provider(voice_id)

        try:

            return primary.synthesize(text, output_path, progress_callback)

        except (TTSProviderError, OSError, FileNotFoundError) as primary_err:

            logger.warning(

                f"[TTSEngine] Primary TTS failed ({primary_err}); "

                "falling back to edge-tts"

            )

            # Clean up any partial output before trying fallback.

            output_path.unlink(missing_ok=True)

            if progress_callback:

                progress_callback(0, "tts_synthesizing")

            fallback = EdgeTTSProvider(ffmpeg_path=self.ffmpeg_path)

            try:

                duration = fallback.synthesize(text, output_path, progress_callback)

                logger.info("[TTSEngine] Fallback edge-tts synthesis succeeded")

                return duration

            except TTSProviderError as fallback_err:

                raise TTSProviderError(

                    f"All TTS providers failed. "

                    f"Primary: {primary_err} | Fallback: {fallback_err}"

                )



    def list_available_voices(self) -> list:

        return self.service.list_voices()


