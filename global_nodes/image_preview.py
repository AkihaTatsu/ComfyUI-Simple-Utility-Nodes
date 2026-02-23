"""Global Image Preview node for ComfyUI.

This module provides a node that monitors ALL nodes producing temporary/preview/saved
images and automatically syncs them for display — no connections needed.

Architecture:
- The front-end JS extension does the heavy lifting: it globally listens to
  ``executed`` WebSocket events (which carry the ``{images: [...]}`` payload
  produced by PreviewImage / SaveImage / etc.) **and** ``b_preview`` binary
  frames (the step-by-step latent previews produced during KSampler runs).
- A pair of HTTP routes on the server side allow the standalone fullscreen
  viewer page to:
    1. Fetch the latest image metadata via ``GET /simple_utility/global_image_preview/latest``
    2. Load the viewer HTML via ``GET /simple_utility/global_image_preview/viewer``
- The backend also hooks into ``PromptServer.send_sync`` so that it can record
  every ``executed`` event's image list server-side, enabling the ``/latest``
  API to work even for the standalone viewer page.
"""

import json
import os
import threading
from typing import Dict, List

# Path to persist the last user prompt across server restarts.
_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", ".cache")
_PERSIST_PATH = os.path.normpath(os.path.join(_PERSIST_DIR, "last_prompt.json"))

# ---------------------------------------------------------------------------
# Server-side latest-image tracker
# (Populated by hooking PromptServer.send_sync — see _install_server_hook)
# ---------------------------------------------------------------------------

_latest_images: List[Dict[str, str]] = []
_latest_images_lock = threading.Lock()
_latest_images_counter: int = 0  # bumped each time new executed images arrive
_latest_preview_blob: bytes | None = None
_latest_preview_lock = threading.Lock()
_latest_preview_counter: int = 0  # bumped each time a new blob arrives


def _set_latest_images(images: List[Dict[str, str]]) -> None:
    global _latest_images_counter
    with _latest_images_lock:
        _latest_images.clear()
        _latest_images.extend(images)
        _latest_images_counter += 1


def get_latest_images() -> tuple[List[Dict[str, str]], int]:
    with _latest_images_lock:
        return list(_latest_images), _latest_images_counter


def _set_latest_preview_blob(blob: bytes) -> None:
    global _latest_preview_blob, _latest_preview_counter
    with _latest_preview_lock:
        _latest_preview_blob = blob
        _latest_preview_counter += 1


def get_latest_preview_blob() -> tuple[bytes | None, int]:
    with _latest_preview_lock:
        return _latest_preview_blob, _latest_preview_counter


# ---------------------------------------------------------------------------
# Workflow execution status tracker
# ---------------------------------------------------------------------------

_workflow_status_lock = threading.Lock()
_workflow_running: bool = False
_current_node_id: str | None = None
_current_node_class: str | None = None
_current_prompt_id: str | None = None
_user_prompt: dict | None = None       # original user prompt, NEVER overwritten by reruns
_user_extra_data: dict | None = None

# Guard: True while any rerun (same or new) is in-flight so that
# _patched_put does not overwrite _user_prompt with rerun data.
_rerun_in_progress: bool = False

# Tracks the last successfully queued rerun_id for per-tab confirmation.
_last_rerun_id: str | None = None

# Tracks the last successfully processed interrupt_id for per-tab confirmation.
_last_interrupt_id: str | None = None


def _set_workflow_executing(node_id: str | None, prompt_id: str | None,
                            node_class: str | None = None) -> None:
    global _workflow_running, _current_node_id, _current_node_class, _current_prompt_id
    with _workflow_status_lock:
        if node_id is None:
            # Prompt finished
            _workflow_running = False
            _current_node_id = None
            _current_node_class = None
        else:
            _workflow_running = True
            _current_node_id = node_id
            _current_prompt_id = prompt_id
            if node_class:
                _current_node_class = node_class


def _set_user_prompt(prompt: dict, extra_data: dict | None = None) -> None:
    global _user_prompt, _user_extra_data
    with _workflow_status_lock:
        _user_prompt = prompt
        _user_extra_data = extra_data
    # Persist to disk so it survives server restarts
    _save_user_prompt_to_disk(prompt, extra_data)


def _save_user_prompt_to_disk(prompt: dict, extra_data: dict | None) -> None:
    """Write the last user prompt to a JSON file for cross-session rerun."""
    try:
        os.makedirs(_PERSIST_DIR, exist_ok=True)
        payload = {"prompt": prompt, "extra_data": extra_data or {}}
        with open(_PERSIST_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass  # best-effort


def _load_user_prompt_from_disk() -> bool:
    """Load the persisted prompt from disk into ``_user_prompt``.

    Returns True if successful, False otherwise.
    """
    global _user_prompt, _user_extra_data
    import copy
    with _workflow_status_lock:
        if _user_prompt is not None:
            return True  # already have one

    try:
        if not os.path.isfile(_PERSIST_PATH):
            return False
        with open(_PERSIST_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        prompt = payload.get("prompt")
        extra_data = payload.get("extra_data", {})
        if not prompt or not isinstance(prompt, dict):
            return False
        # Write directly to globals (skip _set_user_prompt to avoid
        # redundantly re-saving the same file we just loaded).
        with _workflow_status_lock:
            _user_prompt = copy.deepcopy(prompt)
            _user_extra_data = copy.deepcopy(extra_data)
        return True
    except Exception:
        return False


def get_workflow_status() -> dict:
    with _workflow_status_lock:
        return {
            "running": _workflow_running,
            "current_node_id": _current_node_id,
            "current_node_class": _current_node_class,
            "prompt_id": _current_prompt_id,
            "has_last_prompt": _user_prompt is not None,
            "last_rerun_id": _last_rerun_id,
            "last_interrupt_id": _last_interrupt_id,
        }


# ---------------------------------------------------------------------------
# Server hook — intercepts PromptServer.send_sync to capture image events
# ---------------------------------------------------------------------------

_hook_installed = False


def _install_server_hook() -> None:
    """Monkey-patch ``PromptServer.send_sync`` to capture ``executed`` events
    that carry image data, and ``BinaryEventTypes.UNENCODED_PREVIEW_IMAGE``
    events that carry step-by-step KSampler latent previews.

    This is called once at module load time.
    """
    global _hook_installed
    if _hook_installed:
        return
    _hook_installed = True

    try:
        from server import PromptServer, BinaryEventTypes
    except ImportError:
        return
    if not hasattr(PromptServer, "instance") or PromptServer.instance is None:
        return

    server = PromptServer.instance
    _orig_send_sync = server.send_sync

    def _patched_send_sync(event, data, sid=None):
        try:
            # Capture "executed" events that contain images
            if event == "executed" and isinstance(data, dict):
                output = data.get("output")
                if output and isinstance(output, dict):
                    images = output.get("images")
                    if images and isinstance(images, list) and len(images) > 0:
                        _set_latest_images(images)

            # Track which node is currently executing
            if event == "executing" and isinstance(data, dict):
                node_id = data.get("node")
                prompt_id = data.get("prompt_id")
                display_node = data.get("display_node")
                # Try to resolve the node class type from the prompt
                node_class = None
                if node_id is not None:
                    try:
                        status = get_workflow_status()
                        pid = prompt_id or status.get("prompt_id")
                        if pid and _user_prompt:
                            node_info = _user_prompt.get(node_id) or _user_prompt.get(display_node)
                            if node_info and isinstance(node_info, dict):
                                node_class = node_info.get("class_type")
                    except Exception:
                        pass
                _set_workflow_executing(node_id, prompt_id, node_class)

            # Capture the prompt data when execution_start fires for requeue
            if event == "execution_start" and isinstance(data, dict):
                prompt_id = data.get("prompt_id")
                if prompt_id:
                    _set_workflow_executing("__starting__", prompt_id, "Starting…")

            # Capture unencoded preview images (KSampler step previews)
            # Old method: UNENCODED_PREVIEW_IMAGE — data is (format_str, PIL.Image, max_size)
            if event == BinaryEventTypes.UNENCODED_PREVIEW_IMAGE and data is not None:
                try:
                    _encode_and_store_preview(data)
                except Exception:
                    pass

            # New method: PREVIEW_IMAGE_WITH_METADATA — data is ((format_str, PIL.Image, max_size), metadata_dict)
            # Modern frontends that declare "supports_preview_metadata" use this path instead.
            if event == BinaryEventTypes.PREVIEW_IMAGE_WITH_METADATA and data is not None:
                try:
                    image_tuple = data[0]  # (format_str, PIL.Image, max_size)
                    _encode_and_store_preview(image_tuple)
                except Exception:
                    pass
        except Exception:
            pass

        return _orig_send_sync(event, data, sid)

    def _encode_and_store_preview(image_data):
        """Encode a (format_str, PIL.Image, max_size) tuple to JPEG bytes and store it."""
        from io import BytesIO
        from PIL import Image, ImageOps
        fmt = image_data[0]   # "JPEG" or "PNG"
        img = image_data[1]
        max_size = image_data[2]
        if max_size is not None:
            resampling = getattr(Image, "Resampling", Image).BILINEAR
            img = ImageOps.contain(img, (max_size, max_size), resampling)
        buf = BytesIO()
        img.save(buf, format=fmt, quality=95, compress_level=1)
        _set_latest_preview_blob(buf.getvalue())

    server.send_sync = _patched_send_sync

    # Also hook prompt_queue.put to capture prompt data for rerun.
    # When _rerun_in_progress is True we skip overwriting _user_prompt so
    # that the original user prompt is preserved for future reruns.
    _orig_put = server.prompt_queue.put
    def _patched_put(item):
        try:
            if item and len(item) >= 4 and not _rerun_in_progress:
                import copy
                _set_user_prompt(copy.deepcopy(item[2]), copy.deepcopy(item[3]))
        except Exception:
            pass
        return _orig_put(item)
    server.prompt_queue.put = _patched_put


# ---------------------------------------------------------------------------
# Rerun helpers
# ---------------------------------------------------------------------------

# Prompt input keys that typically carry a seed value.
_SEED_INPUT_KEYS = {"seed", "noise_seed", "seed_num"}

# Default upper bound — matches ComfyUI's standard INT widget range.
_DEFAULT_SEED_MAX = 0xFFFFFFFFFFFFFFFF


def _get_seed_range_for_node(class_type: str, seed_key: str) -> tuple[int, int]:
    """Return ``(min, max)`` for *seed_key* as declared in the node's
    ``INPUT_TYPES``.  Falls back to ``(0, _DEFAULT_SEED_MAX)``."""
    try:
        import nodes
        cls = nodes.NODE_CLASS_MAPPINGS.get(class_type)
        if cls is None:
            return 0, _DEFAULT_SEED_MAX
        input_types = cls.INPUT_TYPES()
        for section in ("required", "optional"):
            section_dict = input_types.get(section, {})
            if seed_key in section_dict:
                spec = section_dict[seed_key]
                if isinstance(spec, tuple) and len(spec) >= 2 and isinstance(spec[1], dict):
                    return (spec[1].get("min", 0),
                            spec[1].get("max", _DEFAULT_SEED_MAX))
    except Exception:
        pass
    return 0, _DEFAULT_SEED_MAX


def _clamp_seed_values(prompt: dict, extra_data: dict | None = None) -> None:
    """Clamp every seed-like INT input to its node-defined range.

    This prevents ``validate_prompt`` from rejecting nodes whose cached
    seed value exceeds the ``max`` declared in their ``INPUT_TYPES``.

    Uses ``seed_widgets`` from the workflow metadata (if available) to
    reliably identify seed inputs and keep ``widgets_values`` in sync.
    Falls back to scanning ``_SEED_INPUT_KEYS`` in the prompt dict.
    """
    import random

    seed_widget_map: dict | None = None
    workflow_nodes_by_id: dict = {}
    try:
        wf = extra_data["extra_pnginfo"]["workflow"]
        seed_widget_map = wf.get("seed_widgets")
        for n in wf.get("nodes", []):
            workflow_nodes_by_id[str(n["id"])] = n
    except (KeyError, TypeError, AttributeError):
        pass

    for node_id, node_data in prompt.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get("class_type", "")
        inputs = node_data.get("inputs")
        if not isinstance(inputs, dict):
            continue

        # Check every seed-like key in this node's inputs
        for seed_key in _SEED_INPUT_KEYS:
            if seed_key not in inputs or not isinstance(inputs[seed_key], (int, float)):
                continue
            val = int(inputs[seed_key])
            lo, hi = _get_seed_range_for_node(class_type, seed_key)
            if val < lo or val > hi:
                inputs[seed_key] = random.randint(lo, hi)
                # Also sync widgets_values via seed_widget_map
                wf_node = workflow_nodes_by_id.get(node_id)
                wv_idx = (seed_widget_map or {}).get(node_id)
                if wf_node and wv_idx is not None:
                    wv = wf_node.get("widgets_values")
                    if isinstance(wv, list) and wv_idx < len(wv):
                        wv[wv_idx] = inputs[seed_key]


def _apply_control_after_generate(prompt: dict, extra_data: dict,
                                  skip_nodes: set[str] | None = None) -> None:
    """Apply per-widget ``control_after_generate`` rules to seed inputs.

    This function handles **standard ComfyUI seed widgets** that are NOT
    managed by any third-party ``on_prompt_handler`` hook.  Third-party
    global-seed nodes (Easy-Use, Inspire-Pack, Impact-Pack, etc.) are
    handled *universally* by calling ``trigger_on_prompt`` in the rerun
    handler **before** this function is invoked.

    *skip_nodes* — node IDs whose seeds were already modified by a hook
    and must NOT be touched again.

    Strategy:
      1. **seed_widgets** map (from workflow metadata) — for every
         node ID in this map, read the ``control_after_generate``
         action string from ``widgets_values[widget_idx + 1]``.
      2. **Fallback** — for nodes NOT in ``seed_widgets``, scan for
         ``seed`` / ``noise_seed`` / ``seed_num`` inputs and try to
         discover the action from ``widgets_values`` via value-matching.

    All generated seed values are clamped to the node's declared min/max.
    """
    if skip_nodes is None:
        skip_nodes = set()

    # ── Extract workflow metadata ──
    seed_widget_map: dict | None = None   # node_id_str → widget_idx
    workflow_nodes_by_id: dict = {}
    try:
        wf = extra_data["extra_pnginfo"]["workflow"]
        seed_widget_map = wf.get("seed_widgets")
        for n in wf.get("nodes", []):
            workflow_nodes_by_id[str(n["id"])] = n
    except (KeyError, TypeError):
        pass

    # ── Strategy 1: use seed_widgets for reliable widget-index lookup ──
    handled_nodes: set[str] = set()
    if seed_widget_map:
        for nid, wv_idx in seed_widget_map.items():
            if nid not in prompt or nid in skip_nodes:
                continue
            ndata = prompt[nid]
            if not isinstance(ndata, dict):
                continue
            class_type = ndata.get("class_type", "")
            inputs = ndata.get("inputs", {})
            wf_node = workflow_nodes_by_id.get(nid)
            wv = wf_node.get("widgets_values") if wf_node else None

            # Read action from widgets_values[wv_idx + 1]
            action = "randomize"  # default
            if isinstance(wv, list) and wv_idx + 1 < len(wv):
                candidate = wv[wv_idx + 1]
                if isinstance(candidate, str) and candidate in (
                    "fixed", "increment", "decrement", "randomize"
                ):
                    action = candidate

            # Find the seed input key and apply the action
            for sk in ("seed_num", "seed", "noise_seed"):
                if sk in inputs and isinstance(inputs[sk], (int, float)):
                    lo, hi = _get_seed_range_for_node(class_type, sk)
                    inputs[sk] = _apply_seed_action(
                        int(inputs[sk]), action, hi, lo
                    )
                    # Sync widgets_values
                    if isinstance(wv, list) and wv_idx < len(wv):
                        wv[wv_idx] = inputs[sk]
                    handled_nodes.add(nid)
                    break

    # ── Strategy 2: nodes NOT in seed_widget_map ──
    # Use the workflow node's widgets_values to find control_after_generate.
    for nid, ndata in prompt.items():
        if not isinstance(ndata, dict):
            continue
        if nid in handled_nodes or nid in skip_nodes:
            continue  # already handled via seed_widget_map or hook
        inputs = ndata.get("inputs")
        if not isinstance(inputs, dict):
            continue
        class_type = ndata.get("class_type", "")

        wf_node = workflow_nodes_by_id.get(nid)
        wv = wf_node.get("widgets_values") if wf_node else None

        for seed_key in _SEED_INPUT_KEYS:
            if seed_key not in inputs or not isinstance(inputs[seed_key], (int, float)):
                continue
            lo, hi = _get_seed_range_for_node(class_type, seed_key)

            # Try to discover the action from widgets_values
            action = "randomize"  # default for nodes without metadata
            if isinstance(wv, list):
                seed_val = inputs[seed_key]
                for idx, wv_val in enumerate(wv):
                    if wv_val == seed_val and idx + 1 < len(wv):
                        candidate = wv[idx + 1]
                        if isinstance(candidate, str) and candidate in (
                            "fixed", "increment", "decrement", "randomize"
                        ):
                            action = candidate
                            break

            inputs[seed_key] = _apply_seed_action(
                int(inputs[seed_key]), action, hi, lo
            )

            # Sync widgets_values (best-effort value search)
            if isinstance(wv, list):
                for idx, wv_val in enumerate(wv):
                    if idx + 1 < len(wv) and isinstance(wv[idx + 1], str) and wv[idx + 1] in (
                        "fixed", "increment", "decrement", "randomize"
                    ):
                        wv[idx] = inputs[seed_key]
                        break


def _apply_seed_action(current: int, action: str, max_seed: int,
                       min_seed: int = 0) -> int:
    """Apply a control_after_generate action to a seed value."""
    import random
    if action == "randomize":
        return random.randint(min_seed, max_seed)
    elif action == "increment":
        return (current + 1) if current < max_seed else min_seed
    elif action == "decrement":
        return (current - 1) if current > min_seed else max_seed
    else:  # "fixed" or unknown
        return current


def _try_load_from_history() -> bool:
    """Try to load the last prompt from ComfyUI's history.

    If ``_user_prompt`` is None (nothing queued this session), inspect
    the server's execution history for the most recent entry and use
    its prompt/extra_data.  Returns True if successful.
    """
    import copy
    with _workflow_status_lock:
        if _user_prompt is not None:
            return True  # already have one

    try:
        from server import PromptServer
        srv = PromptServer.instance
        history = srv.prompt_queue.get_history(max_items=1)
        if not history:
            return False
        # history is {prompt_id: {"prompt": [number, id, prompt_dict, extra_data, ...], ...}}
        entry = next(iter(history.values()))
        prompt_tuple = entry.get("prompt")
        if not prompt_tuple or len(prompt_tuple) < 4:
            return False
        prompt_dict = copy.deepcopy(prompt_tuple[2])
        extra_data = copy.deepcopy(prompt_tuple[3]) if prompt_tuple[3] else {}
        _set_user_prompt(prompt_dict, extra_data)
        return True
    except Exception:
        return False


def _clear_pending_queue(srv) -> None:
    """Remove all pending (not-yet-running) items from the queue.

    This prevents stacking multiple reruns when the button is clicked
    rapidly or when retries fire before the previous rerun started.
    """
    try:
        srv.prompt_queue.wipe_queue()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Register HTTP routes
# ---------------------------------------------------------------------------

_routes_registered = False


def _register_routes() -> None:
    """Register custom HTTP routes on the PromptServer singleton.

    Provides:
        GET /simple_utility/global_image_preview/latest          — JSON of latest images
        GET /simple_utility/global_image_preview/latest_preview   — raw JPEG of latest step preview
        GET /simple_utility/global_image_preview/viewer           — fullscreen HTML viewer
    """
    global _routes_registered
    if _routes_registered:
        return
    _routes_registered = True

    try:
        from server import PromptServer
        from aiohttp import web
    except ImportError:
        return
    if not hasattr(PromptServer, "instance") or PromptServer.instance is None:
        return

    routes = PromptServer.instance.routes

    # All polling endpoints MUST include Cache-Control: no-store.
    # Without it, browsers may apply heuristic caching for non-loopback
    # origins (e.g. LAN IPs like 192.168.x.x) while bypassing cache for
    # 127.0.0.1, causing the standalone viewer to never refresh on LAN.
    _NO_CACHE_HDRS = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    @routes.get("/simple_utility/global_image_preview/latest")
    async def _api_latest(request):
        """Return the latest executed-event images as JSON."""
        images, images_counter = get_latest_images()
        blob, preview_counter = get_latest_preview_blob()
        return web.json_response({
            "images": images,
            "images_counter": images_counter,
            "has_preview_blob": blob is not None,
            "preview_counter": preview_counter,
        }, headers=_NO_CACHE_HDRS)

    @routes.get("/simple_utility/global_image_preview/latest_preview")
    async def _api_latest_preview(request):
        """Return the latest KSampler step preview as raw JPEG."""
        blob, counter = get_latest_preview_blob()
        if blob is None:
            return web.Response(status=204, headers=_NO_CACHE_HDRS)
        return web.Response(
            body=blob,
            content_type="image/jpeg",
            headers={
                **_NO_CACHE_HDRS,
                "X-Preview-Counter": str(counter),
            },
        )

    @routes.get("/simple_utility/global_image_preview/status")
    async def _api_status(request):
        """Return workflow execution status + queue info for smart retry."""
        st = get_workflow_status()
        # Include queue_pending so the viewer can avoid duplicate submissions
        try:
            st["queue_pending"] = PromptServer.instance.prompt_queue.get_tasks_remaining()
        except Exception:
            st["queue_pending"] = 0
        return web.json_response(st, headers=_NO_CACHE_HDRS)

    @routes.post("/simple_utility/global_image_preview/rerun")
    async def _api_rerun(request):
        """Interrupt the current workflow (if running), wait for it to
        fully stop, then re-queue the last prompt.

        Accepts JSON body:
          - ``mode``: ``"same"`` (default) or ``"new"``
            - ``"same"``: re-queue with identical settings (seeds unchanged).
            - ``"new"``: apply each seed widget's ``control_after_generate``
              setting (randomize / increment / decrement / fixed) so the
              result changes as it would when pressing Queue Prompt in the UI.
          - ``rerun_id``: a unique caller-supplied ID (e.g. per-tab UUID).
            The server tracks the last ``rerun_id`` that successfully queued
            so callers can poll ``GET /status`` and check ``last_rerun_id``
            to confirm their command was processed without ambiguity.
        """
        global _rerun_in_progress, _last_rerun_id
        import nodes as comfy_nodes
        import asyncio
        import copy
        import random

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        mode = body.get("mode", "same")        # "same" | "new"
        rerun_id = body.get("rerun_id", None)  # per-tab caller ID

        # ── Step 1: Interrupt current workflow if running ──
        status = get_workflow_status()
        if status["running"]:
            comfy_nodes.interrupt_processing()
            # Poll until the workflow is no longer running (max 5 s)
            for _ in range(50):
                await asyncio.sleep(0.1)
                if not get_workflow_status()["running"]:
                    break

        # ── Step 2: Clear pending queue to avoid stacking reruns ──
        try:
            srv = PromptServer.instance
            _clear_pending_queue(srv)
        except Exception:
            pass

        # ── Step 3: Deep-copy the saved user prompt ──
        # If nothing has been queued this session, try loading from:
        #   1. Disk cache (persisted from a previous session)
        #   2. In-memory history (if any prompt ran this session)
        if _user_prompt is None:
            if not _load_user_prompt_from_disk():
                _try_load_from_history()

        with _workflow_status_lock:
            if _user_prompt is None:
                return web.json_response(
                    {"error": "No previous prompt to rerun. "
                     "Run a workflow first or check history."},
                    status=400,
                )
            prompt = copy.deepcopy(_user_prompt)
            extra_data = copy.deepcopy(_user_extra_data) if _user_extra_data else {}

        # ── Step 4 (New Task only): run on_prompt hooks + per-node CAG ──
        #
        # The normal ``/prompt`` route calls ``trigger_on_prompt`` which
        # invokes ALL ``on_prompt_handler`` hooks registered by every
        # custom-node package (e.g. Easy-Use globalSeed distribution,
        # Impact-Pack switches / wildcards / regional-sampler seeds,
        # Inspire-Pack global-seed / wildcards / sampler updates, etc.).
        #
        # Our rerun bypasses ``/prompt`` entirely, so we must call
        # ``trigger_on_prompt`` ourselves for New Task mode so that
        # **all** hooks run — no hardcoded node-specific logic needed.
        #
        # For Same Task mode, hooks must NOT run (user wants the exact
        # same prompt), but we still clamp seeds to valid ranges.
        #
        # After hooks, we also run our own per-node control_after_generate
        # logic for *standard* ComfyUI seed widgets — these are NOT
        # handled by any hook (KSampler, etc.).

        import uuid
        prompt_id = str(uuid.uuid4())
        srv = PromptServer.instance

        if mode == "new":
            # Snapshot seed values BEFORE hooks — so we can detect which
            # nodes were modified by a hook and avoid double-applying our
            # own per-node control_after_generate to those nodes.
            seed_snapshot: dict[str, dict[str, int]] = {}
            for nid, ndata in prompt.items():
                if not isinstance(ndata, dict):
                    continue
                inputs = ndata.get("inputs")
                if not isinstance(inputs, dict):
                    continue
                for sk in _SEED_INPUT_KEYS:
                    if sk in inputs and isinstance(inputs[sk], (int, float)):
                        seed_snapshot.setdefault(nid, {})[sk] = int(inputs[sk])

            # Build the json_data envelope that trigger_on_prompt expects
            # (same shape the frontend POSTs to /prompt).
            json_data = {
                "prompt": prompt,
                "extra_data": extra_data,
            }
            json_data = srv.trigger_on_prompt(json_data)
            # Re-extract prompt / extra_data — hooks may have replaced or
            # mutated the dicts, or even restructured the envelope.
            prompt = json_data.get("prompt", prompt)
            extra_data = json_data.get("extra_data", extra_data)

            # Determine which nodes had their seeds changed by hooks
            hook_modified_nodes: set[str] = set()
            for nid, old_seeds in seed_snapshot.items():
                if nid not in prompt:
                    continue
                ndata = prompt[nid]
                if not isinstance(ndata, dict):
                    continue
                inputs = ndata.get("inputs", {})
                for sk, old_val in old_seeds.items():
                    cur = inputs.get(sk)
                    if isinstance(cur, (int, float)) and int(cur) != old_val:
                        hook_modified_nodes.add(nid)
                        break

            # Apply per-node control_after_generate for standard seed
            # widgets (KSampler etc.) that no hook has already modified.
            _apply_control_after_generate(prompt, extra_data,
                                          skip_nodes=hook_modified_nodes)

        # ── Step 4b: Clamp seed values to each node's declared range ──
        # This is necessary for BOTH modes because the cached prompt may
        # contain seed values that were valid in a different context (e.g.
        # the frontend randomised within 64-bit range but the node only
        # accepts 32-bit seeds).  validate_prompt would reject such nodes.
        _clamp_seed_values(prompt, extra_data)

        # ── Step 5: Apply node replacements (same as /prompt route) ──
        try:
            srv.node_replace_manager.apply_replacements(prompt)
        except Exception:
            pass

        try:
            import execution
            valid = await execution.validate_prompt(prompt_id, prompt, None)
            if valid[0]:
                outputs_to_execute = valid[2]
                _rerun_in_progress = True
                try:
                    srv.prompt_queue.put(
                        (srv.number, prompt_id, prompt, extra_data,
                         outputs_to_execute, {})
                    )
                finally:
                    _rerun_in_progress = False
                srv.number += 1
                # Update _user_prompt so the NEXT rerun always uses the
                # very last queued workflow (not the original one).
                import copy as _copy
                _set_user_prompt(_copy.deepcopy(prompt), _copy.deepcopy(extra_data))
                # Track the rerun_id so callers can confirm processing
                with _workflow_status_lock:
                    _last_rerun_id = rerun_id
                return web.json_response(
                    {"prompt_id": prompt_id, "status": "queued",
                     "mode": mode, "rerun_id": rerun_id}
                )
            else:
                return web.json_response(
                    {"error": str(valid[1])}, status=400
                )
        except Exception as e:
            _rerun_in_progress = False
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/simple_utility/global_image_preview/interrupt")
    async def _api_interrupt(request):
        """Interrupt the current workflow and confirm via interrupt_id.

        Accepts JSON body:
          - ``interrupt_id``: a unique caller-supplied ID (per-tab UUID).
            The server tracks the last ``interrupt_id`` that was processed
            so callers can poll ``GET /status`` to confirm.

        Does nothing if no workflow is running (returns success immediately).
        """
        global _last_interrupt_id
        import nodes as comfy_nodes
        import asyncio

        body = {}
        try:
            body = await request.json()
        except Exception:
            pass
        interrupt_id = body.get("interrupt_id", None)

        status = get_workflow_status()
        if status["running"]:
            comfy_nodes.interrupt_processing()
            # Poll until the workflow is no longer running (max 5 s)
            for _ in range(50):
                await asyncio.sleep(0.1)
                if not get_workflow_status()["running"]:
                    break

        with _workflow_status_lock:
            _last_interrupt_id = interrupt_id

        return web.json_response({
            "status": "interrupted" if status["running"] else "idle",
            "interrupt_id": interrupt_id,
        })

    @routes.get("/simple_utility/global_image_preview/viewer")
    async def _viewer_page(request):
        """Serve the fullscreen auto-updating viewer HTML page.

        The response MUST include ``Cache-Control: no-cache`` so browsers
        always revalidate (or re-fetch) the viewer HTML.  Without this,
        browsers may heuristically cache the HTML using the ``Last-Modified``
        date and serve a stale copy — particularly on non-loopback origins
        (LAN IPs) where some browsers are more aggressive with caching.
        """
        html_path = os.path.join(
            os.path.dirname(__file__), "..", "web", "global_image_preview_viewer.html"
        )
        html_path = os.path.normpath(html_path)
        if os.path.isfile(html_path):
            # Read the file and return as a normal Response with cache headers
            # instead of FileResponse, because FileResponse does not allow
            # overriding Cache-Control (it only sets ETag/Last-Modified).
            try:
                with open(html_path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                return web.Response(
                    text=html_content,
                    content_type="text/html; charset=utf-8",
                    headers=_NO_CACHE_HDRS,
                )
            except Exception:
                return web.FileResponse(html_path)
        return web.Response(
            text="<html><body><h1>Viewer HTML not found</h1></body></html>",
            content_type="text/html",
        )


# Run at import time
try:
    _install_server_hook()
    _register_routes()
except Exception:
    pass


# ---------------------------------------------------------------------------
# The ComfyUI Node
# ---------------------------------------------------------------------------

class SimpleGlobalImagePreview:
    """Monitor ALL nodes that generate preview / temp / saved images and display them.

    This node requires **no input connections**.  The front-end extension globally
    listens to every ``executed`` WebSocket event (from PreviewImage, SaveImage,
    etc.) and every ``b_preview`` binary frame (KSampler step-by-step latent
    previews) and draws them on the node canvas.

    A button on the node opens a new browser tab with a fullscreen auto-updating
    image viewer.

    The node does **not** send images to the ComfyUI image feed.
    """

    CATEGORY = "Simple Utility ⛏️/Global"
    FUNCTION = "execute"
    RETURN_TYPES = ()
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always re-execute so the node stays alive in the execution graph."""
        return float("NaN")

    def execute(self, unique_id: str = None):
        # Ensure hooks / routes are in place (retry if earlier attempt failed)
        _install_server_hook()
        _register_routes()

        # We intentionally return an empty ui dict so the node does NOT
        # push anything into the ComfyUI image feed.
        return {"ui": {}}


# ---------------------------------------------------------------------------
# Node registration
# ---------------------------------------------------------------------------

NODE_CLASS_MAPPINGS = {
    "SimpleGlobalImagePreview": SimpleGlobalImagePreview,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleGlobalImagePreview": "⛏️ Simple Global Image Preview",
}
