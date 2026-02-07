"""Global variable custom nodes for ComfyUI.

This module provides nodes for passing data between disconnected parts of a workflow
using named global variables. The Input node stores its INPUT value, and the Output
node retrieves it. This avoids the need for long connecting wires across the canvas.

The Input node also has a passthrough 'anything' input (like other utility nodes)
that passes data through unchanged, allowing it to be chained in workflows.

Key optimization: These nodes use a pass-through pattern similar to reroute nodes,
where the data is stored by reference rather than copied, minimizing RAM usage.

IMPORTANT NOTE ON EXECUTION ORDER:
ComfyUI uses topological sorting based on node connections to determine execution order.
Since these global variable nodes are designed to work WITHOUT physical connections,
we cannot guarantee execution order through normal means.

Solution: The Output node has a "trigger" input that should be connected to a node
that executes AFTER the corresponding Input node. This creates an implicit dependency.
If no trigger is connected, the Output node will try to find the value, but may fail
if the Input node hasn't executed yet.
"""

import json
import os
from typing import Any, Tuple, List

# Sentinel value to distinguish between "not connected" and "connected but not evaluated"
_MISSING = object()

# Load settings
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

# Global variable storage - stores references, not copies
# This is a module-level dictionary that persists across node executions
_GLOBAL_VARIABLES: dict[str, Any] = {}

# Track which variables have been set in the current execution
_EXECUTION_MARKER: dict[str, bool] = {}


def get_global_variable(name: str) -> Any:
    """Get a global variable by name.
    
    Args:
        name: The variable name.
        
    Returns:
        The stored value (by reference).
        
    Raises:
        KeyError: If the variable doesn't exist.
    """
    if name not in _GLOBAL_VARIABLES:
        raise KeyError(f"Global variable '{name}' not found. "
                      f"Make sure a 'Simple Global Variable Input' node with "
                      f"variable_name='{name}' exists and has been executed. "
                      f"Tip: Connect the 'trigger' input on the Output node to ensure "
                      f"the Input node executes first.")
    return _GLOBAL_VARIABLES[name]


def set_global_variable(name: str, value: Any) -> None:
    """Set a global variable by name.
    
    The value is stored by reference to minimize RAM usage.
    
    Args:
        name: The variable name.
        value: The value to store (stored by reference, not copied).
    """
    _GLOBAL_VARIABLES[name] = value
    _EXECUTION_MARKER[name] = True


def clear_global_variables() -> None:
    """Clear all global variables."""
    _GLOBAL_VARIABLES.clear()
    _EXECUTION_MARKER.clear()


def is_variable_set(name: str) -> bool:
    """Check if a variable has been set in this execution."""
    return name in _EXECUTION_MARKER


def list_global_variables() -> list[str]:
    """List all defined global variable names."""
    return list(_GLOBAL_VARIABLES.keys())


class SimpleGlobalVariableInput:
    """Store a value in a named global variable.
    
    This node accepts an INPUT value and stores it in a global variable with
    the specified name. The data is stored by reference, not copied, to minimize
    RAM usage (similar to reroute node optimization).
    
    Additionally, it has a passthrough 'anything' input (like other utility nodes)
    that passes data through unchanged, allowing it to be chained in workflows.
    
    Use this with 'Simple Global Variable Output' to pass data between
    disconnected parts of your workflow without long connecting wires.
    """
    
    CATEGORY = "Simple Utility ⛏️/Global Variable"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("passthrough",)
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleGlobalVariableInput"]
        return {
            "required": {
                "INPUT": ("*",),
                "variable_name": ("STRING", {
                    "default": settings["default_variable_name"],
                    "multiline": False,
                }),
            },
            "optional": {
                "anything": ("*",),
            },
        }
    
    @classmethod
    def VALIDATE_INPUTS(cls, INPUT, variable_name, anything=None):
        """Validate that variable_name is not empty."""
        if not variable_name or not variable_name.strip():
            return "Variable name cannot be empty."
        return True
    
    def execute(self, INPUT: Any, variable_name: str, anything: Any = None) -> Tuple[Any]:
        """Store the INPUT value in the global variable and pass through anything.
        
        The INPUT value is stored by reference to minimize RAM usage.
        This is the same optimization used by reroute nodes.
        The 'anything' input is passed through unchanged (or None if not connected).
        """
        # Store INPUT by reference - no copy is made
        set_global_variable(variable_name.strip(), INPUT)
        
        # Pass through the 'anything' input unchanged (None if not connected)
        return (anything,)


class SimpleGlobalVariableOutput:
    """Retrieve a value from a named global variable.
    
    This node retrieves a value that was stored by a 'Simple Global Variable Input'
    node with the matching variable name. The data is retrieved by reference,
    not copied, to minimize RAM usage.
    
    IMPORTANT: To ensure the Input node executes before this Output node,
    connect the 'trigger' input to any output from a node that depends on
    (directly or indirectly) the Input node. This creates an execution dependency.
    
    Example workflow:
    [Load Image] -> [Global Variable Input (name="my_image")] -> [Some Processing]
                                                                        |
    [Global Variable Output (name="my_image")] <-- trigger -------------+
            |
            v
    [Another Processing]
    """
    
    CATEGORY = "Simple Utility ⛏️/Global Variable"
    FUNCTION = "execute"
    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("OUTPUT",)
    OUTPUT_NODE = False
    
    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleGlobalVariableOutput"]
        return {
            "required": {
                "variable_name": ("STRING", {
                    "default": settings["default_variable_name"],
                    "multiline": False,
                }),
            },
            "optional": {
                # The trigger input creates an execution dependency
                # This ensures the connected node (and its dependencies) execute first
                "trigger": ("*", {"lazy": True}),
            },
        }
    
    def check_lazy_status(self, variable_name: str, trigger=_MISSING) -> List[str]:
        """Control lazy evaluation to ensure proper execution order.
        
        If a trigger is connected but not yet evaluated, we request it to be evaluated.
        This forces ComfyUI to execute all nodes that the trigger depends on first,
        which should include the corresponding Input node.
        
        Note: We use _MISSING sentinel to distinguish between:
        - Not connected: trigger=_MISSING (default)
        - Connected but not evaluated: trigger=None
        - Connected and evaluated: trigger=<actual value>
        """
        # If trigger is not connected at all, we don't need to evaluate it
        if trigger is _MISSING:
            return []
        
        # If trigger is connected but not yet evaluated (None means unevaluated)
        # we request its evaluation to ensure dependencies are met
        if trigger is None:
            return ["trigger"]
        
        # Trigger is connected and evaluated, proceed with execution
        return []
    
    @classmethod
    def VALIDATE_INPUTS(cls, variable_name, trigger=_MISSING):
        """Validate that variable_name is not empty."""
        if not variable_name or not variable_name.strip():
            return "Variable name cannot be empty."
        return True
    
    def execute(self, variable_name: str, trigger=_MISSING) -> Tuple[Any]:
        """Retrieve the value from the global variable.
        
        The value is retrieved by reference to minimize RAM usage.
        This is the same optimization used by reroute nodes.
        
        Args:
            variable_name: The name of the global variable to retrieve.
            trigger: Optional trigger input to force execution ordering.
                     The value itself is ignored; only the connection matters.
        
        Raises:
            KeyError: If the variable doesn't exist.
        """
        # Retrieve by reference - no copy is made
        try:
            value = get_global_variable(variable_name.strip())
        except KeyError as e:
            # Provide a more helpful error message
            error_msg = (
                f"Global variable '{variable_name.strip()}' not found.\n\n"
                f"Possible solutions:\n"
                f"1. Make sure a 'Simple Global Variable Input' node with the same "
                f"variable_name exists in your workflow.\n"
                f"2. Connect this node's 'trigger' input to ensure the Input node "
                f"executes before this Output node.\n"
                f"3. Check that the Input node is not disabled or bypassed."
            )
            raise KeyError(error_msg) from e
        
        return (value,)


# Node class mappings
NODE_CLASS_MAPPINGS = {
    "SimpleGlobalVariableInput": SimpleGlobalVariableInput,
    "SimpleGlobalVariableOutput": SimpleGlobalVariableOutput,
}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleGlobalVariableInput": "⛏️ Simple Global Variable Input",
    "SimpleGlobalVariableOutput": "⛏️ Simple Global Variable Output",
}
