"""VRAM cache management nodes for ComfyUI.

This module provides nodes for saving and restoring the VRAM cache (loaded
models) to/from system RAM and disk, allowing users to temporarily free VRAM
for other tasks and restore the model state later.

Save flow:
  1.  Collect all ModelPatcher references currently tracked by
      ``comfy.model_management.current_loaded_models``.
  2.  Check available system RAM.
      • Enough RAM  → unload models from VRAM to CPU (RAM), store strong
        references in the RAM cache, and start a **background thread** that
        serialises the models to disk.  Downstream nodes execute immediately.
      • Not enough RAM → serialise models to disk **synchronously**, then
        unload VRAM.
  3.  VRAM is cleared via ``unload_all_models`` + ``soft_empty_cache``.

Load flow:
  1.  Look up the RAM cache first (fast, full ModelPatcher objects).
  2.  If not in RAM, wait for any in-flight background disk save to finish,
      then try loading from disk.
  3.  Clear current VRAM and call ``load_models_gpu`` with the restored
      ModelPatcher list.

Lifecycle guarantees:
  • RAM and disk caches are **never** automatically evicted.  They can only be
    overwritten by another save with the same ``cache_name``, or cleared when
    ComfyUI is terminated / restarted.
  • On module import (= ComfyUI startup), all previous RAM and disk caches
    are purged so that stale data from a prior session does not linger.
"""

import atexit
import gc
import glob
import logging
import os
import pickle
import shutil
import tempfile
import threading
from typing import Any, Dict, List, Optional, Tuple

import torch

try:
    import dill as _dill
    _HAS_DILL = True
except ImportError:
    _dill = None
    _HAS_DILL = False

import comfy.model_management
from comfy.model_patcher import ModelPatcher

logger = logging.getLogger("ComfyUI-Simple-Utility-Nodes")

# ---------------------------------------------------------------------------
# Cache storage
# ---------------------------------------------------------------------------

# RAM cache: cache_name → list[ModelPatcher]  (strong refs keep them alive)
_VRAM_CACHE_RAM: Dict[str, List[ModelPatcher]] = {}

# Disk cache: cache_name → absolute file path
_VRAM_CACHE_DISK: Dict[str, str] = {}

# Thread‑safety
_CACHE_LOCK = threading.Lock()

# Background disk‑save threads keyed by cache_name
_BACKGROUND_THREADS: Dict[str, threading.Thread] = {}

# Disk cache directory — every ComfyUI instance gets its own unique temp dir.
# A common parent lives under the system temp folder so that leftover dirs
# from crashed / killed instances can be discovered and cleaned up on restart.
_CACHE_PARENT_DIR = os.path.join(tempfile.gettempdir(), "comfyui_vram_cache")

# ---------------------------------------------------------------------------
# Startup cleanup — remove ALL prior instances' leftover cache directories
# ---------------------------------------------------------------------------

def _cleanup_stale_disk_caches() -> None:
    """Remove every ``comfyui_vram_cache/comfyui_vc_*`` directory from the
    system temp folder.  Safe to call even when no leftovers exist."""
    if not os.path.isdir(_CACHE_PARENT_DIR):
        return
    for entry in glob.glob(os.path.join(_CACHE_PARENT_DIR, "comfyui_vc_*")):
        if os.path.isdir(entry):
            try:
                shutil.rmtree(entry)
                logger.info("[VRAM Cache] Removed stale disk cache: %s", entry)
            except OSError as exc:
                logger.warning("[VRAM Cache] Could not remove %s: %s", entry, exc)


def cleanup_all_caches() -> None:
    """Clear every RAM and disk cache.  Called once at import time."""
    with _CACHE_LOCK:
        _VRAM_CACHE_RAM.clear()
        _VRAM_CACHE_DISK.clear()

    _cleanup_stale_disk_caches()


# Executed on first import → ComfyUI startup
cleanup_all_caches()

# Now create a fresh, unique temp directory for *this* instance.
os.makedirs(_CACHE_PARENT_DIR, exist_ok=True)
_CACHE_DIR: str = tempfile.mkdtemp(prefix="comfyui_vc_", dir=_CACHE_PARENT_DIR)
logger.info("[VRAM Cache] Disk cache directory for this instance: %s", _CACHE_DIR)


def _cleanup_on_exit() -> None:
    """Best‑effort cleanup when the process exits normally."""
    try:
        if os.path.isdir(_CACHE_DIR):
            shutil.rmtree(_CACHE_DIR)
    except OSError:
        pass


atexit.register(_cleanup_on_exit)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_cache_dir() -> None:
    os.makedirs(_CACHE_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Size / label helpers
# ---------------------------------------------------------------------------

def _fmt_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable MB or GB string."""
    if num_bytes >= 1024 ** 3:
        return f"{num_bytes / (1024 ** 3):.2f} GB"
    return f"{num_bytes / (1024 ** 2):.2f} MB"


def _patchers_total_bytes(patchers: List[ModelPatcher]) -> int:
    """Sum the reported size of each ModelPatcher in bytes."""
    return sum(p.size for p in patchers if p is not None)


def _patcher_label(patcher: ModelPatcher) -> str:
    """Human-readable label for a single ModelPatcher."""
    name = type(patcher.model).__name__ if patcher.model is not None else "?"
    return f"{name} ({_fmt_size(patcher.size)})"


def _free_vram_str() -> str:
    """Return a human-readable string of free VRAM on the default CUDA device.
    Returns 'N/A' if CUDA is unavailable or the query fails."""
    try:
        if torch.cuda.is_available():
            free = comfy.model_management.get_free_memory(torch.device("cuda"))
            return _fmt_size(free)
    except Exception:
        pass
    return "N/A"


def _log_patchers(patchers: List[ModelPatcher], indent: str = "  ") -> None:
    """Log one line per patcher at DEBUG level with index, name and size."""
    for i, p in enumerate(patchers, start=1):
        if p is not None:
            logger.debug("%s#%d  %s", indent, i, _patcher_label(p))


def _disk_cache_path(cache_name: str, use_dill: bool = False) -> str:
    safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in cache_name)
    ext = ".dill" if use_dill else ".pt"
    return os.path.join(_CACHE_DIR, f"{safe}{ext}")


def _collect_save_data(patchers: List[ModelPatcher]) -> list:
    """Build a serialisable list of dicts from ModelPatcher objects."""
    save_data = []
    for patcher in patchers:
        if patcher is None or patcher.model is None:
            continue
        save_data.append({
            "model": patcher.model,                       # nn.Module
            "load_device": str(patcher.load_device),
            "offload_device": str(patcher.offload_device),
            "size": patcher.size,
            "weight_inplace_update": patcher.weight_inplace_update,
        })
    return save_data


def _save_to_disk(cache_name: str, patchers: List[ModelPatcher]) -> None:
    """Serialise model nn.Modules + device metadata to disk.

    Uses standard ``torch.save`` (pickle) first.  If pickling fails (e.g.
    dynamically-created local classes such as
    ``model_sampling.<locals>.ModelSampling``), falls back to ``dill`` as the
    pickle module.  Files saved via dill use a ``.dill`` extension so that
    ``_load_from_disk`` can choose the right deserialiser.
    """
    try:
        _ensure_cache_dir()

        save_data = _collect_save_data(patchers)
        if not save_data:
            return

        # ── Attempt 1: standard pickle ───────────────────────────────
        try:
            path = _disk_cache_path(cache_name, use_dill=False)
            torch.save(save_data, path)
            # Remove any stale dill variant for this name
            _dill_path = _disk_cache_path(cache_name, use_dill=True)
            if os.path.exists(_dill_path):
                try:
                    os.remove(_dill_path)
                except OSError:
                    pass
        except (pickle.PicklingError, TypeError, AttributeError) as pkl_exc:
            # ── Attempt 2: dill fallback ─────────────────────────────
            if not _HAS_DILL:
                raise RuntimeError(
                    f"Standard pickle failed ({pkl_exc}). "
                    f"Install 'dill' (pip install dill) to enable the "
                    f"fallback serialiser for unpicklable model objects."
                ) from pkl_exc

            logger.info(
                "[VRAM Cache] Standard pickle failed for '%s' (%s). "
                "Retrying with dill …",
                cache_name, pkl_exc,
            )
            path = _disk_cache_path(cache_name, use_dill=True)
            torch.save(save_data, path, pickle_module=_dill)
            # Remove any stale pickle variant for this name
            _pkl_path = _disk_cache_path(cache_name, use_dill=False)
            if os.path.exists(_pkl_path):
                try:
                    os.remove(_pkl_path)
                except OSError:
                    pass

        with _CACHE_LOCK:
            _VRAM_CACHE_DISK[cache_name] = path

        serialiser = "dill" if path.endswith(".dill") else "pickle"
        try:
            file_size_str = _fmt_size(os.path.getsize(path))
        except OSError:
            file_size_str = "unknown size"
        total_bytes = sum(d.get("size", 0) for d in save_data)
        logger.info(
            "[VRAM Cache] Disk save complete for '%s': %d model(s), "
            "total model size %s, file size %s, serialiser: %s — %s",
            cache_name, len(save_data), _fmt_size(total_bytes),
            file_size_str, serialiser, path,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("[VRAM Cache] Disk save failed for '%s': %s", cache_name, exc)


def _deserialise_patchers(save_data: list) -> List[ModelPatcher]:
    """Reconstruct ModelPatcher objects from a loaded save_data list."""
    patchers: List[ModelPatcher] = []
    for item in save_data:
        load_dev = torch.device(item["load_device"])
        offload_dev = torch.device(item["offload_device"])
        patcher = ModelPatcher(
            model=item["model"],
            load_device=load_dev,
            offload_device=offload_dev,
            size=item["size"],
            weight_inplace_update=item.get("weight_inplace_update", False),
        )
        patchers.append(patcher)
    return patchers


def _load_from_disk(cache_name: str) -> Optional[List[ModelPatcher]]:
    """Deserialise a ``.pt`` or ``.dill`` file back into ModelPatcher objects.

    Checks the path stored in ``_VRAM_CACHE_DISK`` first.  If that is missing,
    probes both extensions so a cache saved in a previous run (before a
    restart) can still be found.
    """
    with _CACHE_LOCK:
        path = _VRAM_CACHE_DISK.get(cache_name)

    # Fallback: probe both extensions if the mapping is empty
    if path is None or not os.path.exists(path):
        for use_dill in (False, True):
            candidate = _disk_cache_path(cache_name, use_dill=use_dill)
            if os.path.exists(candidate):
                path = candidate
                break

    if path is None or not os.path.exists(path):
        return None

    try:
        use_dill_load = path.endswith(".dill")
        if use_dill_load:
            if not _HAS_DILL:
                logger.error(
                    "[VRAM Cache] Cache '%s' was saved with dill but dill "
                    "is not installed.  Install it with: pip install dill",
                    cache_name,
                )
                return None
            save_data = torch.load(path, pickle_module=_dill, weights_only=False)
        else:
            save_data = torch.load(path, weights_only=False)

        patchers = _deserialise_patchers(save_data)

        serialiser = "dill" if use_dill_load else "pickle"
        total_bytes = _patchers_total_bytes(patchers)
        try:
            file_size_str = _fmt_size(os.path.getsize(path))
        except OSError:
            file_size_str = "unknown size"
        logger.info(
            "[VRAM Cache] Disk load complete for '%s': %d model(s), "
            "total model size %s, file size %s, serialiser: %s",
            cache_name, len(patchers), _fmt_size(total_bytes),
            file_size_str, serialiser,
        )
        _log_patchers(patchers)
        return patchers
    except Exception as exc:  # noqa: BLE001
        logger.error("[VRAM Cache] Disk load failed for '%s': %s", cache_name, exc)
        return None


def _estimate_models_ram_usage() -> int:
    """Bytes needed to keep all currently‑loaded VRAM models on CPU."""
    total = 0
    for lm in comfy.model_management.current_loaded_models:
        if lm.model is not None:
            total += lm.model_memory()
    return total


def _wait_for_background_thread(cache_name: str) -> None:
    """Block until a previous background disk‑save finishes (if any)."""
    thread = _BACKGROUND_THREADS.get(cache_name)
    if thread is not None and thread.is_alive():
        logger.info(
            "[VRAM Cache] Waiting for background disk save '%s' to complete …",
            cache_name,
        )
        thread.join()


# ---------------------------------------------------------------------------
# Node classes
# ---------------------------------------------------------------------------

class SimpleGlobalVRAMCacheSaving:
    """Save the current VRAM cache to RAM (and disk) and clear VRAM.

    If enough system RAM is available the models are moved to CPU first (fast)
    and a background thread saves them to disk without blocking downstream
    nodes.  Otherwise the disk save happens synchronously before the node
    returns.
    """

    CATEGORY = "Simple Utility ⛏️/Global"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "anything": ("*",),
                "cache_name": ("STRING", {
                    "default": "VRAM_cache",
                    "multiline": False,
                }),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, cache_name, anything):
        if not cache_name or not cache_name.strip():
            return "Cache name cannot be empty."
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def execute(self, anything: Any, cache_name: str) -> Tuple[Any]:
        cache_name = cache_name.strip()

        # ── Collect ModelPatcher references ──────────────────────────
        patchers: List[ModelPatcher] = []
        for lm in comfy.model_management.current_loaded_models:
            patcher = lm.model
            if patcher is not None:
                patchers.append(patcher)

        if not patchers:
            logger.info(
                "[VRAM Cache] No models in VRAM to save for cache '%s'.",
                cache_name,
            )
            return (anything,)

        total_bytes = _patchers_total_bytes(patchers)
        model_ram_needed = _estimate_models_ram_usage()
        free_ram = comfy.model_management.get_free_ram()
        safety_margin = max(int(model_ram_needed * 0.2), 512 * 1024 * 1024)
        enough_ram = free_ram > (model_ram_needed + safety_margin)

        # ── Log what we're about to cache ────────────────────────────
        logger.info(
            "[VRAM Cache] Caching %d model(s) — total size: %s "
            "| free RAM: %s | free VRAM: %s",
            len(patchers), _fmt_size(total_bytes),
            _fmt_size(free_ram), _free_vram_str(),
        )
        _log_patchers(patchers)

        if enough_ram:
            # ── Fast path: RAM first, background disk save ───────────
            logger.info(
                "[VRAM Cache] RAM is sufficient — moving %d model(s) (%s) "
                "to RAM for cache '%s'. Background disk save will follow.",
                len(patchers), _fmt_size(total_bytes), cache_name,
            )

            # Move weights from GPU → CPU
            comfy.model_management.unload_all_models()
            comfy.model_management.soft_empty_cache()

            # Protect the patchers with strong references
            with _CACHE_LOCK:
                _VRAM_CACHE_RAM[cache_name] = patchers

            logger.info(
                "[VRAM Cache] %d model(s) (%s) saved to RAM cache '%s'. "
                "Free VRAM after unload: %s",
                len(patchers), _fmt_size(total_bytes), cache_name,
                _free_vram_str(),
            )

            # Wait for any prior background save of the same name
            _wait_for_background_thread(cache_name)

            thread = threading.Thread(
                target=_save_to_disk,
                args=(cache_name, patchers),
                daemon=True,
                name=f"vram_cache_disk_{cache_name}",
            )
            _BACKGROUND_THREADS[cache_name] = thread
            thread.start()
            logger.info(
                "[VRAM Cache] Background disk save started for cache '%s'.",
                cache_name,
            )
        else:
            # ── Slow path: disk first (blocking), then clear VRAM ────
            logger.info(
                "[VRAM Cache] Not enough RAM for in-memory copy "
                "(%s needed + margin, %s free) — saving %d model(s) (%s) "
                "to disk synchronously for cache '%s'.",
                _fmt_size(model_ram_needed), _fmt_size(free_ram),
                len(patchers), _fmt_size(total_bytes), cache_name,
            )

            # Wait for any prior background save of the same name
            _wait_for_background_thread(cache_name)

            # Disk save while models are still resident (CPU or GPU)
            _save_to_disk(cache_name, patchers)

            # Now clear VRAM
            comfy.model_management.unload_all_models()
            comfy.model_management.soft_empty_cache()

            # Still keep RAM references if possible (they cost nothing
            # extra since the weights are already on CPU after unload)
            with _CACHE_LOCK:
                _VRAM_CACHE_RAM[cache_name] = patchers

            logger.info(
                "[VRAM Cache] %d model(s) (%s) saved to disk cache '%s'. "
                "Free VRAM after unload: %s",
                len(patchers), _fmt_size(total_bytes), cache_name,
                _free_vram_str(),
            )

        return (anything,)


class SimpleGlobalVRAMCacheLoading:
    """Restore a previously saved VRAM cache from RAM or disk.

    Checks the RAM cache first (preserves full ModelPatcher state).
    Falls back to the disk cache if the RAM entry is absent.
    Raises an error when no cache with the given name exists.
    """

    CATEGORY = "Simple Utility ⛏️/Global"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "anything": ("*",),
                "cache_name": ("STRING", {
                    "default": "VRAM_cache",
                    "multiline": False,
                }),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, cache_name, anything):
        if not cache_name or not cache_name.strip():
            return "Cache name cannot be empty."
        return True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def execute(self, anything: Any, cache_name: str) -> Tuple[Any]:
        cache_name = cache_name.strip()

        patchers: Optional[List[ModelPatcher]] = None
        source: Optional[str] = None

        # ── 1. Try RAM cache ────────────────────────────────────────
        with _CACHE_LOCK:
            if cache_name in _VRAM_CACHE_RAM:
                patchers = _VRAM_CACHE_RAM[cache_name]
                source = "RAM"

        # ── 2. Fallback: disk cache ─────────────────────────────────
        if patchers is None:
            # Ensure any in‑flight background save has finished
            _wait_for_background_thread(cache_name)

            patchers = _load_from_disk(cache_name)
            if patchers is not None:
                source = "disk"
                # Promote to RAM cache for faster access next time
                with _CACHE_LOCK:
                    _VRAM_CACHE_RAM[cache_name] = patchers

        # ── 3. Error if nothing was found ───────────────────────────
        if patchers is None or len(patchers) == 0:
            with _CACHE_LOCK:
                ram_keys = list(_VRAM_CACHE_RAM.keys())
                disk_keys = list(_VRAM_CACHE_DISK.keys())
            raise RuntimeError(
                f"[VRAM Cache] No cache found with name '{cache_name}'.\n\n"
                f"Make sure a 'Simple Global VRAM Cache Saving' node with the "
                f"same cache_name has been executed before this node.\n"
                f"Available RAM caches: {ram_keys}\n"
                f"Available disk caches: {disk_keys}"
            )

        # ── 4. Clear current VRAM and restore saved models ──────────
        alive = [p for p in patchers if p is not None]
        total_bytes = _patchers_total_bytes(alive)

        logger.info(
            "[VRAM Cache] Restoring %d model(s) (%s) from %s cache '%s' to VRAM "
            "| free VRAM before: %s",
            len(alive), _fmt_size(total_bytes), source, cache_name,
            _free_vram_str(),
        )
        _log_patchers(alive)

        comfy.model_management.unload_all_models()
        comfy.model_management.soft_empty_cache()

        if alive:
            comfy.model_management.load_models_gpu(alive)
            logger.info(
                "[VRAM Cache] Restored %d model(s) (%s) from %s cache '%s' to VRAM. "
                "Free VRAM after restore: %s",
                len(alive), _fmt_size(total_bytes), source, cache_name,
                _free_vram_str(),
            )

        return (anything,)


class SimpleVRAMCacheRAMClearing:
    """Clear **all** VRAM caches currently held in system RAM.

    Disk caches are **not** affected — they remain available for future
    ``Simple Global VRAM Cache Loading`` nodes to fall back on.

    This is useful to reclaim RAM after you no longer need the fast‑path
    cached models.
    """

    CATEGORY = "Simple Utility ⛏️/Global"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "anything": ("*",),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def execute(self, anything: Any) -> Tuple[Any]:
        with _CACHE_LOCK:
            # Snapshot sizes before clearing
            snapshot = {
                name: list(plist)
                for name, plist in _VRAM_CACHE_RAM.items()
            }
            _VRAM_CACHE_RAM.clear()

        if not snapshot:
            logger.info("[VRAM Cache] No RAM caches to clear.")
            return (anything,)

        total_cleared_bytes = 0
        for name, plist in snapshot.items():
            cache_bytes = _patchers_total_bytes(plist)
            total_cleared_bytes += cache_bytes
            logger.info(
                "[VRAM Cache]   '%s' — %d model(s), %s",
                name, len(plist), _fmt_size(cache_bytes),
            )

        gc.collect()
        logger.info(
            "[VRAM Cache] Cleared %d RAM cache(s) — total size freed: %s. "
            "Disk caches are unaffected.",
            len(snapshot), _fmt_size(total_cleared_bytes),
        )

        return (anything,)


# ---------------------------------------------------------------------------
# Node registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "SimpleGlobalVRAMCacheSaving": SimpleGlobalVRAMCacheSaving,
    "SimpleGlobalVRAMCacheLoading": SimpleGlobalVRAMCacheLoading,
    "SimpleVRAMCacheRAMClearing": SimpleVRAMCacheRAMClearing,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleGlobalVRAMCacheSaving": "⛏️ Simple Global VRAM Cache Saving",
    "SimpleGlobalVRAMCacheLoading": "⛏️ Simple Global VRAM Cache Loading",
    "SimpleVRAMCacheRAMClearing": "⛏️ Simple VRAM Cache RAM Clearing",
}
