"""Utility functions for string-related nodes."""

import codecs
import os
from typing import Tuple


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
