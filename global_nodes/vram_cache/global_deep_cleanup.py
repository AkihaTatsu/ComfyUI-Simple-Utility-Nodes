"""Best-effort global RAM/VRAM cleanup node for ComfyUI."""

import gc
import json
import logging
import os
import time
from typing import Any, Tuple

import torch

from .utils import (
    disk_monitors,
    empty_cache_markers,
    legacy_patcher_cache,
    ram_cache,
)

logger = logging.getLogger("ComfyUI-Deep-Cleanup")

_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "settings.json"
)
with open(_SETTINGS_PATH, "r", encoding="utf-8") as _f:
    _SETTINGS = json.load(_f)

_CLEANUP_MODES = ["RAM + VRAM", "RAM", "VRAM"]
_MODE_BITS = {
    "RAM": 1,
    "VRAM": 2,
    "RAM + VRAM": 3,
}


def _bits_for_mode(mode: str) -> int:
    return _MODE_BITS.get(mode, _MODE_BITS["RAM + VRAM"])


def _safe_call(label: str, fn) -> Any:
    try:
        return fn()
    except Exception as exc:
        logger.warning("[Deep-Cleanup] %s failed: %s", label, exc)
        return None


def _clear_simple_utility_ram() -> None:
    if disk_monitors().has_active():
        logger.info("[Deep-Cleanup] Waiting for VRAM cache disk-save thread(s).")
        _safe_call("wait for VRAM cache disk saves", disk_monitors().wait_for_all)

    tensor_count = _safe_call("clear tensor RAM cache", ram_cache().clear_all) or 0
    legacy_count = _safe_call("clear legacy RAM cache", legacy_patcher_cache().clear_all) or 0
    marker_count = _safe_call("clear empty RAM markers", empty_cache_markers().clear_all) or 0
    logger.info(
        "[Deep-Cleanup] Cleared Simple Utility RAM cache: %s tensor, %s legacy, %s marker.",
        tensor_count,
        legacy_count,
        marker_count,
    )


def _clear_comfy_ram_helpers() -> None:
    def clear_folder_paths():
        import folder_paths

        cache_helper = getattr(folder_paths, "cache_helper", None)
        if cache_helper is not None and hasattr(cache_helper, "clear"):
            cache_helper.clear()
        filename_list_cache = getattr(folder_paths, "filename_list_cache", None)
        if isinstance(filename_list_cache, dict):
            filename_list_cache.clear()

    _safe_call("clear folder_paths caches", clear_folder_paths)


def _collect_garbage() -> None:
    _safe_call("gc.collect", gc.collect)


def _clear_ram_now() -> None:
    _clear_simple_utility_ram()
    _clear_comfy_ram_helpers()
    _collect_garbage()


def _clear_vram_now() -> None:
    def cleanup_prefetch():
        import comfy.model_prefetch as model_prefetch

        model_prefetch.cleanup_prefetch_queues()

    _safe_call("cleanup prefetch queues", cleanup_prefetch)

    def cleanup_model_management():
        import comfy.model_management as mm

        if hasattr(mm, "unload_all_models"):
            mm.unload_all_models()
        if hasattr(mm, "cleanup_models"):
            mm.cleanup_models()
        if hasattr(mm, "cleanup_models_gc"):
            mm.cleanup_models_gc()
        if hasattr(mm, "reset_cast_buffers"):
            mm.reset_cast_buffers()
        if hasattr(mm, "soft_empty_cache"):
            mm.soft_empty_cache(force=True)

    _safe_call("ComfyUI model management cleanup", cleanup_model_management)

    def cleanup_cuda():
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()

    _safe_call("torch CUDA cleanup", cleanup_cuda)
    _collect_garbage()


def _request_end_of_run_cleanup(bits: int) -> None:
    """Ask ComfyUI's main loop to perform its official post-prompt cleanup.

    The main loop consumes these flags once after task_done(), so multiple Deep
    Cleanup nodes in the same prompt naturally coalesce into one end-of-run pass.
    """
    def set_flags():
        from server import PromptServer

        prompt_server = getattr(PromptServer, "instance", None)
        prompt_queue = getattr(prompt_server, "prompt_queue", None)
        if prompt_queue is None:
            raise RuntimeError("PromptServer prompt_queue is not available")
        if bits & _MODE_BITS["VRAM"]:
            prompt_queue.set_flag("unload_models", True)
        if bits & _MODE_BITS["RAM"]:
            prompt_queue.set_flag("free_memory", True)

    _safe_call("schedule ComfyUI end-of-run cleanup", set_flags)


class SimpleGlobalDeepCleanup:
    """Best-effort RAM/VRAM cleanup node.

    This node cannot strictly restore ComfyUI to a fresh-process state. It clears
    known caches immediately and schedules one extra cleanup pass after the
    current prompt finishes, when executor-held graph/cache references can be
    safely released.
    """

    CATEGORY = "Simple Utility ⛏️/Global"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        settings = _SETTINGS.get("SimpleGlobalDeepCleanup", {})
        return {
            "required": {
                "cleanup_mode": (
                    _CLEANUP_MODES,
                    {
                        "default": settings.get(
                            "default_cleanup_mode",
                            "RAM + VRAM",
                        ),
                    },
                ),
                "anything": ("*",),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("NaN")

    @classmethod
    def VALIDATE_INPUTS(cls, cleanup_mode, anything):
        if cleanup_mode not in _CLEANUP_MODES:
            return f"Invalid cleanup_mode '{cleanup_mode}'. Must be one of {_CLEANUP_MODES}."
        return True

    def execute(self, cleanup_mode: str = "RAM + VRAM", anything: Any = None) -> Tuple[Any]:
        bits = _bits_for_mode(cleanup_mode)
        _request_end_of_run_cleanup(bits)

        t_start = time.perf_counter()
        logger.info("[Deep-Cleanup] Immediate cleanup started: %s.", cleanup_mode)

        if bits & _MODE_BITS["RAM"]:
            _clear_ram_now()
        if bits & _MODE_BITS["VRAM"]:
            _clear_vram_now()

        elapsed = time.perf_counter() - t_start
        logger.info(
            "[Deep-Cleanup] Immediate cleanup finished in %.2fs; end-of-run cleanup is scheduled once.",
            elapsed,
        )
        return (anything,)


NODE_CLASS_MAPPINGS = {
    "SimpleGlobalDeepCleanup": SimpleGlobalDeepCleanup,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleGlobalDeepCleanup": "⛏️ Simple Global Deep Cleanup",
}
