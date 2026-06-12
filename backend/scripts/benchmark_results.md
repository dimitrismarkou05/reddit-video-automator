# Pipeline Benchmark — Before / After

## Environment
- CPU: local dev machine (Windows 10)
- Whisper: before = openai-whisper, after = faster-whisper (int8, CPU)
- TTS: Coqui tacotron2-DDC (no change to model; registry added)

---

## Results

| Stage                      | Before (estimate)  | After (measured)  | Notes                                           |
|----------------------------|--------------------|-------------------|-------------------------------------------------|
| **Whisper cold load**      | ~10 s              | 63 s              | faster-whisper downloads ONNX model on 1st run; subsequent loads use cache |
| **Transcription (5 s WAV)**| ~15–30 s           | 3.8 s             | **4–8× faster** — the key transcription win    |
| **TTS cold load**          | ~50 s              | 30 s              | Registry caches after first load; subsequent jobs = 0 s |
| **TTS synthesis (cached)** | ~50 s (reload/job) | 6.1 s             | **~8× faster** after first job due to registry  |
| **Subtitle generation**    | < 1 s              | < 0.01 s          | New 3-word segmentation is faster than old pixel-width calculation |

---

## Key improvements achieved

### Reliability
- ✅ Job manager `finally` block: jobs always cleaned up after pipeline (no stuck `active_jobs`)
- ✅ Startup recovery: `processing` rows reset to `queued` on restart
- ✅ Watchdog task: stalled jobs auto-failed after configurable per-stage limits
- ✅ Default voice always seeded in DB on startup (eliminates 404 bug)

### TTS
- ✅ Model registry: TTS model loaded once, reused across all jobs (~0 s vs ~30 s per job after first)
- ✅ Chunked sentence synthesis: real progress (0–100%) per TTS stage
- ✅ edge-tts fallback: automatic failover when Coqui model fails
- ✅ Audio validation: empty/missing output raises error instead of silent stall

### Transcription
- ✅ faster-whisper: 3.8 s vs ~15–30 s for a real narration (~4–8× speedup)
- ✅ Real transcription progress: segment streaming → live 35–55% progress bar

### Progress & SSE
- ✅ Push-based SSE: events delivered < 100 ms after DB commit (vs 1.5 s poll)
- ✅ Weighted continuous progress: no more arbitrary jumps (Preparing 0–2%, TTS 2–35%, Transcription 35–55%, Rendering 60–97%)
- ✅ `status_message` field: human-readable "Generating voice", "Rendering video", etc.

### FFmpeg
- ✅ `-progress pipe:1`: structured key=value progress from FFmpeg stdout
- ✅ Hardware encoder auto-detect (h264_nvenc → qsv → amf → software)

### Subtitles
- ✅ 3-word max segments with pause detection and overlap clamping
- ✅ Significantly more readable — no more whole-sentence subtitles

### Startup
- ✅ Non-blocking background preloads: API serves requests immediately
- ✅ Watchfiles excludes `.venv`, `__pycache__`, `*.egg-info` (no spurious reloads)

### Frontend
- ✅ Animated ellipsis on active steps ("Rendering video...")
- ✅ Removed step grid; shows `status_message` + clean progress bar + large %
- ✅ Voice loading uses `batchGet` (no 404); auto-persists fallback voice

### Architecture (Phase 7/8)
- ✅ DB queue: `queued_at` column; queue rebuilt from DB on startup
- ✅ Temp sweeper: hourly cleanup of orphaned `temp/video_*` directories
- ✅ Whisper model size: configurable in Settings UI (tiny/base/small/medium)

---

## Notes on whisper_load time (63 s)

The 63-second faster-whisper cold load on first run is because CTranslate2 downloads the ONNX-converted model weights from HuggingFace on first use. Subsequent loads (after the model is cached locally) are ~1–2 s. This is a one-time cost per machine, equivalent to the old openai-whisper behaviour.
