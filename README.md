# ComfyUI Simple Utility Nodes

A collection of simple utility nodes for ComfyUI including time-related, string manipulation, string file I/O, switch, script, and global nodes.

## Autofix (Cross-Platform Model Paths)

This package now includes a startup-time autofix that targets cross-platform workflow portability for model path strings.

What it does at ComfyUI launch:

- Detects and logs the current runtime system (`system`, `release`, `machine`, `os.name`, and path separator).
- Installs global runtime patches so model-relative path separators are normalized silently when needed.

What gets normalized:

- Model file path resolution through ComfyUI `folder_paths.get_full_path()` / `get_full_path_or_raise()`.
- Embedding file lookup (`embedding:...`) through `comfy.sd1_clip.load_embed()`.
- Combo/list input validation in the ComfyUI execution validator, so values like `a/b/model.safetensors` and `a\b\model.safetensors` can match each other across Linux/Windows workflows.

Scope:

- The patch is global at runtime (not just this node pack's own nodes), so it affects all nodes that rely on these core ComfyUI loading/validation paths.
- This is a runtime compatibility layer. It does not rewrite files on disk or modify workflow JSON content permanently.

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

#### ⛏️ Simple Timer

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
- `passthrough`: Passthrough of input
- `time_string`: The formatted time string

</details>

#### ⛏️ Simple Current Datetime

Retrieve the current date and time.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: Passthrough input (any data type)
- `time_format`: Predefined datetime format selection
- `use_custom_format`: Toggle to use custom format string
- `custom_format`: Custom strftime format string

**Outputs:**
- `passthrough`: Passthrough of input
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

#### ⛏️ Simple String Appending

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

#### ⛏️ Simple String Wrapping

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

#### ⛏️ Simple String Severing

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

#### ⛏️ Simple Loading String from File

Load a string from a text file with selectable encoding.

<details>
<summary>Details</summary>

**Inputs:**
- No input connection slots by default
- `file_path`: Path to the input file
  - Absolute paths are used directly
  - Relative paths are resolved from the current ComfyUI working directory
- `encoding`: Text encoding used for reading (default: `utf-8`)
  - Dropdown options are loaded from `string_nodes/encodings.json`
  - Includes all packaged text encodings detected in the runtime environment
- `working_dir_display`: Read-only display string in the node UI
  - Shows `Working Dir: <path>`
  - Uses the same dedicated read-only STRING display box style as Time nodes
  - Includes a `Copy Working Directory` button directly below the display box
  - Clicking the button copies only the path itself (without the `Working Dir: ` prefix)
  - Shows a ComfyUI canvas toast notification for copy success/failure
  - Automatically set when the node is created
  - Automatically refreshed after each workflow execution
  - Working directory path is normalized via cross-platform Python path handling

**Outputs:**
- `string`: Full file content as a string

</details>

#### ⛏️ Simple Saving String to File

Save an input string to a text file with selectable encoding.

<details>
<summary>Details</summary>

**Inputs:**
- `string`: Input string to write to file (only input connection slot)
- `file_path`: Path to the output file
  - Absolute paths are used directly
  - Relative paths are resolved from the current ComfyUI working directory
  - Parent directories are created automatically when needed
- `encoding`: Text encoding used for writing (default: `utf-8`)
  - Dropdown options are loaded from `string_nodes/encodings.json`
  - Includes all packaged text encodings detected in the runtime environment
- `working_dir_display`: Read-only display string in the node UI
  - Shows `Working Dir: <path>`
  - Uses the same dedicated read-only STRING display box style as Time nodes
  - Includes a `Copy Working Directory` button directly below the display box
  - Clicking the button copies only the path itself (without the `Working Dir: ` prefix)
  - Shows a ComfyUI canvas toast notification for copy success/failure
  - Automatically set when the node is created
  - Automatically refreshed after each workflow execution
  - Working directory path is normalized via cross-platform Python path handling

**Outputs:**
- `passthrough`: Passthrough of input string after saving completes

</details>

#### ⛏️ Simple Markdown String

A markdown note node with click-to-edit rich text rendering and string output. Click the rendered markdown to edit the raw text; press ESC or click elsewhere to re-render.

<details>
<summary>Details</summary>

**Inputs:**
- `text`: The markdown text to render

**Outputs:**
- `string`: The raw markdown text as a string output

**Supported Features:**
- **GitHub Flavored Markdown (GFM):**
  - Headers (`#`, `##`, etc.)
  - Bold (`**text**`), Italic (`*text*`), Strikethrough (`~~text~~`)
  - Ordered and unordered lists
  - Task lists (`- [ ]`, `- [x]`)
  - Tables
  - Code blocks
  - Blockquotes
  - Horizontal rules
  - Links and images (`![alt](url)`)
  - Inline HTML
- **KaTeX Math Formulae:**
  - Inline math: `$E = mc^2$`
  - Block math: `$$\sum_{i=1}^{n} x_i$$`
- **Emoji Shortcodes:**
  - `:smile:` → 😄, `:rocket:` → 🚀, `:heart:` → ❤️, etc.
- **Images:**
  - Standard markdown images: `![alt text](image_url)`

**Editing Behaviour:**
- **Click** the rendered markdown to switch to the raw text editor
- **Press ESC** or **click elsewhere** to re-render the markdown

</details>

#### ⛏️ Simple Markdown String Display

Display an input string as markdown-rendered rich text or raw text with passthrough output. The last displayed string is saved with the workflow, and readable markdown images are inlined as base64 for reload-safe previews.

<details>
<summary>Details</summary>

**Inputs:**
- `string`: The string to display (must be provided as an input connection)
- `display_mode`: Toggle between display modes
  - `markdown` (False): Render the string as formatted markdown
  - `raw text` (True): Display the raw string without markdown rendering

**Outputs:**
- `passthrough`: Passthrough of the input string

**Supported Features (in markdown mode):**
- Same as Simple Markdown String (GFM, KaTeX Math Formulae, Emoji Shortcodes, Images)

</details>

#### ⛏️ Simple Power Prompt

A prompt node (inspired by rgthree's *Power Prompt*) with in-canvas lora and embedding selectors that insert tags into an editable text box. Inline `<lora:name:strength>` tags are parsed and applied to the incoming MODEL/CLIP, and `embedding:name` references are collected and encoded.

<details>
<summary>Details</summary>

**Inputs:**
- `model`: The MODEL to apply loras to (required input connection)
- `clip`: The CLIP to apply loras to and encode embeddings with (required input connection)
- `text`: The prompt text box. Can be edited by hand, or replaced by an external STRING input (convert widget to input)
- `lora_name`: A selector that inserts `<lora:name:1.0>` into the text box. Named `lora_name` so it is **compatible with ComfyUI Studio** — when Studio is installed, clicking it opens Studio's lora picker; otherwise it is a normal dropdown
- `embedding_name`: A selector that inserts `embedding:name` into the text box (a plain dropdown — ComfyUI Studio has no embedding picker)

**Outputs:**
- `MODEL`: The input model with every parsed `<lora:...>` applied
- `CLIP`: The input clip with every parsed `<lora:...>` applied
- `embedding_conditioning`: A CONDITIONING containing only the CLIP-encoded embeddings (the encoding of an empty string when no embeddings are present)
- `current_text`: The text box content, verbatim (lora tags are kept)
- `embedding_text`: Only the `embedding:name` references, joined so they can be correctly encoded later by another CLIP text-encode node

**Mechanism:**
- The lora/embedding selectors are a frontend convenience: each pick inserts a string at the cursor and then resets the selector to its placeholder. The text box itself is fully editable.
- At run time **only the text-box string is processed** — the selector values are ignored.
- Syntax: `<lora:name:strength>` (e.g. `<lora:detail:0.8>`; strength defaults to `1.0`, `0` is skipped, unresolved names are skipped) and `embedding:name`.
- When `text` is driven by an external input, the selectors become a harmless no-op (there is no text box to insert into).

</details>

### Switch-Related Nodes

#### ⛏️ Simple Switch with Random Mode

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

#### ⛏️ Simple Inversed Switch with Random Mode

Distribute one input to one of multiple outputs, with optional random selection. The number of visible output slots is controlled by the output_num widget. **Unselected outputs use `ExecutionBlocker` to prevent downstream nodes from executing entirely** — they are not simply set to `None`.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: The input value to distribute
- `output_num`: Number of outputs to use (1-20)
- `selected_index`: Index of the output to send value to (1-based)
- `select_random`: If Yes, select output randomly

**Outputs:**
- `output_1` to `output_N`: Output slots. Only the selected slot receives the input value; all other slots are blocked with `ExecutionBlocker` so their downstream graphs never execute.

</details>

#### ⛏️ Simple Boolean Switch

Select one of two inputs based on a boolean value. Uses lazy evaluation so only the selected input's upstream graph is executed — the unselected branch is never evaluated.

<details>
<summary>Details</summary>

**Inputs:**
- `on_true`: The input to use when boolean is True (any data type, lazy)
- `on_false`: The input to use when boolean is False (any data type, lazy)
- `boolean`: The boolean selector (default: True)

**Outputs:**
- `anything`: The value from the selected input

</details>

#### ⛏️ Simple Inversed Boolean Switch

Route one input to one of two outputs based on a boolean value. **The unselected output uses `ExecutionBlocker` to prevent downstream nodes from executing entirely** — they are not simply set to `None`.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: The input value to route (any data type)
- `boolean`: The boolean selector (default: True)

**Outputs:**
- `on_true`: Receives the input value when boolean is True; blocked from execution otherwise
- `on_false`: Receives the input value when boolean is False; blocked from execution otherwise

</details>

### Script-Related Nodes

#### ⛏️ Simple Print to Console

Print a message to the console with optional rich formatting and timestamp.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: Passthrough input (any data type)
- `is_rich_format`: If Yes, interpret message as rich markup (e.g., `[red]text[/red]`)
- `with_timestamp`: If Yes, prepend a logging-style timestamp
- `message`: The message to print

**Outputs:**
- `passthrough`: Passthrough of input

</details>

#### ⛏️ Simple Python Script

Execute a Python script in an isolated environment with dynamic inputs and outputs.

**WARNING: This node uses Python's `exec()` function to execute arbitrary code. Only use scripts from trusted sources. Do not execute scripts from untrusted or unknown sources as they may contain malicious code that could compromise your system.**

<details>
<summary>Details</summary>

**Inputs:**
- `input_num`: Number of inputs to use (1-20)
- `output_num`: Number of outputs to use (1-20)
- `script`: The Python script to execute
- `INPUT1` to `INPUT_N`: Input values (any data type). If an input is not connected, it is `None`.

**Outputs:**
- `OUTPUT1` to `OUTPUT_N`: Output values. If an output variable is not assigned in the script, it is `None`.

**Usage:**
```python
# Inputs are available as INPUT1, INPUT2, ... variables (None if not connected)
# Assign to OUTPUT1, OUTPUT2, ... to pass data to the outputs (None if not assigned)

data = INPUT1
processed = str(data).upper()

OUTPUT1 = processed
OUTPUT2 = len(processed) if processed else 0
```

</details>

### Global Nodes

Global nodes provide workflow-wide functionality including passing data between disconnected nodes using named variables, monitoring all preview images across the workflow, and saving/restoring the current VRAM model cache.

**⚠️ IMPORTANT: Execution Order (for Global Variable nodes)**

ComfyUI executes nodes based on their connections (topological sort). Since global variable nodes are designed to work without physical connections, you must ensure proper execution order by using the `trigger` input on the Output node.

#### ⛏️ Simple Global Variable Input

Store a value in a named global variable. Part of the Global Nodes group.

<details>
<summary>Details</summary>

**Features:**
- Data is stored by reference (like reroute nodes) to minimize RAM usage
- Default color: Pale Blue (for easy identification)

**Inputs:**
- `INPUT`: The value to store in the global variable (any data type)
- `variable_name`: Name of the global variable
- `anything` (optional): Passthrough input (any data type)

**Outputs:**
- `passthrough`: Passthrough of the `anything` input (None if not connected)

</details>

#### ⛏️ Simple Global Variable Output

Retrieve a value from a named global variable. Part of the Global Nodes group.

<details>
<summary>Details</summary>

**Features:**
- Data is retrieved by reference (like reroute nodes) to minimize RAM usage
- Uses lazy evaluation with `trigger` input to ensure proper execution order
- Default color: Pale Blue (for easy identification)

**Inputs:**
- `variable_name`: Name of the global variable to retrieve (must match an input node)
- `trigger` (optional but recommended): Connect to any output from a node that executes after the corresponding Input node

**Outputs:**
- `OUTPUT`: The stored value

**Usage Example:**
```
[Load Image] ──→ [Global Variable Input] ──→ [Some Processing Node]
                  (name="my_image")                    │
                                                       │ (any output)
                                                       ▼
[Global Variable Output] ◀── trigger ─────────────────────
  (name="my_image")
         │
         ▼
[Another Processing Node]
```

The `trigger` input creates an execution dependency, ensuring the Input node (and all its upstream nodes) execute before the Output node.

</details>

**Note:** An error will be raised if the variable doesn't exist. Make sure a "Simple Global Variable Input" node with the same `variable_name` exists in your workflow.

#### ⛏️ Simple Global Image Preview

Automatically monitor and display ALL preview/temporary/saved images and browser-playable videos generated by any node in the workflow — **no connections needed**. Captures both **KSampler step-by-step latent previews** (binary WebSocket frames during sampling) and **final media** from PreviewImage/SaveImage/Save Video nodes (via `executed` WebSocket events). Does **not** send media to the ComfyUI image feed.

<details>
<summary>Details</summary>

**How it works:**
1. A server-side hook intercepts every `executed` WebSocket event to record image/video metadata, and captures KSampler binary preview frames.
2. The front-end JS globally listens to:
   - `executed` events — triggered when PreviewImage / SaveImage / Save Video / any node returns previewable media after execution
   - `b_preview` events — binary KSampler latent step previews sent during each sampling step
3. Images and videos are drawn directly on the node canvas via `onDrawForeground`. Videos are muted and looped, matching ComfyUI's Save Video preview style.
4. A fullscreen viewer page connects its own WebSocket to receive the same events in real time.

**Features:**
- **No connections required** — just add the node to your canvas
- **KSampler step previews** — see latent previews update live during sampling
- **Video previews** — browser-playable video outputs are detected automatically and loop in the node preview
- **Automatic sync** — captures images from *any* node that produces them
- **Does NOT pollute the image feed** — the node returns an empty `ui` dict
- **Fullscreen viewer** — "🔎 Open Fullscreen Viewer" button opens a new browser tab with the [Global Image Preview Viewer Page](#global-image-preview--fullscreen-viewer-page) (see section below for details)
- Default color: Pale Blue (for easy identification)

**Inputs:**
- None (no connections required)

**Outputs:**
- None (this is a display-only output node)

**Usage:**
Simply add the node to your canvas. When any workflow runs:
- During KSampler sampling: step-by-step latent previews appear live
- After PreviewImage / SaveImage / Save Video nodes execute: final media appears automatically

```
[KSampler] → [VAE Decode] → [Preview Image]    ← images from here
                                                    are auto-captured
[⛏️ Simple Global Image Preview]               ← and displayed here
                                                    (no connection needed)
```

</details>

#### Global Image Preview — Fullscreen Viewer Page

The fullscreen viewer is a standalone browser page that displays live images from the running workflow. It can be opened from the **🔎 Open Fullscreen Viewer** button on the node, or by navigating directly to:

```
http://<host>:<port>/simple_utility/global_image_preview/viewer
```

(e.g. `http://localhost:8188/simple_utility/global_image_preview/viewer` for a default local setup)

<details>
<summary>Details</summary>

**Connection & Status:**
- A coloured dot in the header shows the WebSocket connection state (green = connected, red = disconnected).
- The workflow status badge shows whether ComfyUI is **Idle** or **Running**, and displays the class name of the currently executing node.
- Falls back to HTTP polling every 300 ms when WebSocket is unavailable.

**Image Display:**
- Receives live **KSampler latent step previews** (`b_preview` binary WebSocket frames) and **final images/videos** from PreviewImage / SaveImage / Save Video nodes (`executed` events) in real time.
- Browser-playable videos are muted and loop automatically in the main viewer.
- **Fit Mode** selector in the header:
  - `Contain` — scale image to fit within the viewport (default).
  - `Fill` — scale image to fill the viewport (may crop).
  - `Actual Size` — display at native pixel resolution with scrollbars.
- **Mouse wheel zoom** towards the cursor (in Contain / Fill modes).
- **Drag-to-pan** with mouse or touch (when zoomed in, or in Actual Size mode).
- **Double-click** to reset zoom back to 1×.
- **Pinch-to-zoom** on touch devices.

**History Sidebar:**
- The **History** button toggles a thumbnail sidebar listing up to 50 recent images.
- Click any thumbnail to open it in the main viewer.
- The **🗑 Clear** button clears the history list.

**Lightbox:**
- Click any history thumbnail to open a full-size lightbox overlay.
- Images in the lightbox can still be clicked to open in a new browser tab at full resolution.
- Videos in the lightbox use native playback controls, including play/pause and seeking. Clicking the video itself toggles play/pause instead of opening a new tab.
- Press **ESC** or click outside the media to close the lightbox.
- On mobile the system back button / swipe gesture also closes the lightbox.

**Workflow Controls:**
- **✕ Interrupt** button — sends an interrupt signal to stop the currently running workflow (enabled only while a workflow is running).
- **⟳ Rerun** button — re-queues the last workflow prompt:
  - `Same Task` mode: interrupts any running workflow and re-queues the exact same prompt (seed unchanged).
  - `New Task` mode: appends the prompt to the queue without interrupting.
- These controls communicate with ComfyUI directly, so they work even when the ComfyUI browser tab is closed.

**Mobile & Responsive:**
- Controls collapse into a hamburger menu (☰) on narrow viewports.
- Touch-optimised tap targets and pinch-to-zoom support.

**Footer:**
- Left side shows the current image's filename and type.
- Right side shows the WebSocket / polling connection status.

</details>

#### ⛏️ Simple Global VRAM Cache Saving

Save all models currently loaded in VRAM to RAM (and disk) and clear VRAM. Useful for temporarily freeing VRAM for other tasks without having to reload models from scratch.

<details>
<summary>Details</summary>

**How it works:**

1. Captures a flat state dict of every tensor loaded on GPU via ComfyUI's `current_loaded_models`.
2. Measures total cache size vs. available system RAM and auto-selects one of two branches:
   - **RAM + Disk** (free RAM ≥ cache size):
     1. Moves all VRAM tensors to CPU RAM — protected with per-entry `mmap` guards and `weakref.finalize` so they are read-only and safely garbage-collected even if ComfyUI is killed.
     2. Completely cleans VRAM (`unload_all_models` + `soft_empty_cache`).
     3. Launches a **background daemon thread** that writes the RAM cache to disk using **safetensors** (raw binary, no pickle). The node finishes immediately — disk I/O is non-blocking.
   - **Disk Only** (free RAM < cache size):
     1. Launches a background thread that reads tensors **directly from VRAM** and writes to disk using safetensors.
     2. Waits until the disk save completes.
     3. Cleans VRAM afterwards.
3. If a cache with the same `cache_name` already exists, it is overwritten (both RAM and disk).
4. Detailed logging at every step: tensor count, model sizes, elapsed time, write throughput.

**Features:**
- Disk format is **safetensors** — fastest possible serialisation, no pickle, dtype-preserving.
- RAM cache entries are mmap-guarded and reference-counted; the OS reclaims them on abnormal exit.
- A `ResourceWarning` is emitted when free RAM is insufficient or dangerously tight.

**Inputs:**
- `anything`: Passthrough input (any data type)
- `cache_name`: Name for the cache entry (default: `"VRAM_cache"`)

**Outputs:**
- `passthrough`: Passthrough of input

</details>

#### ⛏️ Simple Global VRAM Cache Loading

Restore a previously saved VRAM cache from RAM or disk back into VRAM.

<details>
<summary>Details</summary>

**How it works:**

1. Completely cleans current VRAM (only ComfyUI-managed models, not other processes).
2. Checks for a **RAM cache** with the given name (fastest path — zero-copy read of the read-only mmap-guarded tensors, then `.to(cuda)`).
3. If no RAM cache exists, checks for a **disk cache** (safetensors file).
   - If a background disk-save thread for the same name is still running, waits for it to finish first.
   - Loads the safetensors file directly into VRAM using `safetensors.torch.load_file(device="cuda")`.
4. Raises `FileNotFoundError` if neither RAM nor disk cache is found.

**Inputs:**
- `anything`: Passthrough input (any data type)
- `cache_name`: Name of the cache to restore (must match a prior Save node)

**Outputs:**
- `passthrough`: Passthrough of input

</details>

#### ⛏️ Simple Global VRAM Cache RAM Clearing

Clear **all** VRAM caches currently held in system RAM.  Before clearing, this node **waits for every in-flight background save thread to finish**, ensuring all model data has been fully persisted to disk.  Disk caches are **not** affected and remain available for future loading.

<details>
<summary>Details</summary>

**Inputs:**
- `anything`: Passthrough input (any data type)

**Outputs:**
- `passthrough`: Passthrough of input

**Usage:**
Add this node after you no longer need the fast-path cached models to reclaim system RAM.  All background disk-save threads are joined first so that disk caches are guaranteed to be complete.  Disk caches can still be loaded by a `Simple Global VRAM Cache Loading` node after RAM is cleared.

</details>

#### ⛏️ Simple Global Deep Cleanup

Best-effort RAM/VRAM cleanup for the current ComfyUI process. This is useful at the end of large workflows to reduce leftover memory pressure before the next run.

<details>
<summary>Details</summary>

**Important limits:**
- This node can free many internal ComfyUI and Simple Utility caches, but it cannot strictly restore the process to the same state as a fresh ComfyUI launch.
- It preserves visible/user-facing state, including ComfyUI output records, Global Image Preview history/current display, and Simple Global Variable values.
- A true fresh-start state requires restarting the ComfyUI process.
- If a loop carries large IMAGE/LATENT batches, this node can only help after the loop and prompt finish. It cannot reduce the RAM peak that already happens while the loop is running.
- The passthrough output itself may remain referenced by ComfyUI until the prompt finishes.

**Modes:**
- `RAM + VRAM` (default): Clears internal RAM caches, unloads models, clears device caches, and schedules one end-of-run executor cache reset.
- `RAM`: Clears internal RAM caches and schedules one end-of-run executor cache reset. Models are not actively unloaded.
- `VRAM`: Unloads models and clears device allocator caches. Simple Utility RAM caches are not cleared.

**End-of-run cleanup:**

Running this node schedules an extra cleanup pass after the current prompt finishes. If multiple `Simple Global Deep Cleanup` nodes run in the same prompt, the end-of-run cleanup is performed only once, with the strongest requested mode.

**Inputs:**
- `cleanup_mode`: `RAM + VRAM`, `RAM`, or `VRAM`
- `anything`: Passthrough input (any data type)

**Outputs:**
- `passthrough`: Passthrough of input

</details>
