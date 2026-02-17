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

import os
import threading
from typing import Dict, List

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


def get_workflow_status() -> dict:
    with _workflow_status_lock:
        return {
            "running": _workflow_running,
            "current_node_id": _current_node_id,
            "current_node_class": _current_node_class,
            "prompt_id": _current_prompt_id,
            "has_last_prompt": _user_prompt is not None,
            "last_rerun_id": _last_rerun_id,
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

_SEED_INPUT_KEYS = {"seed", "noise_seed"}


def _apply_control_after_generate(prompt: dict, extra_data: dict) -> None:
    """Apply per-widget ``control_after_generate`` rules to seed inputs.

    Inspects ``extra_data['extra_pnginfo']['workflow']['nodes']`` to discover
    which nodes have seed widgets with a companion ``control_after_generate``
    combo widget.  For each such node the corresponding seed value in *prompt*
    is mutated according to the rule:

    - ``"randomize"`` → random 64-bit integer
    - ``"increment"`` → current value + 1  (wraps at 2^64)
    - ``"decrement"`` → current value − 1  (wraps at 0)
    - ``"fixed"``     → no change

    If no workflow metadata is available, falls back to randomising every
    ``seed`` / ``noise_seed`` input unconditionally.
    """
    import random

    MAX_SEED = 0xFFFFFFFFFFFFFFFF

    # Try to extract node metadata from the workflow
    workflow_nodes: list | None = None
    try:
        workflow_nodes = extra_data["extra_pnginfo"]["workflow"]["nodes"]
    except (KeyError, TypeError):
        pass

    if workflow_nodes:
        # Build a mapping:  node_id_str → control_after_generate action
        # by inspecting widgets_values for each workflow node.
        #
        # Convention: for each seed/noise_seed INT input declared with
        # control_after_generate=True, the frontend inserts a combo widget
        # immediately *after* the seed widget in widgets_values.
        # We detect this by walking the prompt's inputs, finding seed keys,
        # then locating them in the serialised widgets_values array.
        node_actions: dict[str, dict[str, str]] = {}  # node_id → { input_key → action }
        for wf_node in workflow_nodes:
            node_id = str(wf_node.get("id", ""))
            wv = wf_node.get("widgets_values")
            if not isinstance(wv, list) or node_id not in prompt:
                continue
            node_inputs = prompt[node_id].get("inputs") if isinstance(prompt[node_id], dict) else None
            if not node_inputs:
                continue
            # For each seed key in the prompt inputs, find its position in
            # widgets_values and read the next value as the action string.
            for seed_key in _SEED_INPUT_KEYS:
                if seed_key not in node_inputs:
                    continue
                seed_val = node_inputs[seed_key]
                if not isinstance(seed_val, (int, float)):
                    continue
                # Locate seed_val in widgets_values
                for idx, wv_val in enumerate(wv):
                    if wv_val == seed_val and idx + 1 < len(wv):
                        next_val = wv[idx + 1]
                        if isinstance(next_val, str) and next_val in (
                            "fixed", "increment", "decrement", "randomize"
                        ):
                            node_actions.setdefault(node_id, {})[seed_key] = next_val
                            break

        # Apply the discovered actions (or default to randomize for
        # nodes that have seed inputs but no workflow metadata entry)
        for node_id, node_data in prompt.items():
            if not isinstance(node_data, dict):
                continue
            inputs = node_data.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for seed_key in _SEED_INPUT_KEYS:
                if seed_key not in inputs or not isinstance(inputs[seed_key], (int, float)):
                    continue
                action = (node_actions.get(node_id) or {}).get(seed_key, "randomize")
                inputs[seed_key] = _apply_seed_action(int(inputs[seed_key]), action, MAX_SEED)

        # Also update widgets_values in the workflow metadata so that
        # saved PNG metadata stays consistent with what was actually run.
        for wf_node in workflow_nodes:
            node_id = str(wf_node.get("id", ""))
            wv = wf_node.get("widgets_values")
            if not isinstance(wv, list) or node_id not in prompt:
                continue
            node_inputs = prompt[node_id].get("inputs") if isinstance(prompt[node_id], dict) else None
            if not node_inputs:
                continue
            for seed_key in _SEED_INPUT_KEYS:
                if seed_key not in node_inputs:
                    continue
                new_val = node_inputs[seed_key]
                # Find and update the old seed value in widgets_values
                actions = (node_actions.get(node_id) or {})
                if seed_key in actions:
                    for idx, wv_val in enumerate(wv):
                        if idx + 1 < len(wv) and isinstance(wv[idx + 1], str) and wv[idx + 1] in (
                            "fixed", "increment", "decrement", "randomize"
                        ):
                            wv[idx] = new_val
                            break
    else:
        # Fallback: no workflow metadata — randomise all seed inputs
        for _nid, node_data in prompt.items():
            if not isinstance(node_data, dict):
                continue
            inputs = node_data.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for seed_key in _SEED_INPUT_KEYS:
                if seed_key in inputs and isinstance(inputs[seed_key], (int, float)):
                    inputs[seed_key] = random.randint(0, MAX_SEED)


def _apply_seed_action(current: int, action: str, max_seed: int) -> int:
    """Apply a control_after_generate action to a seed value."""
    import random
    if action == "randomize":
        return random.randint(0, max_seed)
    elif action == "increment":
        return (current + 1) if current < max_seed else 0
    elif action == "decrement":
        return (current - 1) if current > 0 else max_seed
    else:  # "fixed" or unknown
        return current


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
        })

    @routes.get("/simple_utility/global_image_preview/latest_preview")
    async def _api_latest_preview(request):
        """Return the latest KSampler step preview as raw JPEG."""
        blob, counter = get_latest_preview_blob()
        if blob is None:
            return web.Response(status=204)  # No content yet
        return web.Response(
            body=blob,
            content_type="image/jpeg",
            headers={
                "Cache-Control": "no-cache, no-store",
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
        return web.json_response(st)

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
        with _workflow_status_lock:
            if _user_prompt is None:
                return web.json_response(
                    {"error": "No previous prompt to rerun"}, status=400
                )
            prompt = copy.deepcopy(_user_prompt)
            extra_data = copy.deepcopy(_user_extra_data) if _user_extra_data else {}

        # ── Step 4 (New Task only): apply control_after_generate rules ──
        if mode == "new":
            _apply_control_after_generate(prompt, extra_data)

        import uuid
        prompt_id = str(uuid.uuid4())

        try:
            import execution
            srv = PromptServer.instance
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

    @routes.get("/simple_utility/global_image_preview/viewer")
    async def _viewer_page(request):
        """Serve the fullscreen auto-updating viewer HTML page."""
        html_path = os.path.join(
            os.path.dirname(__file__), "..", "web", "global_image_preview_viewer.html"
        )
        html_path = os.path.normpath(html_path)
        if os.path.isfile(html_path):
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
