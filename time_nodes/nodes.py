"""Time-related custom nodes for ComfyUI."""

import json
import os
from datetime import datetime
from typing import Any

from .utils import (
    create_or_reset_timer,
    format_time_output,
    record_timer,
)

# Load settings
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


class SimpleTimer:
    """A timer for recording the running time of the workflow."""
    
    CATEGORY = "Simple Utility/Time"
    FUNCTION = "execute"
    RETURN_TYPES = ("*", "STRING")
    RETURN_NAMES = ("anything", "time")
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleTimer"]
        return {
            "required": {
                "anything": ("*",),
                "timer_name": ("STRING", {
                    "default": settings["default_timer_name"],
                    "multiline": False
                }),
                "mode": (settings["timer_modes"], {
                    "default": settings["default_mode"]
                }),
                "display_format": (settings["display_formats"], {
                    "default": settings["default_display_format"]
                }),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute to get accurate timing."""
        return float("nan")
    
    def execute(
        self,
        anything: Any,
        timer_name: str,
        mode: str,
        display_format: str
    ) -> dict:
        """Execute the timer node."""
        
        if mode == "start/reset":
            create_or_reset_timer(timer_name)
            result = format_time_output(0, display_format)
        
        elif mode == "total time record":
            total_time, _ = record_timer(timer_name)
            result = format_time_output(total_time, display_format)
        
        elif mode == "since last record":
            _, time_since_last = record_timer(timer_name)
            result = format_time_output(time_since_last, display_format)
        
        else:
            result = "Invalid mode"
        
        return {
            "ui": {"text": [result]},
            "result": (anything, result)
        }


class SimpleCurrentDatetime:
    """Retrieve the current time when running through this node."""
    
    CATEGORY = "Simple Utility/Time"
    FUNCTION = "execute"
    RETURN_TYPES = ("*", "STRING")
    RETURN_NAMES = ("anything", "datetime_string")
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleCurrentDatetime"]
        return {
            "required": {
                "anything": ("*",),
                "time_format": (settings["datetime_formats"], {
                    "default": settings["default_datetime_format"]
                }),
                "use_custom_format": ("BOOLEAN", {
                    "default": settings["default_use_custom_format"],
                    "label_on": "Yes",
                    "label_off": "No"
                }),
                "custom_format": ("STRING", {
                    "default": settings["default_custom_format"],
                    "multiline": False
                }),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute to get current time."""
        return float("nan")
    
    def execute(
        self,
        anything: Any,
        time_format: str,
        use_custom_format: bool,
        custom_format: str
    ) -> dict:
        """Execute the current datetime node."""
        
        now = datetime.now()
        
        # Determine which format to use
        format_str = custom_format if use_custom_format else time_format
        
        # Handle special formats
        if format_str == "Unix Timestamp":
            result = str(int(now.timestamp()))
        elif format_str == "Unix Timestamp (ms)":
            result = str(int(now.timestamp() * 1000))
        else:
            try:
                result = now.strftime(format_str)
            except Exception as e:
                result = f"Format error: {str(e)}"
        
        return {
            "ui": {"text": [result]},
            "result": (anything, result)
        }


# Node class mappings
NODE_CLASS_MAPPINGS = {
    "SimpleTimer": SimpleTimer,
    "SimpleCurrentDatetime": SimpleCurrentDatetime,
}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleTimer": "Simple Timer",
    "SimpleCurrentDatetime": "Simple Current Datetime",
}
