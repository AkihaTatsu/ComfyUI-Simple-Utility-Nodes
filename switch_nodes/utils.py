"""Utility functions for switch-related nodes."""

import random
from typing import Any, List, Tuple


# Sentinel value to represent an unconnected input
UNCONNECTED = object()


def select_from_inputs(
    inputs: List[Any],
    selected_index: int,
    select_random: bool,
    input_num: int
) -> Any:
    """
    Select one input from a list of inputs.
    
    Args:
        inputs: List of input values (UNCONNECTED for unconnected inputs).
        selected_index: The index to select (1-based).
        select_random: If True, select randomly from connected inputs.
        input_num: The number of inputs configured.
        
    Returns:
        The selected input value.
        
    Raises:
        ValueError: If no valid input can be selected.
    """
    if select_random:
        # Filter to only connected inputs (not UNCONNECTED)
        connected_inputs = [
            (i, v) for i, v in enumerate(inputs) 
            if v is not UNCONNECTED
        ]
        
        if not connected_inputs:
            raise ValueError(
                "Random mode enabled but no inputs are connected. "
                "Please connect at least one input."
            )
        
        _, selected_value = random.choice(connected_inputs)
        return selected_value
    else:
        # Validate selected_index is within range
        if selected_index < 1 or selected_index > input_num:
            raise ValueError(
                f"Selected index {selected_index} is out of valid range (1 to {input_num})."
            )
        
        # Check if the selected input is connected
        idx = selected_index - 1
        if idx >= len(inputs) or inputs[idx] is UNCONNECTED:
            raise ValueError(
                f"Input {selected_index} is not connected. "
                f"Please connect input_{selected_index} or select a different index."
            )
        
        return inputs[idx]


def distribute_to_outputs(
    value: Any,
    output_num: int,
    selected_index: int,
    select_random: bool
) -> Tuple[List[Any], int]:
    """
    Distribute a value to one of the outputs, others get None.
    
    Args:
        value: The input value to distribute.
        output_num: Number of outputs.
        selected_index: The index to output to (1-based).
        select_random: If True, select randomly instead of using selected_index.
        
    Returns:
        A tuple of (list of outputs, selected index 1-based).
    """
    outputs = [None] * output_num
    
    if select_random:
        idx = random.randint(0, output_num - 1)
    else:
        # Convert to 0-based index and clamp to valid range
        idx = max(0, min(selected_index - 1, output_num - 1))
    
    outputs[idx] = value
    return outputs, idx + 1
