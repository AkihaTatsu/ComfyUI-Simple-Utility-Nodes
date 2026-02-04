"""Script-related custom nodes for ComfyUI."""

import json
import os
from typing import Any

from .utils import execute_python_script, print_to_console

# Load settings
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


class SimplePrintToConsole:
    """Print a message to the console with optional rich formatting and timestamp."""
    
    CATEGORY = "Simple Utility ⛏️/Script"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimplePrintToConsole"]
        return {
            "required": {
                "anything": ("*",),
                "is_rich_format": ("BOOLEAN", {
                    "default": settings["default_is_rich_format"],
                    "label_on": "Yes",
                    "label_off": "No"
                }),
                "with_timestamp": ("BOOLEAN", {
                    "default": settings["default_with_timestamp"],
                    "label_on": "Yes",
                    "label_off": "No"
                }),
                "message": ("STRING", {
                    "default": settings["default_message"],
                    "multiline": True
                }),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute to print message."""
        return float("nan")
    
    def execute(
        self,
        anything: Any,
        is_rich_format: bool,
        with_timestamp: bool,
        message: str
    ) -> dict:
        """Execute the print to console operation."""
        output_message = print_to_console(message, is_rich_format, with_timestamp)
        
        return {
            "ui": {"text": [output_message]},
            "result": (anything,)
        }


class SimplePythonScript:
    """Execute a Python script in an isolated environment."""
    
    CATEGORY = "Simple Utility ⛏️/Script"
    FUNCTION = "execute"
    RETURN_TYPES = ("*", "*")
    RETURN_NAMES = ("passthrough", "RESULT")
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimplePythonScript"]
        return {
            "required": {
                "anything": ("*",),
                "script": ("STRING", {
                    "default": settings["default_script"],
                    "multiline": True
                }),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute the script."""
        return float("nan")
    
    def execute(
        self,
        anything: Any,
        script: str
    ) -> dict:
        """Execute the Python script."""
        result, error = execute_python_script(script, anything)
        
        if error:
            raise RuntimeError(f"Script execution failed:\n{error}")
        
        return {
            "ui": {"text": [f"Script executed successfully. RESULT: {repr(result)}"]},
            "result": (anything, result)
        }


# Node class mappings
NODE_CLASS_MAPPINGS = {
    "SimplePrintToConsole": SimplePrintToConsole,
    "SimplePythonScript": SimplePythonScript,
}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimplePrintToConsole": "⛏️ Simple Print to Console",
    "SimplePythonScript": "⛏️ Simple Python Script",
}
