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
    format_bytes,
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
            "required": {},
            "optional": {
                "anything": ("*",),
            },
        }

    # ── Main execution ────────────────────────────────────────
    def execute(self, anything: Any = None) -> Tuple[Any]:
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

        elapsed = time.perf_counter() - t_start
        logger.info(
            f"[VRAM-Cache-RAMClear] Done – {count} RAM cache(s) freed "
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
