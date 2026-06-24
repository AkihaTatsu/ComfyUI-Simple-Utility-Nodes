"""Utility functions for string-related nodes."""

import codecs
import os
import re
from typing import List, Optional, Tuple


def append_string(original: str, to_append: str, at_beginning: bool) -> str:
    """
    Append a string to another string.
    
    Args:
        original: The original string.
        to_append: The string to append.
        at_beginning: If True, append at the beginning; otherwise at the end.
        
    Returns:
        The new appended string.
    """
    if at_beginning:
        return to_append + original
    else:
        return original + to_append


def wrap_string(original: str, prefix: str, suffix: str) -> str:
    """
    Wrap a string with prefix and suffix.
    
    Args:
        original: The original string.
        prefix: The string to prepend.
        suffix: The string to append.
        
    Returns:
        The wrapped string.
    """
    return prefix + original + suffix


def sever_string(
    original: str,
    delimiter: str,
    index_selector: str,
    delimiter_index: int
) -> Tuple[str, str]:
    """
    Sever a string by a delimiter.
    
    Args:
        original: The original string.
        delimiter: The delimiter to use for severing.
        index_selector: "first", "last", or "decided by index".
        delimiter_index: The index of the delimiter to use (0-based).
        
    Returns:
        A tuple of two strings severed by the delimiter.
    """
    if not delimiter or delimiter not in original:
        return original, ""
    
    # Find all occurrences of the delimiter
    parts = original.split(delimiter)
    
    if len(parts) <= 1:
        return original, ""
    
    # Determine which delimiter to use
    num_delimiters = len(parts) - 1
    
    if index_selector == "first":
        split_index = 0
    elif index_selector == "last":
        split_index = num_delimiters - 1
    else:  # "decided by index"
        if delimiter_index < 0 or delimiter_index >= num_delimiters:
            return original, ""
        split_index = delimiter_index
    
    # Reconstruct the two parts
    first_part = delimiter.join(parts[:split_index + 1])
    second_part = delimiter.join(parts[split_index + 1:])
    
    return first_part, second_part


def get_working_dir_path() -> str:
    """Return a normalized absolute working directory path.

    Falls back to the current user's home directory when the process
    working directory is unavailable.
    """
    try:
        cwd = os.getcwd()
    except OSError:
        cwd = os.path.expanduser("~")

    return os.path.normpath(os.path.abspath(cwd))


def get_working_dir_display() -> str:
    """Return the display text for current working directory."""
    return f"Working Dir: {get_working_dir_path()}"


def resolve_file_path(file_path: str) -> str:
    """Resolve a user-supplied file path against current working directory."""
    normalized = os.path.expandvars(os.path.expanduser(file_path.strip()))
    if not normalized:
        raise ValueError("File path cannot be empty.")

    if os.path.isabs(normalized):
        return os.path.normpath(normalized)

    return os.path.normpath(os.path.join(get_working_dir_path(), normalized))


def validate_text_encoding(encoding: str) -> str:
    """Validate and normalize a text encoding name."""
    try:
        info = codecs.lookup(encoding)
    except LookupError as exc:
        raise ValueError(f"Unknown encoding: {encoding}") from exc

    if not getattr(info, "_is_text_encoding", False):
        raise ValueError(f"Encoding is not a text encoding: {encoding}")

    if info.name == "undefined":
        raise ValueError("The 'undefined' codec cannot be used for text file I/O.")

    return info.name


def load_string_from_file(file_path: str, encoding: str) -> str:
    """Load a string from a text file using the given encoding."""
    resolved_path = resolve_file_path(file_path)
    normalized_encoding = validate_text_encoding(encoding)

    with open(resolved_path, "r", encoding=normalized_encoding) as f:
        return f.read()


def save_string_to_file(string: str, file_path: str, encoding: str) -> str:
    """Save a string to a text file and return the resolved absolute path."""
    resolved_path = resolve_file_path(file_path)
    normalized_encoding = validate_text_encoding(encoding)

    parent_dir = os.path.dirname(resolved_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    with open(resolved_path, "w", encoding=normalized_encoding) as f:
        f.write(string)

    return resolved_path


# ---------------------------------------------------------------------------
# Power Prompt helpers (lora / embedding parsing)
#
# Ported from rgthree-comfy's power_prompt_utils.py so this package does not
# depend on rgthree being installed. The text box is the single source of
# truth at run time; these helpers only read it, they never modify it.
# ---------------------------------------------------------------------------

# Matches <lora:name> or <lora:name:strength> (strength may be negative/decimal).
_LORA_TAG_PATTERN = re.compile(r"<lora:([^:>]*?)(?::(-?\d*(?:\.\d*)?))?>")

# Matches an embedding reference the same way ComfyUI's CLIP tokenizer does
# (comfy/sd1_clip.py): the "embedding:" marker is only recognised at the start
# of the prompt or right after whitespace, and the name is the first
# whitespace-delimited token that follows. ComfyUI does `name.split()[0]`, so
# names containing spaces are NOT addressable inline — only the leading token
# is used — and we mirror that exactly here.
_EMBEDDING_PATTERN = re.compile(r"(?:^|\s)embedding:(\S+)")


def get_lora_by_filename(file_path: str, lora_paths: Optional[List[str]] = None) -> Optional[str]:
    """Resolve a lora reference to a real filename from the loras folder.

    Tries, in order: exact path, path-without-extension, basename,
    basename-without-extension, and finally a fuzzy substring match.
    Returns the matching entry from ``folder_paths.get_filename_list('loras')``
    or ``None`` when nothing matches.
    """
    import folder_paths

    if lora_paths is None:
        lora_paths = folder_paths.get_filename_list("loras")

    if file_path in lora_paths:
        return file_path

    lora_paths_no_ext = [os.path.splitext(x)[0] for x in lora_paths]

    # Exact path, but without the extension.
    if file_path in lora_paths_no_ext:
        return lora_paths[lora_paths_no_ext.index(file_path)]

    # Same, forcing the input to be without extension.
    file_path_no_ext = os.path.splitext(file_path)[0]
    if file_path_no_ext in lora_paths_no_ext:
        return lora_paths[lora_paths_no_ext.index(file_path_no_ext)]

    # Just the filename, without any directories.
    lora_filenames = [os.path.basename(x) for x in lora_paths]
    if file_path in lora_filenames:
        return lora_paths[lora_filenames.index(file_path)]

    file_path_filename = os.path.basename(file_path)
    if file_path_filename in lora_filenames:
        return lora_paths[lora_filenames.index(file_path_filename)]

    # Filename without extension.
    lora_filenames_no_ext = [os.path.splitext(os.path.basename(x))[0] for x in lora_paths]
    if file_path in lora_filenames_no_ext:
        return lora_paths[lora_filenames_no_ext.index(file_path)]

    file_path_filename_no_ext = os.path.splitext(os.path.basename(file_path))[0]
    if file_path_filename_no_ext in lora_filenames_no_ext:
        return lora_paths[lora_filenames_no_ext.index(file_path_filename_no_ext)]

    # Super fuzzy: input appears anywhere inside a known path.
    for index, lora_path in enumerate(lora_paths):
        if file_path in lora_path:
            return lora_paths[index]

    return None


def parse_loras_from_text(text: str) -> List[dict]:
    """Collect ``<lora:name:strength>`` tags from text without modifying it.

    Returns a list of ``{"lora": <resolved filename>, "strength": float}``.
    Tags with a strength of 0 or that cannot be resolved to a real file are
    skipped.
    """
    import folder_paths

    lora_paths = folder_paths.get_filename_list("loras")
    loras: List[dict] = []
    for match in _LORA_TAG_PATTERN.findall(text or ""):
        tag_path = match[0]
        strength = float(match[1]) if match[1] else 1.0
        if strength == 0:
            continue
        resolved = get_lora_by_filename(tag_path, lora_paths)
        if resolved is None:
            continue
        loras.append({"lora": resolved, "strength": strength})
    return loras


def extract_embedding_text(text: str) -> str:
    """Extract only the ``embedding:name`` references from text.

    The references are resolved exactly like ComfyUI's CLIP tokenizer: each
    name is the first whitespace-delimited token after the marker, with any
    surrounding commas stripped (ComfyUI does ``name.split()[0]`` and falls
    back to ``name.strip(',')``). The matches are joined by ", " so they can be
    re-encoded by a standard CLIP text-encode node and resolve identically to
    the full prompt. Returns an empty string when no embeddings are present.
    """
    refs = []
    for token in _EMBEDDING_PATTERN.findall(text or ""):
        name = token.strip(",")
        if name:
            refs.append(f"embedding:{name}")
    return ", ".join(refs)
