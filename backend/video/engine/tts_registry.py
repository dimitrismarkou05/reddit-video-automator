"""Global TTS model registry.

Keeps loaded Coqui TTS models alive between pipeline runs so the
~50-second torch initialisation only pays for itself once per model.

Thread-safe: multiple pipeline coroutines can call get_model() concurrently;
only one thread will load a given model at a time.
"""

import logging
import threading
from typing import Dict, Optional, Callable

logger = logging.getLogger(__name__)

# model_name -> loaded TTS instance
_registry: Dict[str, object] = {}
_registry_lock = threading.Lock()

# model_name -> threading.Event (signals load-in-progress)
_loading_events: Dict[str, threading.Event] = {}


def get_model(
    model_name: str,
    progress_callback: Optional[Callable[[int, str], None]] = None,
):
    """Return the TTS model for *model_name*, loading it if necessary.

    If another thread is already loading the same model, this call blocks
    until that load completes (up to 180 s) then returns the shared instance.
    """
    with _registry_lock:
        if model_name in _registry:
            logger.debug(f"[TTS Registry] Cache hit: {model_name}")
            return _registry[model_name]
        already_loading = model_name in _loading_events
        if not already_loading:
            event = threading.Event()
            _loading_events[model_name] = event

    if already_loading:
        # Another thread is loading – wait up to 3 minutes then try once more.
        event = _loading_events.get(model_name)
        if event:
            event.wait(timeout=180)
        with _registry_lock:
            if model_name in _registry:
                return _registry[model_name]
        raise RuntimeError(
            f"[TTS Registry] Model {model_name} did not finish loading in time"
        )

    # We are responsible for loading.
    event = _loading_events[model_name]
    try:
        logger.info(f"[TTS Registry] Loading model: {model_name}")
        if progress_callback:
            progress_callback(0, "downloading_model")
        from TTS.api import TTS  # type: ignore[import-untyped]
        model = TTS(model_name=model_name, progress_bar=False, gpu=False)
        if progress_callback:
            progress_callback(100, "downloading_model")
        with _registry_lock:
            _registry[model_name] = model
        logger.info(f"[TTS Registry] Model ready: {model_name}")
        return model
    except Exception as exc:
        logger.error(f"[TTS Registry] Failed to load {model_name}: {exc}")
        raise
    finally:
        with _registry_lock:
            _loading_events.pop(model_name, None)
        event.set()


def evict(model_name: str) -> None:
    """Remove a model from the registry (e.g. after a failed synthesis)."""
    with _registry_lock:
        dropped = _registry.pop(model_name, None)
    if dropped is not None:
        logger.info(f"[TTS Registry] Evicted: {model_name}")


def warmup(model_name: str) -> None:
    """Pre-load a model in a daemon thread (fire-and-forget)."""
    def _load():
        try:
            get_model(model_name)
        except Exception as exc:
            logger.warning(f"[TTS Registry] Warmup failed for {model_name}: {exc}")

    t = threading.Thread(target=_load, daemon=True, name=f"tts-warmup-{model_name}")
    t.start()
    logger.info(f"[TTS Registry] Warmup started for: {model_name}")
