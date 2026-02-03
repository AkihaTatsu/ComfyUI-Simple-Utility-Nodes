"""Utility functions for string-related nodes."""

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
