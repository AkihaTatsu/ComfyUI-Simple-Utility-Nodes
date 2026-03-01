"""Shared utilities for VRAM cache saving, loading and clearing.

This module contains all reusable functions and classes used across
vram_cache_saving, vram_cache_loading, and vram_ram_cache_clearing modules.
"""

import atexit
import gc
import json as _json
import logging
import mmap
import os
import shutil
import struct as _struct
import threading
import time
import weakref
from typing import Any, Dict, List, Optional, Tuple

import psutil
import torch
from safetensors.torch import load_file as safetensors_load_file

logger = logging.getLogger("ComfyUI-VRAM-Cache")

# Save a duplicate of the stdout file descriptor at **import time**.
# This fd points to the real OS console and is immune to
# llama-cpp-python's ``suppress_stdout_stderr`` context manager, which
# uses ``os.dup2`` to redirect fd 1/2 to ``/dev/null`` during model
# loading (making ``print()`` and ``logging`` silent in that window).
_CONSOLE_FD = os.dup(1)


def _console_log(msg: str) -> None:
    """Write *msg* directly to the OS console.

    Bypasses Python's ``sys.stdout`` / ``sys.stderr`` entirely so the
    message always reaches the terminal — even when ``llama-cpp-python``
    (or any other C library) has temporarily redirected the standard
    file descriptors to ``/dev/null``.
    """
    try:
        os.write(_CONSOLE_FD, (msg + "\n").encode("utf-8", errors="replace"))
    except OSError:
        pass


# ──────────────────────────  Constants  ──────────────────────────
CACHE_DIR_NAME = "vram_cache_store"
SAFETENSORS_EXT = ".safetensors"

# Torch dtype → safetensors dtype-string (used by _write_safetensors)
_TORCH_TO_ST_DTYPE: Dict[torch.dtype, str] = {
    torch.bool:     "BOOL",
    torch.uint8:    "U8",
    torch.int8:     "I8",
    torch.int16:    "I16",
    torch.int32:    "I32",
    torch.int64:    "I64",
    torch.float16:  "F16",
    torch.bfloat16: "BF16",
    torch.float32:  "F32",
    torch.float64:  "F64",
}

# ──────────────────────────  Path helpers  ──────────────────────────

def _cache_directory_path() -> str:
    """Return the cache directory path WITHOUT creating it."""
    try:
        import folder_paths
        base = folder_paths.get_temp_directory()
    except Exception:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "temp")
    return os.path.join(base, CACHE_DIR_NAME)


def get_cache_directory() -> str:
    """Return (and create) the on-disk cache directory under ComfyUI/temp/."""
    cache_dir = _cache_directory_path()
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def get_cache_file_path(cache_name: str) -> str:
    """Return the full path for a cache file (safetensors format)."""
    safe_name = cache_name.replace(os.sep, "_").replace("/", "_").replace("\\", "_")
    return os.path.join(get_cache_directory(), f"{safe_name}{SAFETENSORS_EXT}")


# ──────────────────────────  Memory helpers  ──────────────────────────

def get_free_ram_bytes() -> int:
    """Return available system RAM in bytes."""
    return psutil.virtual_memory().available


def get_total_vram_cache_size(state_dict: Dict[str, torch.Tensor]) -> int:
    """Calculate total bytes of a state dict (on any device)."""
    total = 0
    for t in state_dict.values():
        total += t.nelement() * t.element_size()
    return total


def format_bytes(n: int) -> str:
    """Human-readable byte size."""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.2f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024 ** 2:.2f} MB"
    else:
        return f"{n / 1024 ** 3:.2f} GB"


# ──────────────────────────  VRAM cleanup  ──────────────────────────

def cleanup_current_vram() -> None:
    """Absolutely clean up VRAM used by the current ComfyUI instance.

    Uses ComfyUI's own model_management API so that we do NOT affect other
    PyTorch processes or unrelated VRAM allocations.
    """
    try:
        from comfy.model_management import (
            unload_all_models,
            soft_empty_cache,
        )
        unload_all_models()
        soft_empty_cache(force=True)
    except ImportError:
        logger.warning("[VRAM-Cache] comfy.model_management not available; "
                       "falling back to torch.cuda.empty_cache()")
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    gc.collect()


# ──────────────────────────  State dict capture  ──────────────────────────

def capture_vram_state_dict() -> Dict[str, torch.Tensor]:
    """Capture a *flat* state dict of ALL models currently loaded on GPU.

    Each key is ``<model_index>_<ClassName>/<param_path>`` so that different
    models never collide.

    IMPORTANT: We iterate ``named_parameters()`` + ``named_buffers()``
    directly instead of calling ``state_dict()`` which would implicitly
    ``.detach().clone()`` every tensor, doubling VRAM usage.  The returned
    dict holds **live references** to the model tensors — no VRAM copy.
    """
    try:
        from comfy.model_management import current_loaded_models
    except ImportError:
        logger.warning("[VRAM-Cache] Cannot import current_loaded_models; returning empty dict")
        return {}

    state: Dict[str, torch.Tensor] = {}
    skipped_cpu = 0
    model_count = 0
    for idx, loaded in enumerate(current_loaded_models):
        model_patcher = loaded.model
        if model_patcher is None:
            continue
        nn_model = model_patcher.model
        if nn_model is None:
            continue
        model_name = nn_model.__class__.__name__
        seen: set = set()
        model_had_gpu = False
        for name, param in nn_model.named_parameters():
            if param.data.device.type == "cpu":
                # Tensor was already unloaded from VRAM by a previous cleanup;
                # skip it — we're capturing *VRAM* state, not CPU state.
                skipped_cpu += 1
                seen.add(name)
                continue
            key = f"{idx}_{model_name}/{name}"
            state[key] = param.data          # direct storage reference
            seen.add(name)
            model_had_gpu = True
        for name, buf in nn_model.named_buffers():
            if name in seen:
                continue
            if buf.device.type == "cpu":
                skipped_cpu += 1
                continue
            key = f"{idx}_{model_name}/{name}"
            state[key] = buf
            seen.add(name)
            model_had_gpu = True
        if model_had_gpu:
            model_count += 1

    if skipped_cpu:
        logger.debug(
            f"[VRAM-Cache] Skipped {skipped_cpu} already-CPU tensor(s) "
            f"(unloaded from VRAM by a previous run)."
        )
    if not state:
        logger.warning("[VRAM-Cache] No CUDA tensors found in VRAM to cache.")
    else:
        logger.info(f"[VRAM-Cache] Captured {len(state)} tensors from "
                     f"{model_count} loaded model(s) (zero-copy refs).")
    return state


# ──────────────────────────  Bulk VRAM → CPU transfer  ──────────────────────────

def bulk_vram_to_cpu(
    state_dict: Dict[str, torch.Tensor],
) -> Dict[str, torch.Tensor]:
    """Move an entire state dict from GPU to CPU RAM in a single DMA transfer.

    Strategy: flatten every tensor into raw uint8 bytes on GPU, ``torch.cat``
    them into one contiguous buffer, perform **one** GPU -> CPU copy, then split
    the CPU buffer back into individual tensors.

    This eliminates the per-tensor CUDA-sync overhead that dominates when
    there are thousands of small tensors.

    If VRAM headroom is too tight for the temporary concat buffer, falls back
    to a chunked (but still batched) transfer.
    """
    if not state_dict:
        return {}

    # Fast path: already CPU
    if all(v.device.type == "cpu" for v in state_dict.values()):
        return {k: v.detach().contiguous() for k, v in state_dict.items()}

    keys = list(state_dict.keys())
    tensors = [state_dict[k] for k in keys]

    total_bytes = sum(t.nelement() * t.element_size() for t in tensors)

    # Check whether we can afford the concat buffer in VRAM
    try:
        free_vram = torch.cuda.mem_get_info()[0] if torch.cuda.is_available() else 0
    except Exception:
        free_vram = 0

    if free_vram > total_bytes * 1.15:  # 15 % safety margin
        return _bulk_concat_transfer(keys, tensors, total_bytes)
    else:
        logger.info(f"[VRAM-Cache] Not enough GPU VRAM headroom for single-shot "
                     f"concat ({format_bytes(free_vram)} free GPU VRAM vs "
                     f"{format_bytes(total_bytes)} needed).  "
                     f"Using chunked GPU -> CPU transfer instead (no data loss).")
        return _chunked_transfer(keys, tensors, total_bytes)


def _bulk_concat_transfer(
    keys: List[str],
    tensors: List[torch.Tensor],
    total_bytes: int,
) -> Dict[str, torch.Tensor]:
    """Concat all tensors as raw bytes → single DMA → split on CPU.

    CPU tensors (already off VRAM) are passed through directly without
    touching CUDA, so a mixed-device state dict never causes a crash.
    """
    logger.info(f"[VRAM-Cache] Bulk concat VRAM -> CPU: {format_bytes(total_bytes)}, "
                 f"{len(tensors)} tensors …")
    t0 = time.perf_counter()

    # Separate CPU tensors from GPU tensors
    gpu_keys: List[str] = []
    gpu_tensors: List[torch.Tensor] = []
    result: Dict[str, torch.Tensor] = {}

    for key, t in zip(keys, tensors):
        if t.device.type == "cpu":
            result[key] = t.detach().contiguous().clone()
        else:
            gpu_tensors.append(t)
            gpu_keys.append(key)

    if gpu_tensors:
        # Record metadata for reconstruction
        meta: List[Tuple[torch.dtype, torch.Size, int]] = []
        byte_views: List[torch.Tensor] = []

        for t in gpu_tensors:
            td = t.detach().contiguous()
            nbytes = td.nelement() * td.element_size()
            meta.append((td.dtype, td.shape, nbytes))
            bv = torch.as_tensor(td.untyped_storage(), dtype=torch.uint8, device=td.device)[:nbytes]
            byte_views.append(bv)

        # One big cat on GPU → single DMA → split on CPU
        big_gpu = torch.cat(byte_views)
        del byte_views
        big_cpu = big_gpu.cpu()
        del big_gpu
        if torch.cuda.is_available():
            torch.cuda.synchronize()

        offset = 0
        for key, (dtype, shape, nbytes) in zip(gpu_keys, meta):
            byte_slice = big_cpu[offset:offset + nbytes]
            result[key] = byte_slice.view(dtype).reshape(shape).clone()
            offset += nbytes
        del big_cpu

    elapsed = time.perf_counter() - t0
    speed = total_bytes / max(elapsed, 1e-9)
    logger.info(f"[VRAM-Cache] Bulk concat done in {elapsed:.2f}s "
                 f"({format_bytes(int(speed))}/s).")
    return result


def _chunked_transfer(
    keys: List[str],
    tensors: List[torch.Tensor],
    total_bytes: int,
    chunk_target: int = 512 * 1024 * 1024,  # 512 MB per chunk
) -> Dict[str, torch.Tensor]:
    """Transfer tensors CPU-ward in ~512 MB chunks to limit VRAM overhead."""
    logger.info(f"[VRAM-Cache] Chunked VRAM -> CPU: {format_bytes(total_bytes)}, "
                 f"{len(tensors)} tensors in ~{format_bytes(chunk_target)} chunks …")
    t0 = time.perf_counter()

    result: Dict[str, torch.Tensor] = {}
    chunk_keys: List[str] = []
    chunk_tensors: List[torch.Tensor] = []
    chunk_bytes = 0

    def _flush():
        nonlocal chunk_keys, chunk_tensors, chunk_bytes
        if not chunk_tensors:
            return

        # Separate CPU-only tensors — they don't need a GPU cat
        gpu_chunk_keys: List[str] = []
        gpu_chunk_tensors: List[torch.Tensor] = []
        for ck, t in zip(chunk_keys, chunk_tensors):
            if t.device.type == "cpu":
                result[ck] = t.detach().contiguous().clone()
            else:
                gpu_chunk_keys.append(ck)
                gpu_chunk_tensors.append(t)

        if gpu_chunk_tensors:
            # Build byte views for GPU tensors only
            meta: List[Tuple[torch.dtype, torch.Size, int]] = []
            byte_views: List[torch.Tensor] = []
            for t in gpu_chunk_tensors:
                td = t.detach().contiguous()
                nb = td.nelement() * td.element_size()
                meta.append((td.dtype, td.shape, nb))
                bv = torch.as_tensor(td.untyped_storage(), dtype=torch.uint8, device=td.device)[:nb]
                byte_views.append(bv)

            cat_gpu = torch.cat(byte_views)
            del byte_views
            cat_cpu = cat_gpu.cpu()
            del cat_gpu

            offset = 0
            for ck, (dtype, shape, nb) in zip(gpu_chunk_keys, meta):
                byte_slice = cat_cpu[offset:offset + nb]
                result[ck] = byte_slice.view(dtype).reshape(shape).clone()
                offset += nb
            del cat_cpu

        chunk_keys.clear()
        chunk_tensors.clear()
        chunk_bytes = 0

    for k, t in zip(keys, tensors):
        tb = t.nelement() * t.element_size()
        if chunk_bytes + tb > chunk_target and chunk_tensors:
            _flush()
        chunk_keys.append(k)
        chunk_tensors.append(t)
        chunk_bytes += tb

    _flush()

    if torch.cuda.is_available():
        torch.cuda.synchronize()

    elapsed = time.perf_counter() - t0
    speed = total_bytes / max(elapsed, 1e-9)
    logger.info(f"[VRAM-Cache] Chunked transfer done in {elapsed:.2f}s "
                 f"({format_bytes(int(speed))}/s).")
    return result


# ──────────────────────────  RAM cache store  ──────────────────────────

class _RAMCacheEntry:
    """Holds a CPU state dict with an mmap lifecycle guard.

    A **single** 4-byte mmap (not one per tensor!) acts as an OS-level
    resource sentinel.  ``weakref.finalize`` ensures cleanup even on
    abnormal process exit — the OS reclaims the mmap pages automatically.

    Expects an **already-on-CPU** state dict (produced by ``bulk_vram_to_cpu``).
    No device transfer is done here.
    """

    def __init__(self, cpu_state_dict: Dict[str, torch.Tensor]):
        self.state_dict: Dict[str, torch.Tensor] = cpu_state_dict
        self._lock = threading.Lock()

        # Single mmap guard for the whole entry
        self._mmap_guard = mmap.mmap(-1, 4, access=mmap.ACCESS_WRITE)
        self._mmap_guard.write(b'\x01\x02\x03\x04')
        self._mmap_guard.seek(0)

        # weakref destructor — fires on GC or atexit
        guard = self._mmap_guard
        weakref.finalize(self, lambda: _safe_close(guard))

    def get_state_dict(self) -> Dict[str, torch.Tensor]:
        """Return the read-only CPU state dict (references, no copies)."""
        return self.state_dict

    def release(self):
        """Explicitly release all resources."""
        with self._lock:
            _safe_close(self._mmap_guard)
            self.state_dict.clear()


def _safe_close(mm):
    """Close an mmap ignoring errors."""
    try:
        mm.close()
    except Exception:
        pass


class RAMCacheManager:
    """Thread-safe singleton manager for named RAM cache entries."""

    _instance: Optional["RAMCacheManager"] = None
    _init_lock = threading.Lock()

    def __new__(cls):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._caches: Dict[str, _RAMCacheEntry] = {}
                cls._instance._lock = threading.Lock()
            return cls._instance

    # ── public API ────────────────────────────────────────────
    def store(self, name: str, cpu_state_dict: Dict[str, torch.Tensor]) -> None:
        """Store (or overwrite) a named RAM cache.

        Expects an **already-CPU** state dict produced by ``bulk_vram_to_cpu``.
        No device transfer is performed here.
        """
        with self._lock:
            if name in self._caches:
                self._caches[name].release()
            entry = _RAMCacheEntry(cpu_state_dict)
            self._caches[name] = entry
            size = get_total_vram_cache_size(entry.state_dict)
            logger.info(f"[VRAM-Cache] RAM cache '{name}' stored – "
                        f"{len(entry.state_dict)} tensors, {format_bytes(size)}.")

    def load(self, name: str) -> Dict[str, torch.Tensor]:
        """Return the read-only state dict for *name* (raises KeyError if absent)."""
        with self._lock:
            if name not in self._caches:
                raise KeyError(f"RAM cache '{name}' not found.")
            return self._caches[name].get_state_dict()

    def exists(self, name: str) -> bool:
        with self._lock:
            return name in self._caches

    def clear_all(self) -> int:
        """Release every RAM cache. Returns the number of entries cleared."""
        with self._lock:
            count = len(self._caches)
            for entry in self._caches.values():
                entry.release()
            self._caches.clear()
            gc.collect()
            logger.info(f"[VRAM-Cache] Cleared {count} RAM cache(s).")
            return count

    def release(self, name: str) -> None:
        """Release a single named RAM cache entry and remove it from the registry."""
        with self._lock:
            entry = self._caches.pop(name, None)
        if entry is not None:
            entry.release()

    def names(self) -> List[str]:
        with self._lock:
            return list(self._caches.keys())


# Module-level convenience accessor
def ram_cache() -> RAMCacheManager:
    return RAMCacheManager()


# ──────────────────────────  Disk I/O  ──────────────────────────


def _write_safetensors(
    cpu_state_dict: Dict[str, torch.Tensor],
    path: str,
) -> None:
    """Write *cpu_state_dict* in safetensors binary format using Python I/O.

    Unlike ``safetensors.torch.save_file`` (a Rust/PyO3 C extension), every
    ``file.write()`` call here goes through Python's ``io.BufferedWriter``
    which **releases the GIL** during the underlying OS write syscall.

    This is critical for background-thread saves: the main ComfyUI thread
    can continue executing the next node while disk I/O proceeds in
    parallel, instead of being blocked by GIL contention for the entire
    duration of the write.

    The output is 100 % compatible with ``safetensors.torch.load_file``.
    """
    ordered_keys = sorted(cpu_state_dict.keys())

    # ── Build header and collect zero-copy numpy views ──────────
    header: Dict[str, Any] = {}
    data_views: list = []
    offset = 0

    for key in ordered_keys:
        t = cpu_state_dict[key]
        nbytes = t.nelement() * t.element_size()
        dt = _TORCH_TO_ST_DTYPE.get(t.dtype)
        if dt is None:
            raise ValueError(
                f"Unsupported dtype {t.dtype} for safetensors serialisation"
            )
        header[key] = {
            "dtype": dt,
            "shape": list(t.shape),
            "data_offsets": [offset, offset + nbytes],
        }
        if nbytes > 0:
            # Account for possible storage offset (views / slices)
            so = t.storage_offset() * t.element_size()
            raw = torch.as_tensor(
                t.untyped_storage(), dtype=torch.uint8
            )[so : so + nbytes]
            data_views.append(raw.numpy())       # zero-copy view
        else:
            data_views.append(b"")
        offset += nbytes

    # ── Serialise header JSON (space-padded to 8-byte boundary) ─
    header_bytes = _json.dumps(header, separators=(",", ":")).encode("utf-8")
    pad = (8 - len(header_bytes) % 8) % 8
    if pad:
        header_bytes += b" " * pad

    # ── Write file — each write() releases the GIL during OS I/O ─
    with open(path, "wb", buffering=8 * 1024 * 1024) as f:
        f.write(_struct.pack("<Q", len(header_bytes)))
        f.write(header_bytes)
        for view in data_views:
            f.write(view)


def save_state_dict_to_disk(
    state_dict: Dict[str, torch.Tensor],
    cache_name: str,
) -> Tuple[str, float, int]:
    """Save *state_dict* to disk using safetensors (fastest, no pickle).

    All tensors are detached and moved to CPU contiguously before saving.
    Returns ``(file_path, elapsed_seconds, bytes_written)``.

    Safetensors writes raw tensor data with minimal framing – close to
    the theoretical memcpy speed.
    """
    path = get_cache_file_path(cache_name)
    # safetensors requires all tensors on CPU & contiguous
    cpu_dict: Dict[str, torch.Tensor] = {}
    for k, v in state_dict.items():
        t = v.detach()
        if t.device.type != "cpu":
            t = t.cpu()
        if not t.is_contiguous():
            t = t.contiguous()
        cpu_dict[k] = t

    t0 = time.perf_counter()
    _write_safetensors(cpu_dict, path)
    elapsed = time.perf_counter() - t0
    file_size = os.path.getsize(path)

    logger.info(
        f"[VRAM-Cache] Disk save complete for '{cache_name}': "
        f"{format_bytes(file_size)} written to \"{path}\"."
    )
    return path, elapsed, file_size


def load_state_dict_from_disk(
    cache_name: str,
    device: str = "cpu",
) -> Dict[str, torch.Tensor]:
    """Load a cache from disk directly to *device*.

    Uses safetensors ``load_file`` which memory-maps the file for very fast
    loading, especially into CPU.  For GPU loading, safetensors still avoids
    a full Python-level deserialization.
    """
    path = get_cache_file_path(cache_name)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"[VRAM-Cache] Disk cache file not found: {path}"
        )
    t0 = time.perf_counter()
    state = safetensors_load_file(path, device=device)
    elapsed = time.perf_counter() - t0
    file_size = os.path.getsize(path)
    logger.info(
        f"[VRAM-Cache] Disk load complete for '{cache_name}': "
        f"{format_bytes(file_size)} from {path} in {elapsed:.2f}s "
        f"({format_bytes(int(file_size / max(elapsed, 1e-9)))}/s) → {device}."
    )
    return state


def disk_cache_exists(cache_name: str) -> bool:
    return os.path.isfile(get_cache_file_path(cache_name))


# ──────────────────────────  Monitor subprocess (thread)  ──────────────────────────

class _ToDiskMonitor(threading.Thread):
    """Background thread that saves a state_dict to disk.

    Terminology note: called "subprocess" in the algorithm description but
    implemented as a *daemon thread* because:
    1. Python multiprocessing on Windows uses 'spawn' – that would require
       serialising large GPU tensors across process boundaries (very slow/impossible).
    2. A daemon thread shares the same address space, can read VRAM or RAM
       tensors by reference, and is cleaned up automatically if the process dies.

    The thread sets an ``Event`` when saving is complete so that other code
    can wait on it.
    """

    def __init__(self, cache_name: str, state_dict: Dict[str, torch.Tensor]):
        super().__init__(daemon=True, name=f"ToDiskMonitor-{cache_name}")
        self.cache_name = cache_name
        self.state_dict = state_dict
        self.done_event = threading.Event()
        self.error: Optional[Exception] = None
        self._path: Optional[str] = None
        self._elapsed: float = 0.0
        self._file_size: int = 0

    def run(self):
        try:
            self._path, self._elapsed, self._file_size = save_state_dict_to_disk(
                self.state_dict, self.cache_name
            )
            # Write directly to the saved console fd — immune to
            # llama-cpp-python's suppress_stdout_stderr os.dup2 redirect.
            _console_log(
                f"[VRAM-Cache] Disk save complete for '{self.cache_name}': "
                f"{format_bytes(self._file_size)} in {self._elapsed:.2f}s "
                f"({format_bytes(int(self._file_size / max(self._elapsed, 1e-9)))}/s)."
            )
        except Exception as e:
            self.error = e
            _console_log(
                f"[VRAM-Cache] Background disk save FAILED for "
                f"'{self.cache_name}': {e}"
            )
            logger.error(
                f"[VRAM-Cache] Background disk save FAILED for "
                f"'{self.cache_name}': {e}"
            )
        finally:
            # Drop reference so tensors can be GC'd if no one else holds them
            self.state_dict = {}
            self.done_event.set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Block until saving is done.  Returns True if completed."""
        return self.done_event.wait(timeout=timeout)


class ToDiskMonitorManager:
    """Track all active to-disk monitor threads by name."""

    _instance: Optional["ToDiskMonitorManager"] = None
    _init_lock = threading.Lock()

    def __new__(cls):
        with cls._init_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._monitors: Dict[str, _ToDiskMonitor] = {}
                cls._instance._lock = threading.Lock()
            return cls._instance

    def start_monitor(
        self, cache_name: str, state_dict: Dict[str, torch.Tensor]
    ) -> _ToDiskMonitor:
        """Start (or replace) a background disk-save thread for *cache_name*."""
        with self._lock:
            # If there's already a monitor with this name, wait for it first
            existing = self._monitors.get(cache_name)
            if existing is not None and existing.is_alive():
                existing.wait()
            monitor = _ToDiskMonitor(cache_name, state_dict)
            self._monitors[cache_name] = monitor
            monitor.start()
            return monitor

    def get_monitor(self, cache_name: str) -> Optional[_ToDiskMonitor]:
        with self._lock:
            return self._monitors.get(cache_name)

    def wait_for(self, cache_name: str) -> None:
        """Wait for a specific monitor to finish (no-op if none exists)."""
        with self._lock:
            m = self._monitors.get(cache_name)
        if m is not None:
            m.wait()
            if m.error:
                raise RuntimeError(
                    f"Background disk save for '{cache_name}' failed: {m.error}"
                ) from m.error

    def wait_for_all(self) -> None:
        """Wait for ALL active monitors to finish."""
        with self._lock:
            monitors = list(self._monitors.values())
        for m in monitors:
            m.wait()

    def has_active(self) -> bool:
        """Return True if any monitor thread is still alive."""
        with self._lock:
            return any(m.is_alive() for m in self._monitors.values())

    def cleanup(self) -> None:
        """Remove finished monitors from the registry."""
        with self._lock:
            finished = [k for k, v in self._monitors.items()
                        if not v.is_alive()]
            for k in finished:
                del self._monitors[k]


# Module-level convenience
def disk_monitors() -> ToDiskMonitorManager:
    return ToDiskMonitorManager()


# ──────────────────────────  Startup / shutdown lifecycle  ──────────────────────────

def _startup_cleanup() -> None:
    """Wipe the disk cache directory clean at startup.

    ComfyUI already calls ``shutil.rmtree(temp_dir)`` before importing
    custom nodes, so this is normally a no-op.  It runs anyway as a
    safety net for non-standard launches or in-process restarts where
    the temp directory was not wiped first.

    Uses ``_cache_directory_path()`` (not ``get_cache_directory()``) so
    that the folder is not immediately recreated by the makedirs inside
    that function.
    """
    try:
        cache_dir = _cache_directory_path()
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
    except Exception:
        pass


def _shutdown_cleanup() -> None:
    """atexit handler: wait for active disk saves, free RAM caches, delete cache dir.

    This runs before ComfyUI's own ``cleanup_temp()`` so that any still-running
    background disk-save threads have a chance to finish (and release their file
    handles) before the directory is deleted.  Without this wait, ``shutil.rmtree``
    could race with an active write and leave a corrupt or partially-deleted tree.

    Uses ``_cache_directory_path()`` (not ``get_cache_directory()``) so
    that the folder is not immediately recreated by the makedirs inside
    that function.
    """
    try:
        monitors = ToDiskMonitorManager()
        if monitors.has_active():
            _console_log("[VRAM-Cache] Shutdown: waiting for active disk saves to finish …")
            monitors.wait_for_all()
    except Exception:
        pass
    try:
        RAMCacheManager().clear_all()
    except Exception:
        pass
    try:
        cache_dir = _cache_directory_path()
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir, ignore_errors=True)
    except Exception:
        pass


atexit.register(_shutdown_cleanup)
_startup_cleanup()
