"""VRAM Cache RAM Clearing node for ComfyUI.

Algorithm
─────────
1. Wait for ALL active to-disk monitor threads to finish.
2. Release every RAM cache entry created by VRAM Cache Saving.
   (Disk caches are NOT touched and remain available.)
"""

import logging
import time
from typing import Any, Tuple

from .utils import (
    disk_monitors,
    empty_cache_markers,
    format_bytes,
    legacy_patcher_cache,
    ram_cache,
)

logger = logging.getLogger("ComfyUI-VRAM-Cache")


# ══════════════════════════════════════════════════════════════════════
#  Node class
# ══════════════════════════════════════════════════════════════════════

class SimpleGlobalVRAMCacheRAMClearing:
    """Clear ALL VRAM caches currently held in system RAM.

    Waits for every background disk-save thread to finish first (so no
    in-flight data is lost), then releases all protected RAM cache entries.
    Disk caches on disk are unaffected.
    """

    CATEGORY = "Simple Utility ⛏️/Global"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True  # always executes

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "anything": ("*",),
            },
        }

    # ── Main execution ────────────────────────────────────────
    def execute(self, anything: Any = None) -> Tuple[Any]:  # default kept for internal safety only
        t_start = time.perf_counter()

        # Step 1 – wait for all background disk-save threads ───
        if disk_monitors().has_active():
            logger.info(
                "[VRAM-Cache-RAMClear] Waiting for background disk saves "
                "to finish before clearing RAM …"
            )
            disk_monitors().wait_for_all()

        # Step 2 – clear all RAM caches ────────────────────────
        names = ram_cache().names()
        if names:
            logger.info(
                f"[VRAM-Cache-RAMClear] Clearing {len(names)} RAM cache(s): "
                f"{names}"
            )
        count = ram_cache().clear_all()
        legacy_names = legacy_patcher_cache().names()
        if legacy_names:
            logger.info(
                f"[VRAM-Cache-RAMClear] Clearing {len(legacy_names)} "
                f"legacy RAM cache(s): {legacy_names}"
            )
        legacy_count = legacy_patcher_cache().clear_all()
        empty_names = empty_cache_markers().names()
        if empty_names:
            logger.info(
                f"[VRAM-Cache-RAMClear] Clearing {len(empty_names)} "
                f"empty RAM marker(s): {empty_names}"
            )
        empty_count = empty_cache_markers().clear_all()

        elapsed = time.perf_counter() - t_start
        logger.info(
            f"[VRAM-Cache-RAMClear] Done – {count} tensor RAM cache(s) and "
            f"{legacy_count} legacy RAM cache(s), {empty_count} empty marker(s) freed "
            f"in {elapsed:.2f}s."
        )
        return (anything,)


# ══════════════════════════════════════════════════════════════════════
#  Registration
# ══════════════════════════════════════════════════════════════════════
NODE_CLASS_MAPPINGS = {
    "SimpleGlobalVRAMCacheRAMClearing": SimpleGlobalVRAMCacheRAMClearing,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleGlobalVRAMCacheRAMClearing": "⛏️ Simple Global VRAM Cache RAM Clearing",
}
