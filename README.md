# ComfyUI Simple Utility Nodes

A collection of simple utility nodes for ComfyUI including time-related, string manipulation, switch, and script nodes.

## Installation

1. Navigate to your ComfyUI custom nodes directory:
   ```
   cd ComfyUI/custom_nodes
   ```

2. Clone this repository:
   ```
   git clone https://github.com/AkihaTatsu/ComfyUI-Simple-Utility-Nodes.git
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Restart ComfyUI.

## Nodes

### Time-Related Nodes

#### Simple Timer

A timer for recording the running time of the workflow. The timer must be started with 'start/reset' mode before recording time.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: Passthrough input (any data type)
- `timer_name`: Name of the timer (default: "timer")
- `mode`: Timer mode
  - `start/reset`: Create or reset the timer
  - `total time record`: Show time since timer start (requires timer to be started first)
  - `since last record`: Show time since last recording (requires timer to be started first)
- `display_format`: Output format
  - `number in seconds`: Accurate float in seconds
  - `number in nanoseconds`: Raw nanosecond value
  - `%H:%M:%S.%f`: Time format (hours/minutes shown only when needed)
  - `text description`: Human-readable format (e.g., "1 hour, 30 minutes, 45.123 seconds")

**Outputs:**
- `anything`: Passthrough of input
- `time`: The formatted time string

</details>

#### Simple Current Datetime

Retrieve the current date and time.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: Passthrough input (any data type)
- `time_format`: Predefined datetime format selection
- `use_custom_format`: Toggle to use custom format string
- `custom_format`: Custom strftime format string

**Outputs:**
- `anything`: Passthrough of input
- `datetime_string`: Formatted datetime string

**Available Formats:**
- `%Y-%m-%d %H:%M:%S` (2024-01-15 14:30:00)
- `%Y-%m-%d` (2024-01-15)
- `%H:%M:%S` (14:30:00)
- `%Y/%m/%d %H:%M:%S` (2024/01/15 14:30:00)
- `%d-%m-%Y` (15-01-2024)
- `%m/%d/%Y` (01/15/2024)
- `%Y-%m-%dT%H:%M:%S` (ISO 8601)
- `Unix Timestamp`
- `Unix Timestamp (ms)`
- And many more...

</details>

### String-Related Nodes

#### Simple String Append

Append text to a string at the beginning or end.

<details>
<summary>Details</summary>

**Inputs:**
- `string`: The original string
- `append_position`: Where to append
  - `at the end` (False): Append after the string
  - `at the beginning` (True): Prepend before the string
- `text_to_append`: The text to append

**Outputs:**
- `string`: The resulting appended string

</details>

#### Simple String Wrapping

Wrap a string with prefix and suffix.

<details>
<summary>Details</summary>

**Inputs:**
- `string`: The original string
- `prefix`: Text to add at the beginning
- `suffix`: Text to add at the end

**Outputs:**
- `string`: The wrapped string

</details>

#### Simple String Severing

Split a string into two parts using a delimiter.

<details>
<summary>Details</summary>

**Inputs:**
- `string`: The original string
- `delimiter`: The delimiter to split on
- `index_selector`: Which delimiter occurrence to use
  - `first`: Use the first occurrence
  - `last`: Use the last occurrence
  - `decided by index`: Use the n-th occurrence (0-based)
- `delimiter_index`: Index of delimiter to use (when using "decided by index")

**Outputs:**
- `first_part`: Text before the delimiter
- `second_part`: Text after the delimiter

</details>

### Switch-Related Nodes

#### Simple Switch with Random Mode

Select one input from multiple inputs, with optional random selection. The number of visible input slots is controlled by the input_num widget.

<details>
<summary>Details</summary>

**Inputs:**
- `input_num`: Number of inputs to use (1-20)
- `selected_index`: Index of the input to select (1-based)
- `select_random`: If Yes, select randomly from connected inputs
- `input_1` to `input_N`: Input values (any data type)

**Outputs:**
- `output`: The selected input value

**Note:** An error will be raised if the selected input is not connected, or if random mode is enabled but no inputs are connected.

</details>

#### Simple Inversed Switch with Random Mode

Distribute one input to one of multiple outputs, with optional random selection. The number of visible output slots is controlled by the output_num widget.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: The input value to distribute
- `output_num`: Number of outputs to use (1-20)
- `selected_index`: Index of the output to send value to (1-based)
- `select_random`: If Yes, select output randomly

**Outputs:**
- `output_1` to `output_N`: Output slots. Only the selected slot receives the input value; others are None.

</details>

### Script-Related Nodes

#### Simple Print to Console

Print a message to the console with optional rich formatting and timestamp.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: Passthrough input (any data type)
- `is_rich_format`: If Yes, interpret message as rich markup (e.g., `[red]text[/red]`)
- `with_timestamp`: If Yes, prepend a logging-style timestamp
- `message`: The message to print

**Outputs:**
- `anything`: Passthrough of input

</details>

#### Simple Python Script

Execute a Python script in an isolated environment.

**WARNING: This node uses Python's `exec()` function to execute arbitrary code. Only use scripts from trusted sources. Do not execute scripts from untrusted or unknown sources as they may contain malicious code that could compromise your system.**

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: Passthrough input, available in script as `INPUT` variable
- `script`: The Python script to execute

**Outputs:**
- `anything`: Passthrough of input
- `RESULT`: Value of `RESULT` variable defined in script, or None if not defined

**Usage:**
```python
# The input is available as INPUT
data = INPUT

# Process data
processed = str(data).upper()

# Set RESULT to pass data to output
RESULT = processed
```

</details>
