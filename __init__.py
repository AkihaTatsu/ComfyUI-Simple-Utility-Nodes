"""
ComfyUI Simple Utility Nodes

A collection of simple utility nodes for ComfyUI including time-related,
string manipulation, switch, script, and global nodes.
"""

import os
import threading
import logging

logger = logging.getLogger("ComfyUI-Simple-Utility-Nodes")

from .time_nodes import NODE_CLASS_MAPPINGS as TIME_NODE_CLASS_MAPPINGS
from .time_nodes import NODE_DISPLAY_NAME_MAPPINGS as TIME_NODE_DISPLAY_NAME_MAPPINGS
from .string_nodes import NODE_CLASS_MAPPINGS as STRING_NODE_CLASS_MAPPINGS
from .string_nodes import NODE_DISPLAY_NAME_MAPPINGS as STRING_NODE_DISPLAY_NAME_MAPPINGS
from .switch_nodes import NODE_CLASS_MAPPINGS as SWITCH_NODE_CLASS_MAPPINGS
from .switch_nodes import NODE_DISPLAY_NAME_MAPPINGS as SWITCH_NODE_DISPLAY_NAME_MAPPINGS
from .script_nodes import NODE_CLASS_MAPPINGS as SCRIPT_NODE_CLASS_MAPPINGS
from .script_nodes import NODE_DISPLAY_NAME_MAPPINGS as SCRIPT_NODE_DISPLAY_NAME_MAPPINGS
from .global_nodes import NODE_CLASS_MAPPINGS as GLOBAL_VAR_NODE_CLASS_MAPPINGS
from .global_nodes import NODE_DISPLAY_NAME_MAPPINGS as GLOBAL_VAR_NODE_DISPLAY_NAME_MAPPINGS

# Merge all node mappings
NODE_CLASS_MAPPINGS = {
    **TIME_NODE_CLASS_MAPPINGS,
    **STRING_NODE_CLASS_MAPPINGS,
    **SWITCH_NODE_CLASS_MAPPINGS,
    **SCRIPT_NODE_CLASS_MAPPINGS,
    **GLOBAL_VAR_NODE_CLASS_MAPPINGS,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    **TIME_NODE_DISPLAY_NAME_MAPPINGS,
    **STRING_NODE_DISPLAY_NAME_MAPPINGS,
    **SWITCH_NODE_DISPLAY_NAME_MAPPINGS,
    **SCRIPT_NODE_DISPLAY_NAME_MAPPINGS,
    **GLOBAL_VAR_NODE_DISPLAY_NAME_MAPPINGS,
}

WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]


# ---------------------------------------------------------------------------
# CDN backup sync — runs once at import time in a background thread
# ---------------------------------------------------------------------------

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_WEB_DIR = os.path.join(_THIS_DIR, "web")
_BACKUPS_DIR = os.path.join(_WEB_DIR, "backups")
_MANIFEST_PATH = os.path.join(_BACKUPS_DIR, ".manifest.json")

_LOG_PREFIX = "[ComfyUI Simple Utility Nodes]"


def _sha256_of_bytes(data: bytes) -> str:
    """Return the hex SHA-256 digest of *data*."""
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _sha256_of_file(path: str) -> str | None:
    """Return the hex SHA-256 digest of a file, or None on error."""
    import hashlib
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _load_manifest() -> dict:
    """Load the backup manifest (filename → sha256 hex)."""
    import json
    try:
        with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save_manifest(manifest: dict) -> None:
    """Persist the backup manifest to disk."""
    import json
    try:
        with open(_MANIFEST_PATH, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
    except OSError as exc:
        logger.warning("%s Failed to write manifest: %s", _LOG_PREFIX, exc)


def _scan_cdn_urls() -> dict[str, str]:
    """Scan all .js and .html files under web/ for CDN URLs.

    Looks for URLs matching ``https://cdn.jsdelivr.net/...`` (and other
    common CDN hosts) inside the source files.  Returns a dict mapping
    ``{local_filename: cdn_url}``.  The local filename is derived from
    the last path component of the URL (e.g. ``katex.min.js``).
    """
    import re
    # Match common CDN URLs — jsdelivr, unpkg, cdnjs, skypack, esm.sh
    url_re = re.compile(
        r"""(https://(?:cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com|cdn\.skypack\.dev|esm\.sh)/[^\s"'`<>]+)"""
    )
    urls: dict[str, str] = {}
    for fname in os.listdir(_WEB_DIR):
        if not (fname.endswith(".js") or fname.endswith(".html")):
            continue
        fpath = os.path.join(_WEB_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        for match in url_re.finditer(content):
            url = match.group(1)
            # Derive local filename from the last path segment
            local_name = url.rstrip("/").rsplit("/", 1)[-1]
            if local_name:
                urls[local_name] = url
    return urls


def _sync_cdn_backups() -> None:
    """Check each discovered CDN resource against a local SHA-256 manifest
    and download / re-download as needed.

    Integrity logic (per file):
      1. If the local file is missing or empty → download.
      2. If the local file exists but its SHA-256 doesn't match the
         manifest (corrupted / partial write) → re-download.
      3. If the local file exists and its hash matches the manifest
         → skip (fast, no network request).

    After every successful download the manifest is updated on disk so
    that subsequent runs can verify integrity purely locally.

    This runs in a daemon thread so it never blocks ComfyUI startup.
    """
    import urllib.request
    import urllib.error

    os.makedirs(_BACKUPS_DIR, exist_ok=True)

    # Dynamically discover CDN URLs from our own JS/HTML source files
    cdn_urls = _scan_cdn_urls()
    if not cdn_urls:
        return

    logger.info(
        "%s Detected %d CDN resource(s) in JS/HTML files: %s",
        _LOG_PREFIX, len(cdn_urls), ", ".join(sorted(cdn_urls.keys())),
    )

    manifest = _load_manifest()
    manifest_dirty = False

    # Build an opener that respects system proxy settings (e.g. Windows
    # Internet Options / registry proxy).  Plain urllib.request.urlopen
    # only checks HTTP_PROXY / HTTPS_PROXY env-vars which are often not
    # set even when a proxy is active system-wide (Clash, v2ray, etc.).
    proxy_handler = urllib.request.ProxyHandler()   # auto-detects system proxy
    opener = urllib.request.build_opener(proxy_handler)

    for filename, url in cdn_urls.items():
        local_path = os.path.join(_BACKUPS_DIR, filename)

        # ── Fast local integrity check ──
        need_download = False
        reason = ""

        if not os.path.isfile(local_path) or os.path.getsize(local_path) == 0:
            need_download = True
            reason = "missing or empty"
        elif filename not in manifest:
            # File exists but no manifest entry — first run after adding
            # manifest support.  Hash the existing file and record it;
            # no download needed unless the hash is suspiciously wrong
            # (we trust it on first migration).
            file_hash = _sha256_of_file(local_path)
            if file_hash:
                manifest[filename] = file_hash
                manifest_dirty = True
                logger.info(
                    "%s Registered existing backup in manifest: %s (sha256=%s…)",
                    _LOG_PREFIX, filename, file_hash[:12],
                )
            # Don't download — trust the existing file for migration
        else:
            # Both file and manifest entry exist — verify integrity
            file_hash = _sha256_of_file(local_path)
            if file_hash != manifest.get(filename):
                need_download = True
                reason = (
                    f"integrity mismatch (expected {manifest[filename][:12]}…, "
                    f"got {file_hash[:12] if file_hash else 'read-error'}…)"
                )

        if not need_download:
            continue

        # ── Download with retries ──
        last_exc = None
        for attempt in range(1, 4):          # up to 3 attempts
            try:
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "ComfyUI-Simple-Utility-Nodes/1.0")
                with opener.open(req, timeout=15) as resp:
                    data = resp.read()

                data_hash = _sha256_of_bytes(data)

                with open(local_path, "wb") as f:
                    f.write(data)

                manifest[filename] = data_hash
                manifest_dirty = True

                logger.info(
                    "%s Downloaded CDN backup: %s (%d bytes, sha256=%s…) [%s]",
                    _LOG_PREFIX, filename, len(data), data_hash[:12], reason,
                )
                break   # success — move to next file

            except (urllib.error.URLError, OSError, ValueError) as exc:
                last_exc = exc
                if attempt < 3:
                    import time
                    time.sleep(2 * attempt)     # back-off: 2s, 4s
                    continue
            except Exception as exc:
                last_exc = exc
                break           # unexpected error — don't retry
        else:
            # All 3 attempts failed
            logger.warning(
                "%s CDN unreachable for %s after 3 attempts — "
                "backup not available. Markdown rendering may fail "
                "if CDN is also unreachable from the browser. (%s)",
                _LOG_PREFIX, filename, last_exc,
            )
            continue

        if last_exc is not None and not os.path.isfile(local_path):
            logger.warning(
                "%s Unexpected error downloading %s: %s",
                _LOG_PREFIX, filename, last_exc,
            )

    # Persist manifest if anything changed
    if manifest_dirty:
        _save_manifest(manifest)


# Run in a background daemon thread so startup isn't blocked
threading.Thread(target=_sync_cdn_backups, daemon=True).start()
