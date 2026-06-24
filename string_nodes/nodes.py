"""String-related custom nodes for ComfyUI."""

import json
import os
import time
from typing import Tuple

from .utils import (
    append_string,
    extract_embedding_text,
    get_working_dir_display,
    get_working_dir_path,
    load_string_from_file,
    parse_loras_from_text,
    save_string_to_file,
    sever_string,
    wrap_string,
)

# First combo entry is a non-model placeholder so the default never auto-inserts
# anything. The frontend resets the selector back to it after every pick.
LORA_PLACEHOLDER = "🔽 select lora to insert"
EMBEDDING_PLACEHOLDER = "🔽 select embedding to insert"

# Load settings
_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "settings.json")
with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
    SETTINGS = json.load(f)

_ENCODINGS_PATH = os.path.join(os.path.dirname(__file__), "encodings.json")
with open(_ENCODINGS_PATH, "r", encoding="utf-8") as f:
    _ENCODINGS_PAYLOAD = json.load(f)

_AVAILABLE_ENCODINGS = tuple(_ENCODINGS_PAYLOAD.get("encodings", []))
if not _AVAILABLE_ENCODINGS:
    _AVAILABLE_ENCODINGS = ("utf-8",)


def _get_default_encoding(settings_key: str) -> str:
    """Return a safe default encoding for a node."""
    default_encoding = SETTINGS[settings_key].get("default_encoding", "utf-8")
    if default_encoding in _AVAILABLE_ENCODINGS:
        return default_encoding

    if "utf-8" in _AVAILABLE_ENCODINGS:
        return "utf-8"

    return _AVAILABLE_ENCODINGS[0]


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


class SimpleLoadingStringFromFile:
    """Load a string from a text file."""

    CATEGORY = "Simple Utility ⛏️/String"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("string",)

    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleLoadingStringFromFile"]
        return {
            "required": {
                "file_path": ("STRING", {
                    "default": settings["default_file_path"],
                    "multiline": False,
                    "forceInput": False,
                    "defaultInput": False
                }),
                "encoding": (_AVAILABLE_ENCODINGS, {
                    "default": _get_default_encoding("SimpleLoadingStringFromFile"),
                    "defaultInput": False
                }),
                "working_dir_display": ("STRING", {
                    "default": get_working_dir_display(),
                    "multiline": False,
                    "forceInput": False,
                    "defaultInput": False
                }),
            }
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Force re-execution so file content is reloaded every run."""
        return time.time_ns()

    @classmethod
    def VALIDATE_INPUTS(cls, file_path, encoding, working_dir_display):
        """Validate load node inputs."""
        if not file_path or not file_path.strip():
            return "File path cannot be empty."
        if encoding not in _AVAILABLE_ENCODINGS:
            return f"Unsupported encoding: {encoding}"
        return True

    def execute(
        self,
        file_path: str,
        encoding: str,
        working_dir_display: str
    ) -> dict:
        """Execute the file loading operation."""
        try:
            loaded_string = load_string_from_file(file_path, encoding)
        except Exception as exc:
            raise RuntimeError(f"Failed to load string from file: {exc}") from exc

        working_dir = get_working_dir_display()
        working_dir_path = get_working_dir_path()
        return {
            "ui": {
                "working_dir": [working_dir],
                "working_dir_path": [working_dir_path]
            },
            "result": (loaded_string,)
        }


class SimpleSavingStringToFile:
    """Save a string to a text file."""

    CATEGORY = "Simple Utility ⛏️/String"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("passthrough",)
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        settings = SETTINGS["SimpleSavingStringToFile"]
        return {
            "required": {
                "string": ("STRING", {"forceInput": True}),
                "file_path": ("STRING", {
                    "default": settings["default_file_path"],
                    "multiline": False,
                    "forceInput": False,
                    "defaultInput": False
                }),
                "encoding": (_AVAILABLE_ENCODINGS, {
                    "default": _get_default_encoding("SimpleSavingStringToFile"),
                    "defaultInput": False
                }),
                "working_dir_display": ("STRING", {
                    "default": get_working_dir_display(),
                    "multiline": False,
                    "forceInput": False,
                    "defaultInput": False
                }),
            }
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Always execute so writes happen every workflow run."""
        return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, string, file_path, encoding, working_dir_display):
        """Validate save node inputs."""
        if not file_path or not file_path.strip():
            return "File path cannot be empty."
        if encoding not in _AVAILABLE_ENCODINGS:
            return f"Unsupported encoding: {encoding}"
        return True

    def execute(
        self,
        string: str,
        file_path: str,
        encoding: str,
        working_dir_display: str
    ) -> dict:
        """Execute the file saving operation."""
        try:
            saved_path = save_string_to_file(string, file_path, encoding)
        except Exception as exc:
            raise RuntimeError(f"Failed to save string to file: {exc}") from exc

        working_dir = get_working_dir_display()
        working_dir_path = get_working_dir_path()
        return {
            "ui": {
                "text": [f"Saved to: {saved_path}"],
                "working_dir": [working_dir],
                "working_dir_path": [working_dir_path]
            },
            "result": (string,)
        }


class SimpleMarkdownString:
    """A markdown note node with click-to-edit behavior and string output.

    Displays rendered markdown by default. Single-click the rendered view
    to switch to a raw text editor. Click elsewhere or press ESC to
    re-render the markdown. Supports KaTeX math, emoji shortcodes,
    and images via the frontend extension.
    """

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
            "ui": {"text": (text,)},
            "result": (text,)
        }


class SimpleMarkdownStringDisplay:
    """Display an input string as markdown-rendered rich text or raw text.

    Uses the same preview pattern as ComfyUI's PreviewAny node:
    two preview widgets (markdown and plaintext) with a toggle switch.
    The markdown preview is enhanced with KaTeX math, emoji shortcodes,
    and image support.
    """

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
            "ui": {"text": (string,)},
            "result": (string,)
        }


class SimplePowerPrompt:
    """A prompt node with in-canvas lora and embedding selectors.

    Inline ``<lora:name:strength>`` tags in the text box are parsed and
    applied to the incoming MODEL/CLIP. The lora and embedding selectors are
    a frontend convenience: picking one inserts its tag into the (editable)
    text box. At run time only the text-box string is processed.

    The lora selector is named ``lora_name`` so ComfyUI Studio intercepts it
    with its model picker; the embedding selector is a plain dropdown
    (Studio has no embedding picker).

    Outputs:
        MODEL / CLIP            -- with every parsed lora applied.
        embedding_conditioning  -- CLIP-encoded embeddings (encode("") if none).
        current_text            -- the text box, verbatim.
        embedding_text          -- only the embedding references, for later encoding.
    """

    CATEGORY = "Simple Utility ⛏️/String"
    FUNCTION = "execute"
    RETURN_TYPES = ("MODEL", "CLIP", "CONDITIONING", "STRING", "STRING")
    RETURN_NAMES = (
        "MODEL",
        "CLIP",
        "embedding_conditioning",
        "current_text",
        "embedding_text",
    )

    @classmethod
    def INPUT_TYPES(cls):
        import folder_paths

        settings = SETTINGS["SimplePowerPrompt"]
        lora_list = [LORA_PLACEHOLDER] + folder_paths.get_filename_list("loras")
        embedding_list = (
            [EMBEDDING_PLACEHOLDER] + folder_paths.get_filename_list("embeddings")
        )
        return {
            "required": {
                "model": ("MODEL",),
                "clip": ("CLIP",),
                "text": ("STRING", {
                    "default": settings["default_text"],
                    "multiline": True,
                    "dynamicPrompts": True
                }),
            },
            "optional": {
                # MUST be named exactly "lora_name" for ComfyUI Studio compatibility.
                "lora_name": (lora_list,),
                "embedding_name": (embedding_list,),
            },
        }

    def execute(
        self,
        model,
        clip,
        text: str,
        lora_name: str = None,
        embedding_name: str = None,
    ):
        """Apply loras from the text, encode embeddings, and pass text through."""
        from nodes import CLIPTextEncode, LoraLoader

        for lora in parse_loras_from_text(text):
            model, clip = LoraLoader().load_lora(
                model, clip, lora["lora"], lora["strength"], lora["strength"]
            )

        embedding_text = extract_embedding_text(text)
        # encode("") yields a valid "empty" conditioning when no embeddings exist.
        conditioning = CLIPTextEncode().encode(clip, embedding_text)[0]

        return (model, clip, conditioning, text, embedding_text)


# Node class mappings
NODE_CLASS_MAPPINGS = {
    "SimpleStringAppending": SimpleStringAppending,
    "SimpleStringWrapping": SimpleStringWrapping,
    "SimpleStringSevering": SimpleStringSevering,
    "SimpleLoadingStringFromFile": SimpleLoadingStringFromFile,
    "SimpleSavingStringToFile": SimpleSavingStringToFile,
    "SimpleMarkdownString": SimpleMarkdownString,
    "SimpleMarkdownStringDisplay": SimpleMarkdownStringDisplay,
    "SimplePowerPrompt": SimplePowerPrompt,
}

# Display name mappings
NODE_DISPLAY_NAME_MAPPINGS = {
    "SimpleStringAppending": "⛏️ Simple String Appending",
    "SimpleStringWrapping": "⛏️ Simple String Wrapping",
    "SimpleStringSevering": "⛏️ Simple String Severing",
    "SimpleLoadingStringFromFile": "⛏️ Simple Loading String from File",
    "SimpleSavingStringToFile": "⛏️ Simple Saving String to File",
    "SimpleMarkdownString": "⛏️ Simple Markdown String",
    "SimpleMarkdownStringDisplay": "⛏️ Simple Markdown String Display",
    "SimplePowerPrompt": "⛏️ Simple Power Prompt",
}
