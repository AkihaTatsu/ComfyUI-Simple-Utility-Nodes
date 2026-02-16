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
    """Execute a Python script in an isolated environment with dynamic inputs/outputs."""
    
    CATEGORY = "Simple Utility ⛏️/Script"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    
    # Get settings for this node
    _settings = SETTINGS["SimplePythonScript"]
    
    # Dynamic return types - maximum possible outputs
    RETURN_TYPES = tuple(["*"] * _settings["max_num"])
    RETURN_NAMES = tuple([f"OUTPUT{i}" for i in range(1, _settings["max_num"] + 1)])
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimplePythonScript"]
        inputs = {
            "required": {
                "input_num": ("INT", {
                    "default": settings["default_input_num"],
                    "min": settings["min_num"],
                    "max": settings["max_num"],
                    "step": 1
                }),
                "output_num": ("INT", {
                    "default": settings["default_output_num"],
                    "min": settings["min_num"],
                    "max": settings["max_num"],
                    "step": 1
                }),
                "script": ("STRING", {
                    "default": settings["default_script"],
                    "multiline": True
                }),
            },
            "optional": {}
        }
        
        # Add dynamic inputs
        for i in range(1, settings["max_num"] + 1):
            inputs["optional"][f"INPUT{i}"] = ("*",)
        
        return inputs
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute the script."""
        return float("nan")
    
    def execute(
        self,
        input_num: int,
        output_num: int,
        script: str,
        **kwargs
    ) -> dict:
        """Execute the Python script with dynamic inputs/outputs."""
        # Collect inputs based on input_num
        input_values = {}
        for i in range(1, input_num + 1):
            key = f"INPUT{i}"
            if key in kwargs:
                input_values[key] = kwargs[key]
            else:
                input_values[key] = None
        
        result_dict, error = execute_python_script(script, input_values, output_num)
        
        if error:
            raise RuntimeError(f"Script execution failed:\n{error}")
        
        # Build output tuple
        max_num = SETTINGS["SimplePythonScript"]["max_num"]
        outputs = []
        for i in range(1, max_num + 1):
            if i <= output_num:
                outputs.append(result_dict.get(f"OUTPUT{i}", None))
            else:
                outputs.append(None)
        
        # Build UI message
        output_summaries = []
        for i in range(1, output_num + 1):
            output_summaries.append(f"OUTPUT{i}: {repr(result_dict.get(f'OUTPUT{i}', None))}")
        ui_text = "Script executed successfully. " + ", ".join(output_summaries)
        
        return {
            "ui": {"text": [ui_text]},
            "result": tuple(outputs)
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
