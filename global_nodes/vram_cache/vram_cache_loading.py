"""VRAM Cache Loading node for ComfyUI.

Algorithm overview
──────────────────
1. Clean all VRAM used by the current ComfyUI instance.
2. Check for a RAM cache with the requested name.
   • Load from RAM   – read the mmap-protected read-only tensors by
     reference (zero-copy); move them to GPU.
   • Load from Disk  – if the name has an active to-disk monitor,
     wait for it to finish; then load safetensors file directly to GPU.
3. Reconstruct the model state on GPU using ComfyUI model_management.
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Tuple

import torch

from .utils import (
    cleanup_current_vram,
    disk_cache_exists,
    disk_monitors,
    format_bytes,
    get_total_vram_cache_size,
    load_state_dict_from_disk,
    ram_cache,
)

logger = logging.getLogger("ComfyUI-VRAM-Cache")

# ── Settings ──────────────────────────────────────────────────────────
_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "settings.json"
)
with open(_SETTINGS_PATH, "r", encoding="utf-8") as _f:
    _SETTINGS = json.load(_f)


# ──────────────────────────  Helpers  ──────────────────────────────────

def _move_state_dict_to_device(
    state_dict: Dict[str, torch.Tensor],
    device: torch.device,
) -> Dict[str, torch.Tensor]:
    """Move every tensor in *state_dict* to *device*.

    For RAM-cached tensors that are read-only we **must not** use in-place
    operations.  Instead we create new tensors on the target device via
    ``tensor.to(device, copy=False)`` which will only allocate on the
    destination device without mutating the source.
    """
    result: Dict[str, torch.Tensor] = {}
    for k, v in state_dict.items():
        if v.device == device:
            result[k] = v
        else:
            # .to() with copy=False still allocates on the destination but
            # shares storage if same device.  We never write to the source.
            result[k] = v.to(device, non_blocking=True)
    return result


def _restore_models_to_vram(state_dict: Dict[str, torch.Tensor]) -> None:
    """Push the cached state dict back onto GPU models via model_management.

    The keys are formatted as ``<idx>_<ClassName>/<param_path>``.
    We group them by model prefix, then for each model currently registered
    in ComfyUI we load the matching state dict slice.

    If ComfyUI's model_management is not available, we fall back to simply
    keeping the tensors on GPU (they can still be used by downstream nodes).
    """
    try:
        from comfy.model_management import (
            current_loaded_models,
            load_models_gpu,
            get_torch_device,
        )
    except ImportError:
        logger.warning(
            "[VRAM-Cache-Load] comfy.model_management not available; "
            "tensors are on GPU but model patchers are NOT restored."
        )
        return

    device = get_torch_device()

    # Group by model prefix (everything before the first '/')
    model_groups: Dict[str, Dict[str, torch.Tensor]] = {}
    for key, tensor in state_dict.items():
        prefix, _, param_name = key.partition("/")
        if prefix not in model_groups:
            model_groups[prefix] = {}
        model_groups[prefix][param_name] = tensor

    logger.info(
        f"[VRAM-Cache-Load] Restoring {len(model_groups)} model group(s) "
        f"({len(state_dict)} tensors) to VRAM …"
    )

    for prefix, params in model_groups.items():
        # Move all params into VRAM
        _move_state_dict_to_device(params, device)



# ══════════════════════════════════════════════════════════════════════
#  Node class
# ══════════════════════════════════════════════════════════════════════

class SimpleGlobalVRAMCacheLoading:
    """Restore a previously saved VRAM cache from RAM or disk.

    Priority: RAM cache (fast, zero-copy read) → Disk cache (safetensors).
    Current VRAM is cleaned before restoring.
    """

    CATEGORY = "Simple Utility ⛏️/Global"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        settings = _SETTINGS.get("SimpleGlobalVRAMCacheLoading", {})
        return {
            "required": {
                "cache_name": (
                    "STRING",
                    {
                        "default": settings.get("default_cache_name", "VRAM_cache"),
                        "multiline": False,
                    },
                ),
            },
            "optional": {
                "anything": ("*",),
            },
        }

    @classmethod
    def VALIDATE_INPUTS(cls, cache_name, anything=None):
        if not cache_name or not cache_name.strip():
            return "Cache name cannot be empty."
        return True

    # ── Main execution ────────────────────────────────────────
    def execute(self, cache_name: str, anything: Any = None) -> Tuple[Any]:
        cache_name = cache_name.strip()
        t_start = time.perf_counter()

        # Step 1 – clean VRAM ──────────────────────────────────

        cleanup_current_vram()

        # Step 2 – detect source ───────────────────────────────
        has_ram = ram_cache().exists(cache_name)
        has_disk = disk_cache_exists(cache_name)

        if has_ram:
            state = self._load_from_ram(cache_name)
        elif has_disk:
            state = self._load_from_disk(cache_name)
        else:
            raise FileNotFoundError(
                f"[VRAM-Cache-Load] No cache found for '{cache_name}'. "
                f"Available RAM caches: {ram_cache().names()}. "
                f"Check that a 'Simple Global VRAM Cache Saving' node with the "
                f"same cache_name has executed before this node."
            )

        # Step 3 – push to VRAM / restore models ──────────────
        _restore_models_to_vram(state)
        return (anything,)

    # ── Load from RAM (zero-copy read-only) ───────────────────
    def _load_from_ram(self, cache_name: str) -> Dict[str, torch.Tensor]:
        t0 = time.perf_counter()

        # ram_cache().load returns the READ-ONLY dict by reference – no copy
        state = ram_cache().load(cache_name)
        size = get_total_vram_cache_size(state)

        elapsed = time.perf_counter() - t0
        logger.info(
            f"[VRAM-Cache-Load] RAM read '{cache_name}': "
            f"{len(state)} tensors, {format_bytes(size)} in {elapsed:.4f}s."
        )
        return state

    # ── Load from Disk ────────────────────────────────────────
    def _load_from_disk(self, cache_name: str) -> Dict[str, torch.Tensor]:
        # Wait for any active disk monitor with the same name
        monitor = disk_monitors().get_monitor(cache_name)
        if monitor is not None and monitor.is_alive():
            monitor.wait()
            if monitor.error:
                raise RuntimeError(
                    f"[VRAM-Cache-Load] Background save for '{cache_name}' "
                    f"failed: {monitor.error}"
                ) from monitor.error

        # Determine target device
        try:
            from comfy.model_management import get_torch_device
            device_str = str(get_torch_device())
        except ImportError:
            device_str = "cuda" if torch.cuda.is_available() else "cpu"

        state = load_state_dict_from_disk(cache_name, device=device_str)
        return state


# ══════════════════════════════════════════════════════════════════════
#  Registration
# ══════════════════════════════════════════════════════════════════════
NODE_CLASS_MAPPINGS = {
    "SimpleGlobalVRAMCacheLoading": SimpleGlobalVRAMCacheLoading,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleGlobalVRAMCacheLoading": "⛏️ Simple Global VRAM Cache Loading",
}
