from __future__ import annotations

import logging
import os
import platform
from typing import Iterable


logger = logging.getLogger(__name__)

_LOG_PREFIX = "[ComfyUI Simple Utility Nodes][autofix]"
_AUTOFIX_APPLIED = False


def _ordered_unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _strip_known_folder_prefix(path_value: str, folder_name: str | None, map_legacy_fn) -> str:
    if not folder_name:
        return path_value

    folder_candidates = [folder_name]
    try:
        legacy = map_legacy_fn(folder_name)
        if isinstance(legacy, str) and legacy not in folder_candidates:
            folder_candidates.append(legacy)
    except Exception:
        pass

    lower_path = path_value.lower()
    for candidate in folder_candidates:
        prefix = f"{candidate}{os.sep}".lower()
        if lower_path.startswith(prefix):
            return path_value[len(candidate) + 1 :]

    return path_value


def _relative_path_candidates(
    raw_value: str,
    folder_name: str | None = None,
    map_legacy_fn=lambda value: value,
) -> list[str]:
    if not isinstance(raw_value, str):
        return []

    stripped = raw_value.strip().strip('"').strip("'")
    if not stripped:
        return []

    raw_variants = [
        raw_value,
        stripped,
        stripped.replace("\\", "/"),
        stripped.replace("/", "\\"),
    ]

    candidates: list[str] = []
    for variant in raw_variants:
        value = variant.strip().strip('"').strip("'")
        if not value:
            continue

        drive, tail = os.path.splitdrive(value)
        if drive:
            value = tail

        value = value.lstrip("/\\")
        value = value.replace("/", os.sep).replace("\\", os.sep)
        value = os.path.normpath(value)
        if value in ("", "."):
            continue

        value = _strip_known_folder_prefix(value, folder_name, map_legacy_fn)
        if value in ("", "."):
            continue

        candidates.append(value)

    return _ordered_unique(candidates)


def _canonical_pathish_value(value: str) -> str:
    normalized = value.strip().replace("\\", "/")
    while "//" in normalized:
        normalized = normalized.replace("//", "/")
    return normalized


def _match_combo_value_by_separator(raw_value: str, options: list) -> str | None:
    if not isinstance(raw_value, str):
        return None
    if "/" not in raw_value and "\\" not in raw_value:
        return None

    raw_canonical = _canonical_pathish_value(raw_value)
    for option in options:
        if not isinstance(option, str):
            continue
        if "/" not in option and "\\" not in option:
            continue
        if _canonical_pathish_value(option) == raw_canonical:
            return option

    return None


def _patch_folder_paths() -> bool:
    import folder_paths

    if getattr(folder_paths.get_full_path, "_simple_utility_autofix", False):
        return False

    original_get_full_path = folder_paths.get_full_path

    def patched_get_full_path(folder_name: str, filename: str) -> str | None:
        if not isinstance(filename, str):
            return original_get_full_path(folder_name, filename)

        candidates = _relative_path_candidates(
            filename,
            folder_name=folder_name,
            map_legacy_fn=getattr(folder_paths, "map_legacy", lambda value: value),
        )
        if not candidates:
            return original_get_full_path(folder_name, filename)

        for candidate in candidates:
            full_path = original_get_full_path(folder_name, candidate)
            if full_path is not None:
                return full_path

        return None

    def patched_get_full_path_or_raise(folder_name: str, filename: str) -> str:
        full_path = patched_get_full_path(folder_name, filename)
        if full_path is None:
            raise FileNotFoundError(
                f"Model in folder '{folder_name}' with filename '{filename}' not found."
            )
        return full_path

    patched_get_full_path._simple_utility_autofix = True
    patched_get_full_path_or_raise._simple_utility_autofix = True

    folder_paths.get_full_path = patched_get_full_path
    folder_paths.get_full_path_or_raise = patched_get_full_path_or_raise
    return True


def _patch_sd1_embedding_loader() -> bool:
    import comfy.sd1_clip as sd1_clip

    if getattr(sd1_clip.load_embed, "_simple_utility_autofix", False):
        return False

    original_load_embed = sd1_clip.load_embed

    def patched_load_embed(embedding_name, embedding_directory, embedding_size, embed_key=None):
        if not isinstance(embedding_name, str):
            return original_load_embed(
                embedding_name,
                embedding_directory,
                embedding_size,
                embed_key,
            )

        candidates = _relative_path_candidates(embedding_name)
        if not candidates:
            return original_load_embed(
                embedding_name,
                embedding_directory,
                embedding_size,
                embed_key,
            )

        for candidate in candidates:
            embedding = original_load_embed(
                candidate,
                embedding_directory,
                embedding_size,
                embed_key,
            )
            if embedding is not None:
                return embedding

        return None

    patched_load_embed._simple_utility_autofix = True
    sd1_clip.load_embed = patched_load_embed
    return True


def _patch_execution_validate_inputs() -> bool:
    import execution

    if getattr(execution.validate_inputs, "_simple_utility_autofix", False):
        return False

    original_validate_inputs = execution.validate_inputs

    def _normalize_combo_path_values(prompt, unique_id) -> int:
        node = prompt.get(unique_id)
        if not isinstance(node, dict):
            return 0

        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            return 0

        class_type = node.get("class_type")
        obj_class = execution.nodes.NODE_CLASS_MAPPINGS.get(class_type)
        if obj_class is None:
            return 0

        class_inputs = obj_class.INPUT_TYPES()
        if issubclass(obj_class, execution._ComfyNodeInternal):
            class_inputs, _, _ = execution._io.get_finalized_class_inputs(class_inputs, inputs)

        valid_inputs = set(class_inputs.get("required", {})).union(set(class_inputs.get("optional", {})))
        changes = 0

        for input_name in valid_inputs:
            if input_name not in inputs:
                continue

            wrapped = None
            current_value = inputs[input_name]
            if isinstance(current_value, dict) and "__value__" in current_value:
                wrapped = current_value
                current_value = current_value.get("__value__")

            if not isinstance(current_value, str):
                continue

            input_type, _, extra_info = execution.get_input_info(obj_class, input_name, class_inputs)
            if extra_info is None:
                continue

            if input_type == execution.io.Combo.io_type:
                combo_options = extra_info.get("options", [])
            elif isinstance(input_type, list):
                combo_options = input_type
            else:
                continue

            if current_value in combo_options:
                continue

            matched_value = _match_combo_value_by_separator(current_value, combo_options)
            if matched_value is None:
                continue

            if wrapped is not None:
                wrapped["__value__"] = matched_value
            else:
                inputs[input_name] = matched_value
            changes += 1

        return changes

    async def patched_validate_inputs(prompt_id, prompt, item, validated):
        try:
            _normalize_combo_path_values(prompt, item)
        except Exception as exc:
            logger.debug(
                "%s Failed to normalize combo path values for node %s: %s",
                _LOG_PREFIX,
                item,
                exc,
            )
        return await original_validate_inputs(prompt_id, prompt, item, validated)

    patched_validate_inputs._simple_utility_autofix = True
    execution.validate_inputs = patched_validate_inputs
    return True


def apply_model_path_autofix() -> None:
    global _AUTOFIX_APPLIED
    if _AUTOFIX_APPLIED:
        return

    logger.info(
        "%s Detected running system: system=%s, release=%s, machine=%s, os_name=%s, path_sep=%r",
        _LOG_PREFIX,
        platform.system() or "Unknown",
        platform.release() or "Unknown",
        platform.machine() or "Unknown",
        os.name,
        os.sep,
    )

    patchers = (
        _patch_folder_paths,
        _patch_sd1_embedding_loader,
        _patch_execution_validate_inputs,
    )

    active_patches = 0
    for patcher in patchers:
        try:
            if patcher():
                active_patches += 1
        except Exception as exc:
            logger.exception(
                "%s Failed to apply patch %s: %s",
                _LOG_PREFIX,
                patcher.__name__,
                exc,
            )

    logger.info(
        "%s Model-path autofix initialized with %d active patch(es).",
        _LOG_PREFIX,
        active_patches,
    )

    _AUTOFIX_APPLIED = True