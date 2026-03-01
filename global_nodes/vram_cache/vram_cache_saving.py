"""VRAM Cache Saving node for ComfyUI.

Algorithm overview
──────────────────
1. Capture every tensor currently loaded in VRAM (via ComfyUI model_management).
   Uses named_parameters/named_buffers for zero-copy references (no VRAM clone).
2. Measure total cache size vs. free RAM.
   • RAM + Disk branch  (free RAM ≥ cache size):
       a. Bulk-transfer tensors GPU -> CPU in a single DMA (bulk_vram_to_cpu).
       b. Store CPU tensors in the RAM cache (mmap-guarded).
       c. Clean VRAM completely.
       d. Kick off a background thread that writes RAM cache → disk.
       e. Node finishes **immediately** — disk I/O continues in background.
   • Disk Only branch  (free RAM < cache size):
       a. Kick off a background thread that reads VRAM tensors → disk.
       b. Wait until the thread is done.
       c. Clean VRAM completely.
       d. Node finishes.
3. Detailed logging at every step.
"""

import gc
import json
import logging
import os
import time
import warnings
from typing import Any, Tuple

import torch

from .utils import (
    bulk_vram_to_cpu,
    capture_vram_state_dict,
    cleanup_current_vram,
    disk_monitors,
    format_bytes,
    get_cache_file_path,
    get_free_ram_bytes,
    get_total_vram_cache_size,
    ram_cache,
)

logger = logging.getLogger("ComfyUI-VRAM-Cache")

# ── Settings ──────────────────────────────────────────────────────────
_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "settings.json"
)
with open(_SETTINGS_PATH, "r", encoding="utf-8") as _f:
    _SETTINGS = json.load(_f)

# Valid cache_mode choices
_CACHE_MODES = ["RAM + Disk", "Only to Disk"]


# ══════════════════════════════════════════════════════════════════════
#  Node class
# ══════════════════════════════════════════════════════════════════════

class SimpleGlobalVRAMCacheSaving:
    """Save the current VRAM state (all loaded models) to RAM + disk cache.

    If enough free RAM exists the data is first staged in protected CPU
    memory and the disk write happens in the background (non-blocking).
    Otherwise the data is written to disk directly from VRAM (blocking).
    """

    CATEGORY = "Simple Utility ⛏️/Global"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True  # always executes

    @classmethod
    def INPUT_TYPES(cls):
        settings = _SETTINGS.get("SimpleGlobalVRAMCacheSaving", {})
        return {
            "required": {
                "cache_name": (
                    "STRING",
                    {
                        "default": settings.get("default_cache_name", "VRAM_cache"),
                        "multiline": False,
                    },
                ),
                "cache_mode": (
                    _CACHE_MODES,
                    {
                        "default": settings.get("default_cache_mode", "RAM + Disk"),
                    },
                ),
            },
            "optional": {
                "anything": ("*",),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, cache_name, cache_mode, anything=None):
        if not cache_name or not cache_name.strip():
            return "Cache name cannot be empty."
        if cache_mode not in _CACHE_MODES:
            return f"Invalid cache_mode '{cache_mode}'. Must be one of {_CACHE_MODES}."
        return True

    # ── Main execution ────────────────────────────────────────
    def execute(
        self,
        cache_name: str,
        cache_mode: str = "RAM + Disk",
        anything: Any = None,
    ) -> Tuple[Any]:
        cache_name = cache_name.strip()
        t_start = time.perf_counter()

        # 1. Capture current VRAM state dict (zero-copy refs) ─
        state_dict = capture_vram_state_dict()

        if not state_dict:
            logger.warning(
                f"[VRAM-Cache-Save] No tensors found in VRAM for '{cache_name}'. "
                f"Nothing to save."
            )
            return (anything,)

        cache_size = get_total_vram_cache_size(state_dict)
        free_ram = get_free_ram_bytes()

        logger.info(
            f"[VRAM-Cache-Save] Cache size: {format_bytes(cache_size)}, "
            f"Free system RAM: {format_bytes(free_ram)} "
            f"({len(state_dict)} tensors)"
        )

        # 2. Choose branch ────────────────────────────────────
        use_ram = (cache_mode == "RAM + Disk") and (free_ram >= cache_size)

        if cache_mode == "RAM + Disk" and free_ram < cache_size:
            warnings.warn(
                f"[VRAM-Cache-Save] Not enough free RAM for '{cache_name}' in "
                f"RAM + Disk mode.  Need {format_bytes(cache_size)}, "
                f"have {format_bytes(free_ram)} free.  Falling back to Disk Only.",
                ResourceWarning,
                stacklevel=2,
            )

        if use_ram:
            self._ram_and_disk_branch(cache_name, state_dict, cache_size, free_ram)
        else:
            self._disk_only_branch(cache_name, state_dict, cache_size, free_ram)

        return (anything,)

    # ── RAM + Disk branch ─────────────────────────────────────
    def _ram_and_disk_branch(
        self,
        cache_name: str,
        state_dict: dict,
        cache_size: int,
        free_ram: int,
    ) -> None:
        margin = free_ram - cache_size
        if margin < 512 * 1024 * 1024:
            warnings.warn(
                f"[VRAM-Cache-Save] RAM headroom is only {format_bytes(margin)}. "
                f"Need {format_bytes(cache_size)} for RAM caching, "
                f"have {format_bytes(free_ram)} free. "
                f"Proceeding but system may become slow.",
                ResourceWarning,
                stacklevel=3,
            )

        # Step a – Release old RAM cache BEFORE transfer to avoid double RAM usage
        if ram_cache().exists(cache_name):
            disk_monitors().wait_for(cache_name)  # ensure disk save isn't reading it
            ram_cache().release(cache_name)
            gc.collect()

        # Step b – Bulk VRAM -> CPU transfer (single or chunked DMA)
        cpu_state_dict = bulk_vram_to_cpu(state_dict)

        # Step c – Store in RAM cache (no copy, already CPU)
        ram_cache().store(cache_name, cpu_state_dict)

        # Drop refs to the original VRAM tensors before cleanup
        del state_dict

        # Step d – Clean VRAM
        cleanup_current_vram()

        # Step e – Kick off background disk save (truly non-blocking).
        # We pass the RAM cache dict by reference — the background thread
        # only reads it and never mutates it, so no data race.
        ram_state = ram_cache().load(cache_name)
        disk_monitors().start_monitor(cache_name, ram_state)
        # *** Node returns here — no waiting on disk I/O ***

    # ── Disk Only branch ──────────────────────────────────────
    def _disk_only_branch(
        self,
        cache_name: str,
        state_dict: dict,
        cache_size: int,
        free_ram: int,
    ) -> None:
        logger.info(
            f"[VRAM-Cache-Save] Using Disk Only branch for '{cache_name}' "
            f"(need {format_bytes(cache_size)} RAM but only "
            f"{format_bytes(free_ram)} available)."
        )

        # Step a – Start background thread that reads directly from VRAM
        monitor = disk_monitors().start_monitor(cache_name, state_dict)

        # Step b – Wait until disk save is done (blocking)
        monitor.wait()
        if monitor.error:
            raise RuntimeError(
                f"[VRAM-Cache-Save] Disk save for '{cache_name}' failed: "
                f"{monitor.error}"
            ) from monitor.error

        # Step c – Clean VRAM after save completes
        del state_dict
        cleanup_current_vram()


# ══════════════════════════════════════════════════════════════════════
#  Registration
# ══════════════════════════════════════════════════════════════════════
NODE_CLASS_MAPPINGS = {
    "SimpleGlobalVRAMCacheSaving": SimpleGlobalVRAMCacheSaving,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleGlobalVRAMCacheSaving": "⛏️ Simple Global VRAM Cache Saving",
}
