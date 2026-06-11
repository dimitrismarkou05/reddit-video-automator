"""Pipeline benchmark script.

Run from the backend directory with the venv active:

    python scripts/benchmark_pipeline.py

Measures:
  - Whisper model load time
  - TTS model load time (registry warm-up)
  - Transcription time (on a synthetic WAV)
  - TTS synthesis time (short sentence)
  - Subtitle generation time

Results are printed as a table so you can compare before/after changes.
"""

import os
import sys
import time
import tempfile
import wave
import struct

# Ensure the backend package root is on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_silent_wav(path: str, duration_s: float = 5.0, sample_rate: int = 22050) -> None:
    """Write a silent WAV file of *duration_s* seconds for benchmarking."""
    n_frames = int(sample_rate * duration_s)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack("<" + "h" * n_frames, *([0] * n_frames)))


def _timeit(label: str, fn, *args, **kwargs):
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    elapsed = time.perf_counter() - t0
    print(f"  {label:<45} {elapsed:>7.2f}s")
    return result, elapsed


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------

def bench_whisper_load(model_size: str = "base"):
    print("\n[1] Whisper model load")
    from video.engine.subtitles import _load_whisper_model
    # Clear cache so we measure cold load.
    _load_whisper_model.cache_clear()
    model, t = _timeit(f"Load faster-whisper '{model_size}'", _load_whisper_model, model_size)
    return t


def bench_transcription(model_size: str = "base"):
    print("\n[2] Transcription (5s silent WAV)")
    from video.engine.subtitles import SubtitleGenerator
    gen = SubtitleGenerator(model_size)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    _make_silent_wav(wav_path, duration_s=5.0)
    _, t = _timeit("Transcribe 5s audio", gen.transcribe, wav_path)
    os.unlink(wav_path)
    return t


def bench_tts_load():
    print("\n[3] TTS model load (registry cold)")
    import video.engine.tts_registry as reg
    from tts_local.mirrors import get_default_model_name
    model_name = get_default_model_name()
    reg.evict(model_name)  # ensure cold
    _, t = _timeit(f"Load TTS '{model_name}'", reg.get_model, model_name)
    return t


def bench_tts_synthesis_cached():
    print("\n[4] TTS synthesis (registry warm)")
    import video.engine.tts_registry as reg
    from tts_local.mirrors import get_default_model_name
    from pathlib import Path
    model_name = get_default_model_name()
    model = reg.get_model(model_name)  # warm load

    SHORT_TEXT = "Hello, this is a benchmark test of the TTS synthesis engine."
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        out_path = f.name

    def _synth():
        model.tts_to_file(text=SHORT_TEXT, file_path=out_path)

    _, t = _timeit("Synthesize short sentence (cached model)", _synth)
    try:
        os.unlink(out_path)
    except OSError:
        pass
    return t


def bench_subtitle_generation():
    print("\n[5] Subtitle ASS generation (100-segment whisper result)")
    from video.engine.subtitles import SubtitleGenerator
    from video.schemas import SubtitleStyle
    from pathlib import Path

    gen = SubtitleGenerator()
    # Fabricate a whisper-like result.
    segments = []
    t = 0.0
    for i in range(100):
        words = [
            {"word": w, "start": t + j * 0.3, "end": t + j * 0.3 + 0.25}
            for j, w in enumerate(["Hello", "world", "this", "is", "test"])
        ]
        segments.append({"id": i, "start": t, "end": t + 1.5, "text": "Hello world this is test", "words": words})
        t += 1.5

    with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
        ass_path = Path(f.name)

    _, t = _timeit("Generate ASS (100 segments)", gen.generate_ass,
                   {"segments": segments}, ass_path, SubtitleStyle())
    ass_path.unlink(missing_ok=True)
    return t


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Reddit Video Automator — Pipeline Benchmark")
    print("=" * 60)

    results = {}

    # Whisper
    try:
        results["whisper_load"] = bench_whisper_load()
    except Exception as exc:
        print(f"  ERROR: {exc}")

    try:
        results["transcription_5s"] = bench_transcription()
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # TTS
    try:
        results["tts_cold_load"] = bench_tts_load()
    except Exception as exc:
        print(f"  ERROR: {exc}")

    try:
        results["tts_synth_cached"] = bench_tts_synthesis_cached()
    except Exception as exc:
        print(f"  ERROR: {exc}")

    # Subtitles
    try:
        results["subtitle_generation"] = bench_subtitle_generation()
    except Exception as exc:
        print(f"  ERROR: {exc}")

    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    for k, v in results.items():
        print(f"  {k:<40} {v:>7.2f}s")
    print()


if __name__ == "__main__":
    main()
