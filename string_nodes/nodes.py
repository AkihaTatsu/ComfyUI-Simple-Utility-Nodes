"""String-related custom nodes for ComfyUI."""

import json
import os
from typing import Any, Tuple

from .utils import append_string, sever_string, wrap_string

# Load settings
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


class SimpleStringAppending:
    """Append a string to another string."""
    
    CATEGORY = "Simple Utility ⛏️/String"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("string",)
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleStringAppending"]
        return {
            "required": {
                "string": ("STRING", {"forceInput": True}),
                "append_position": ("BOOLEAN", {
                    "default": settings["default_append_position"],
                    "label_on": "at the beginning",
                    "label_off": "at the end"
                }),
                "text_to_append": ("STRING", {
                    "default": settings["default_append_text"],
                    "multiline": True
                }),
            }
        }
    
    def execute(
        self,
        string: str,
        append_position: bool,
        text_to_append: str
    ) -> Tuple[str]:
        """Execute the string append operation."""
        result = append_string(string, text_to_append, append_position)
        return (result,)


class SimpleStringWrapping:
    """Wrap a string with prefix and suffix."""
    
    CATEGORY = "Simple Utility ⛏️/String"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("string",)
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleStringWrapping"]
        return {
            "required": {
                "string": ("STRING", {"forceInput": True}),
                "prefix": ("STRING", {
                    "default": settings["default_prefix_text"],
                    "multiline": True
                }),
                "suffix": ("STRING", {
                    "default": settings["default_suffix_text"],
                    "multiline": True
                }),
            }
        }
    
    def execute(
        self,
        string: str,
        prefix: str,
        suffix: str
    ) -> Tuple[str]:
        """Execute the string wrapping operation."""
        result = wrap_string(string, prefix, suffix)
        return (result,)


class SimpleStringSevering:
    """Sever a string by a delimiter."""
    
    CATEGORY = "Simple Utility ⛏️/String"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("first_part", "second_part")
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleStringSevering"]
        return {
            "required": {
                "string": ("STRING", {"forceInput": True}),
                "delimiter": ("STRING", {
                    "default": settings["default_delimiter"],
                    "multiline": False
                }),
                "index_selector": (settings["index_selector_options"], {
                    "default": settings["default_index_selector"]
                }),
                "delimiter_index": ("INT", {
                    "default": settings["default_delimiter_index"],
                    "min": 0,
                    "max": 1000,
                    "step": 1
                }),
            }
        }
    
    def execute(
        self,
        string: str,
        delimiter: str,
        index_selector: str,
        delimiter_index: int
    ) -> Tuple[str, str]:
        """Execute the string severing operation."""
        first_part, second_part = sever_string(
            string, delimiter, index_selector, delimiter_index
        )
        return (first_part, second_part)


class SimpleMarkdownString:
    """A markdown note node with text editing and rendering capabilities that outputs a string."""
    
    CATEGORY = "Simple Utility ⛏️/String"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("string",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleMarkdownString"]
        return {
            "required": {
                "text": ("STRING", {
                    "default": settings["default_text"],
                    "multiline": True
                }),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute to ensure UI updates."""
        return float("nan")
    
    def execute(self, text: str) -> dict:
        """Execute and return the markdown text as a string."""
        return {
            "ui": {"text": [text]},
            "result": (text,)
        }


class SimpleMarkdownStringDisplay:
    """Display an input string as markdown-rendered rich text or raw text."""
    
    CATEGORY = "Simple Utility ⛏️/String"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleMarkdownStringDisplay"]
        return {
            "required": {
                "string": ("STRING", {"forceInput": True}),
                "display_mode": ("BOOLEAN", {
                    "default": settings["default_display_mode"],
                    "label_on": "raw text",
                    "label_off": "markdown"
                }),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute to ensure UI updates."""
        return float("nan")
    
    def execute(self, string: str, display_mode: bool) -> dict:
        """Execute and return the string with display mode info."""
        return {
            "ui": {"text": [string], "display_raw": [display_mode]},
            "result": (string,)
        }


# Node class mappings
NODE_CLASS_MAPPINGS = {
    "SimpleStringAppending": SimpleStringAppending,
    "SimpleStringWrapping": SimpleStringWrapping,
    "SimpleStringSevering": SimpleStringSevering,
    "SimpleMarkdownString": SimpleMarkdownString,
    "SimpleMarkdownStringDisplay": SimpleMarkdownStringDisplay,
}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleStringAppending": "⛏️ Simple String Appending",
    "SimpleStringWrapping": "⛏️ Simple String Wrapping",
    "SimpleStringSevering": "⛏️ Simple String Severing",
    "SimpleMarkdownString": "⛏️ Simple Markdown String",
    "SimpleMarkdownStringDisplay": "⛏️ Simple Markdown String Display",
}
