"""Switch-related custom nodes for ComfyUI."""

import json
import os
from typing import Any, Tuple

from .utils import distribute_to_outputs, select_from_inputs, UNCONNECTED

# Load settings
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)


class SimpleSwitchWithRandomMode:
    """Select one input from multiple inputs, optionally randomly."""
    
    CATEGORY = "Simple Utility ⛏️/Switch"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("output",)
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleSwitchWithRandomMode"]
        inputs = {
            "required": {
                "input_num": ("INT", {
                    "default": settings["default_input_num"],
                    "min": settings["min_num"],
                    "max": settings["max_num"],
                    "step": 1
                }),
                "selected_index": ("INT", {
                    "default": settings["default_selected_index"],
                    "min": 1,
                    "max": settings["max_num"],
                    "step": 1
                }),
                "select_random": ("BOOLEAN", {
                    "default": settings["default_select_random"],
                    "label_on": "Yes",
                    "label_off": "No"
                }),
            },
            "optional": {}
        }
        
        # Add dynamic inputs
        for i in range(1, settings["max_num"] + 1):
            inputs["optional"][f"input_{i}"] = ("*",)
        
        return inputs
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute if random mode is enabled."""
        if kwargs.get("select_random", False):
            return float("nan")
        return ""
    
    def execute(
        self,
        input_num: int,
        selected_index: int,
        select_random: bool,
        **kwargs
    ) -> Tuple[Any]:
        """Execute the switch selection."""
        # Collect inputs based on input_num
        # Use UNCONNECTED sentinel to distinguish between unconnected and connected-with-None
        inputs = []
        for i in range(1, input_num + 1):
            key = f"input_{i}"
            if key in kwargs:
                inputs.append(kwargs[key])
            else:
                inputs.append(UNCONNECTED)
        
        result = select_from_inputs(inputs, selected_index, select_random, input_num)
        return (result,)


class SimpleInversedSwitchWithRandomMode:
    """Distribute one input to one of multiple outputs, optionally randomly."""
    
    CATEGORY = "Simple Utility ⛏️/Switch"
    FUNCTION = "execute"
    OUTPUT_NODE = True
    
    # Get settings for this node
    _settings = SETTINGS["SimpleInversedSwitchWithRandomMode"]
    
    # Dynamic return types - maximum possible outputs
    RETURN_TYPES = tuple(["*"] * _settings["max_num"])
    RETURN_NAMES = tuple([f"output_{i}" for i in range(1, _settings["max_num"] + 1)])
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleInversedSwitchWithRandomMode"]
        return {
            "required": {
                "anything": ("*",),
                "output_num": ("INT", {
                    "default": settings["default_output_num"],
                    "min": settings["min_num"],
                    "max": settings["max_num"],
                    "step": 1
                }),
                "selected_index": ("INT", {
                    "default": settings["default_selected_index"],
                    "min": 1,
                    "max": settings["max_num"],
                    "step": 1
                }),
                "select_random": ("BOOLEAN", {
                    "default": settings["default_select_random"],
                    "label_on": "Yes",
                    "label_off": "No"
                }),
            }
        }
    
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute if random mode is enabled."""
        if kwargs.get("select_random", False):
            return float("nan")
        return ""
    
    def execute(
        self,
        anything: Any,
        output_num: int,
        selected_index: int,
        select_random: bool
    ) -> Tuple:
        """Execute the inversed switch distribution."""
        # Clamp selected_index to valid range
        clamped_index = max(1, min(selected_index, output_num))
        
        outputs, _ = distribute_to_outputs(
            anything, output_num, clamped_index, select_random
        )
        
        # Pad outputs to max_num for consistent return
        max_num = SETTINGS["SimpleInversedSwitchWithRandomMode"]["max_num"]
        while len(outputs) < max_num:
            outputs.append(None)
        
        return tuple(outputs)


# Node class mappings
NODE_CLASS_MAPPINGS = {
    "SimpleSwitchWithRandomMode": SimpleSwitchWithRandomMode,
    "SimpleInversedSwitchWithRandomMode": SimpleInversedSwitchWithRandomMode,
}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleSwitchWithRandomMode": "⛏️ Simple Switch with Random Mode",
    "SimpleInversedSwitchWithRandomMode": "⛏️ Simple Inversed Switch with Random Mode",
}
