"""Utility functions for script-related nodes."""

import sys
import traceback
from datetime import datetime
from io import StringIO
from typing import Any, Dict, Optional, Tuple

# Try to import rich, but make it optional
try:
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


def get_timestamp() -> str:
    """
    Get a logging-style timestamp.
    
    Returns:
        A formatted timestamp string.
    """
    now = datetime.now()
    return now.strftime("[%Y-%m-%d %H:%M:%S.%f")[:-3] + "]"


def print_to_console(
    message: str,
    is_rich_format: bool = False,
    with_timestamp: bool = False
) -> str:
    """
    Print a message to the console.
    
    Args:
        message: The message to print.
        is_rich_format: If True, interpret the message as rich markup.
        with_timestamp: If True, prepend a timestamp.
        
    Returns:
        The printed message (for display in UI).
    """
    if is_rich_format and RICH_AVAILABLE:
        # Use sys.__stdout__ to get the original stdout before any redirections
        # This bypasses ComfyUI's output capture
        original_stdout = getattr(sys, '__stdout__', sys.stdout) or sys.stdout
        
        # Use rich console for formatted output with explicit color support
        console = Console(
            force_terminal=True,
            file=original_stdout,
            color_system="truecolor",
            legacy_windows=False,
            no_color=False,
        )
        
        if with_timestamp:
            timestamp = get_timestamp()
            # Combine timestamp and message in one print call for consistency
            combined = f"[dim]{timestamp}[/dim] {message}"
            console.print(combined, markup=True, highlight=False)
            output_message = f"{timestamp} {message}"
        else:
            console.print(message, markup=True, highlight=False)
            output_message = message
        
        # Force flush to ensure output appears immediately
        original_stdout.flush()
    else:
        # Plain text output
        if with_timestamp:
            timestamp = get_timestamp()
            output_message = f"{timestamp} {message}"
        else:
            output_message = message
        
        # Use sys.__stdout__ to bypass any redirections
        original_stdout = getattr(sys, '__stdout__', sys.stdout) or sys.stdout
        print(output_message, file=original_stdout, flush=True)
    
    return output_message


def execute_python_script(
    script: str,
    input_values: Dict[str, Any] = None,
    output_num: int = 1
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Execute a Python script in an isolated environment.
    
    Args:
        script: The Python script to execute.
        input_values: Dictionary of input values (INPUT1, INPUT2, ...) passed to the script.
        output_num: Number of outputs to collect (OUTPUT1, OUTPUT2, ...).
        
    Returns:
        A tuple of (dict of output values or None, error message or None).
    """
    # Create an isolated namespace for the script
    script_globals: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "__name__": "__script__",
        "__doc__": None,
    }
    
    # Inject input variables
    if input_values:
        script_globals.update(input_values)
    
    script_locals: Dict[str, Any] = {}
    
    # Capture stdout and stderr
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured_stdout = StringIO()
    captured_stderr = StringIO()
    
    try:
        sys.stdout = captured_stdout
        sys.stderr = captured_stderr
        
        # Execute the script
        exec(script, script_globals, script_locals)
        
        # Collect output variables
        result_dict = {}
        for i in range(1, output_num + 1):
            output_key = f"OUTPUT{i}"
            result_dict[output_key] = script_locals.get(
                output_key, script_globals.get(output_key, None)
            )
        
        # Print any captured output
        stdout_content = captured_stdout.getvalue()
        stderr_content = captured_stderr.getvalue()
        
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
        if stdout_content:
            print(stdout_content, end="")
        if stderr_content:
            print(stderr_content, end="", file=sys.stderr)
        
        return result_dict, None
        
    except Exception as e:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
        # Get the full traceback
        error_message = traceback.format_exc()
        return None, error_message
