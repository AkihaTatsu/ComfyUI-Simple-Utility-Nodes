"""Utility functions and classes for time-related nodes."""

from time import perf_counter_ns
from typing import Dict, Tuple

# Global timer storage
_TIMERS: Dict[str, Dict[str, int]] = {}


def create_or_reset_timer(timer_name: str) -> int:
    """
    Create a new timer or reset an existing one.
    
    Args:
        timer_name: The name of the timer.
        
    Returns:
        The current time in nanoseconds when the timer was created/reset.
    """
    current_time = perf_counter_ns()
    _TIMERS[timer_name] = {
        "start_time": current_time,
        "last_record_time": current_time
    }
    return current_time


def record_timer(timer_name: str) -> Tuple[int, int]:
    """
    Record the current time for a timer.
    
    Args:
        timer_name: The name of the timer.
        
    Returns:
        A tuple of (total_time_ns, time_since_last_record_ns).
        
    Raises:
        ValueError: If the timer doesn't exist (wasn't started/reset first).
    """
    current_time = perf_counter_ns()
    
    timer = _TIMERS.get(timer_name)
    if timer is None:
        # Timer doesn't exist, raise an error
        raise ValueError(
            f"Timer '{timer_name}' has not been started. "
            f"Please use mode 'start/reset' first to initialize the timer."
        )
    
    total_time = current_time - timer["start_time"]
    time_since_last = current_time - timer["last_record_time"]
    timer["last_record_time"] = current_time
    
    return total_time, time_since_last


def format_time_output(time_ns: int, display_format: str) -> str:
    """
    Format time in nanoseconds according to the specified display format.
    
    Args:
        time_ns: Time in nanoseconds.
        display_format: The format to use for display.
        
    Returns:
        Formatted time string.
    """
    if display_format == "number in nanoseconds":
        return str(time_ns)
    
    # Convert to seconds (accurate float)
    time_seconds = time_ns / 1_000_000_000
    
    if display_format == "number in seconds":
        return str(time_seconds)
    
    # Calculate hours, minutes, seconds
    hours = int(time_seconds // 3600)
    remaining = time_seconds % 3600
    minutes = int(remaining // 60)
    seconds = remaining % 60
    
    if display_format == "%H:%M:%S.%f":
        parts = []
        if hours > 0:
            parts.append(f"{hours:02d}")
        if hours > 0 or minutes > 0:
            parts.append(f"{minutes:02d}")
        parts.append(f"{seconds:06.3f}")
        return ":".join(parts)
    
    elif display_format == "text description":
        parts = []
        if hours > 0:
            unit = "hours" if hours > 1 else "hour"
            parts.append(f"{hours} {unit}")
        if minutes > 0:
            unit = "minutes" if minutes > 1 else "minute"
            parts.append(f"{minutes} {unit}")
        # Always show seconds
        unit = "seconds" if seconds > 1 else "second"
        parts.append(f"{seconds:.3f} {unit}")
        return ", ".join(parts)
    
    return str(time_seconds)
