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
_last_prompt: dict | None = None  # the full prompt dict for requeue
_last_extra_data: dict | None = None


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


def _set_last_prompt(prompt: dict, extra_data: dict | None = None) -> None:
    global _last_prompt, _last_extra_data
    with _workflow_status_lock:
        _last_prompt = prompt
        _last_extra_data = extra_data


def get_workflow_status() -> dict:
    with _workflow_status_lock:
        return {
            "running": _workflow_running,
            "current_node_id": _current_node_id,
            "current_node_class": _current_node_class,
            "prompt_id": _current_prompt_id,
            "has_last_prompt": _last_prompt is not None,
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
                        if pid and _last_prompt:
                            node_info = _last_prompt.get(node_id) or _last_prompt.get(display_node)
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

    # Also hook prompt_queue.put to capture prompt data for rerun
    _orig_put = server.prompt_queue.put
    def _patched_put(item):
        try:
            # item is (number, prompt_id, prompt, extra_data, outputs_to_execute, sensitive)
            if item and len(item) >= 4:
                import copy
                _set_last_prompt(copy.deepcopy(item[2]), copy.deepcopy(item[3]))
        except Exception:
            pass
        return _orig_put(item)
    server.prompt_queue.put = _patched_put


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
        """Return workflow execution status."""
        return web.json_response(get_workflow_status())

    @routes.post("/simple_utility/global_image_preview/rerun")
    async def _api_rerun(request):
        """Interrupt the current workflow (if running) and re-queue the last prompt."""
        import nodes as comfy_nodes
        status = get_workflow_status()

        # Interrupt if currently running
        if status["running"]:
            comfy_nodes.interrupt_processing()
            # Small delay to let the interrupt propagate
            import asyncio
            await asyncio.sleep(0.3)

        # Re-queue the last prompt
        with _workflow_status_lock:
            prompt = _last_prompt
            extra = _last_extra_data

        if prompt is None:
            return web.json_response({"error": "No previous prompt to rerun"}, status=400)

        import uuid
        prompt_id = str(uuid.uuid4())
        extra_data = dict(extra) if extra else {}
        # Submit via the queue directly
        try:
            import execution
            srv = PromptServer.instance
            valid = await execution.validate_prompt(prompt_id, prompt, None)
            if valid[0]:
                outputs_to_execute = valid[2]
                srv.prompt_queue.put(
                    (srv.number, prompt_id, prompt, extra_data, outputs_to_execute, {})
                )
                srv.number += 1
                return web.json_response({"prompt_id": prompt_id, "status": "queued"})
            else:
                return web.json_response({"error": str(valid[1])}, status=400)
        except Exception as e:
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

    CATEGORY = "Simple Utility ⛏️/Global Variable"
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
