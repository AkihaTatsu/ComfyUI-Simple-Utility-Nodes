import { app } from "../../scripts/app.js";

// ============================================================================
// Simple Power Prompt
//
// The node has a "text" multiline widget plus two selector combos:
//   - "lora_name"      (named so ComfyUI Studio intercepts it with its picker)
//   - "embedding_name" (a plain dropdown; Studio has no embedding picker)
//
// Picking an entry inserts a tag into the editable text box and snaps the combo
// back to its placeholder. At run time the Python node reads ONLY the text box.
//
// Selection is detected by hooking widget.value (NOT the callback): ComfyUI
// Studio writes its choice back by assigning widget.value directly and never
// fires the widget callback, so a value-setter is the only reliable hook for
// both the normal dropdown and Studio's modal.
//
// If the "text" widget has been converted to / replaced by an external input
// socket, there is no editable textarea — selections become a harmless no-op.
// ============================================================================

const LORA_PLACEHOLDER = "🔽 select lora to insert";
const EMBEDDING_PLACEHOLDER = "🔽 select embedding to insert";

// Normalize a selected value into a single clean line: collapse any CR/LF
// (which some pickers, e.g. ComfyUI Studio, append for names containing
// spaces) into spaces and trim the ends. Internal spaces are part of the
// name and are preserved; only stray line breaks — which would otherwise
// inject a blank line into the prompt — are removed.
function cleanValue(name) {
    return String(name).replace(/[\r\n]+/g, " ").replace(/\s+$/, "").replace(/^\s+/, "");
}

// Remove a single trailing file extension (e.g. ".safetensors").
function stripExt(name) {
    return String(name).replace(/\.[^/.\\]+$/, "");
}

// Append a tag to the end of the text box. Both the dropdown and the Studio
// picker simply add a selection, so the caret position is irrelevant: trim any
// trailing whitespace off the existing text (so a stray blank line can never
// survive), join with a single space, and overwrite the text box.
function insertSelectionText(textarea, text) {
    const prompt = (textarea.value ?? "").replace(/\s+$/, "");
    const next = prompt ? `${prompt} ${text}` : text;

    textarea.value = next;
    // Notify the widget binding so the value is kept in sync / serialized.
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    textarea.focus();
    textarea.selectionStart = textarea.selectionEnd = next.length;
}

// Find the live editable textarea for the "text" widget, or null when the
// widget is absent (converted to an external input).
function getTextArea(node) {
    const textWidget = node.widgets?.find((w) => w.name === "text");
    if (!textWidget) return null;
    const el = textWidget.inputEl || textWidget.element;
    return el && typeof el.value === "string" ? el : null;
}

// Hook a selector combo's value so any change (dropdown or Studio) inserts a
// tag into the text box and resets the combo to its placeholder.
function hookSelector(node, widgetName, placeholder, buildTag) {
    const widget = node.widgets?.find((w) => w.name === widgetName);
    if (!widget) return;

    let backing = widget.value;
    Object.defineProperty(widget, "value", {
        get() {
            return backing;
        },
        set(v) {
            const cleaned = typeof v === "string" ? cleanValue(v) : v;
            if (cleaned && cleaned !== placeholder) {
                const textarea = getTextArea(node);
                if (textarea) {
                    insertSelectionText(textarea, buildTag(stripExt(cleaned)));
                }
                // Always snap back to the placeholder (no-op when text is external).
                backing = placeholder;
                node.setDirtyCanvas?.(true, true);
                return;
            }
            backing = v;
        },
        configurable: true,
    });
}

app.registerExtension({
    name: "SimpleUtility.PowerPrompt",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "SimplePowerPrompt") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;

            hookSelector(this, "lora_name", LORA_PLACEHOLDER,
                (name) => `<lora:${name}:1.0>`);
            hookSelector(this, "embedding_name", EMBEDDING_PLACEHOLDER,
                (name) => `embedding:${name}`);

            return result;
        };
    },
});
