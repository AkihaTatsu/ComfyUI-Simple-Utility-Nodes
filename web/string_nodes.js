import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// ============================================================================
// Library loading (KaTeX, marked, DOMPurify) — with local fallback
// ============================================================================

let librariesLoaded = false;
let librariesLoading = false;
const libraryLoadCallbacks = [];

// Base path for local backup copies served by ComfyUI's static extension route
const BACKUP_BASE = "extensions/ComfyUI-Simple-Utility-Nodes/backups";

// CDN URLs and their local backup filenames
const CDN_RESOURCES = {
    "katex_css":  { cdn: "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css",       file: "katex.min.css"  },
    "katex_js":   { cdn: "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js",        file: "katex.min.js"   },
    "marked_js":  { cdn: "https://cdn.jsdelivr.net/npm/marked@14.1.4/marked.min.js",            file: "marked.min.js"  },
    "purify_js":  { cdn: "https://cdn.jsdelivr.net/npm/dompurify@3.2.4/dist/purify.min.js",     file: "purify.min.js"  },
};

async function loadLibraries() {
    if (librariesLoaded) return;
    if (librariesLoading) {
        return new Promise((resolve) => libraryLoadCallbacks.push(resolve));
    }
    librariesLoading = true;
    try {
        // KaTeX CSS
        await loadStylesheet(CDN_RESOURCES.katex_css);

        // JS libraries — order matters (katex first)
        await loadScript(CDN_RESOURCES.katex_js);
        await loadScript(CDN_RESOURCES.marked_js);
        await loadScript(CDN_RESOURCES.purify_js);

        librariesLoaded = true;
        libraryLoadCallbacks.forEach(cb => cb());
        libraryLoadCallbacks.length = 0;
    } catch (error) {
        console.error("[SimpleMarkdown] Failed to load libraries:", error);
        librariesLoading = false;
        throw error;
    }
}

/**
 * Load a <link rel="stylesheet"> — try CDN first, fall back to local backup.
 */
function loadStylesheet(res) {
    return new Promise((resolve, reject) => {
        // Already present?
        const existing = document.querySelector(`link[href="${res.cdn}"], link[data-backup-for="${res.file}"]`);
        if (existing) { resolve(); return; }

        const link = document.createElement("link");
        link.rel = "stylesheet";
        link.crossOrigin = "anonymous";

        function tryLocal() {
            const localLink = document.createElement("link");
            localLink.rel = "stylesheet";
            localLink.href = `${BACKUP_BASE}/${res.file}`;
            localLink.setAttribute("data-backup-for", res.file);
            localLink.onload = () => {
                console.info(`[SimpleMarkdown] Loaded local backup CSS: ${res.file}`);
                resolve();
            };
            localLink.onerror = () => reject(new Error(`Failed to load CSS from both CDN and local backup: ${res.file}`));
            document.head.appendChild(localLink);
        }

        link.href = res.cdn;
        link.onload = resolve;
        link.onerror = () => {
            console.warn(`[SimpleMarkdown] CDN CSS failed, trying local backup: ${res.file}`);
            link.remove();
            tryLocal();
        };
        document.head.appendChild(link);
    });
}

/**
 * Load a <script> — try CDN first, fall back to local backup.
 */
function loadScript(res) {
    return new Promise((resolve, reject) => {
        // Already loaded?
        const existing = document.querySelector(`script[src="${res.cdn}"], script[data-backup-for="${res.file}"]`);
        if (existing) { resolve(); return; }

        const script = document.createElement("script");
        script.crossOrigin = "anonymous";

        function tryLocal() {
            const localScript = document.createElement("script");
            localScript.src = `${BACKUP_BASE}/${res.file}`;
            localScript.setAttribute("data-backup-for", res.file);
            localScript.onload = () => {
                console.info(`[SimpleMarkdown] Loaded local backup JS: ${res.file}`);
                resolve();
            };
            localScript.onerror = () => reject(new Error(`Failed to load JS from both CDN and local backup: ${res.file}`));
            document.head.appendChild(localScript);
        }

        script.src = res.cdn;
        script.onload = resolve;
        script.onerror = () => {
            console.warn(`[SimpleMarkdown] CDN JS failed, trying local backup: ${res.file}`);
            script.remove();
            tryLocal();
        };
        document.head.appendChild(script);
    });
}

// ============================================================================
// Emoji map
// ============================================================================

const EMOJI_MAP = {
    "smile": "😄", "grinning": "😀", "laughing": "😆", "blush": "😊", "smiley": "😃",
    "relaxed": "☺️", "heart_eyes": "😍", "kissing_heart": "😘", "wink": "😉", "stuck_out_tongue": "😛",
    "sunglasses": "😎", "smirk": "😏", "unamused": "😒", "disappointed": "😞", "pensive": "😔",
    "worried": "😟", "confused": "😕", "frowning": "☹️", "persevere": "😣", "confounded": "😖",
    "tired_face": "😫", "weary": "😩", "cry": "😢", "sob": "😭", "joy": "😂",
    "astonished": "😲", "scream": "😱", "angry": "😠", "rage": "😡", "triumph": "😤",
    "sleepy": "😪", "yum": "😋", "mask": "😷", "innocent": "😇", "alien": "👽",
    "yellow_heart": "💛", "blue_heart": "💙", "purple_heart": "💜", "heart": "❤️", "green_heart": "💚",
    "broken_heart": "💔", "heartbeat": "💓", "heartpulse": "💗", "sparkling_heart": "💖", "cupid": "💘",
    "star": "⭐", "star2": "🌟", "sparkles": "✨", "sunny": "☀️", "cloud": "☁️",
    "umbrella": "☂️", "snowflake": "❄️", "zap": "⚡", "fire": "🔥", "droplet": "💧",
    "thumbsup": "👍", "+1": "👍", "thumbsdown": "👎", "-1": "👎", "ok_hand": "👌",
    "punch": "👊", "fist": "✊", "v": "✌️", "wave": "👋", "hand": "✋",
    "open_hands": "👐", "point_up": "☝️", "point_down": "👇", "point_left": "👈", "point_right": "👉",
    "raised_hands": "🙌", "pray": "🙏", "clap": "👏", "muscle": "💪", "metal": "🤘",
    "rocket": "🚀", "airplane": "✈️", "car": "🚗", "taxi": "🚕", "bus": "🚌",
    "ambulance": "🚑", "fire_engine": "🚒", "bike": "🚲", "helicopter": "🚁", "boat": "⛵",
    "dog": "🐕", "cat": "🐈", "mouse": "🐭", "hamster": "🐹", "rabbit": "🐰",
    "wolf": "🐺", "frog": "🐸", "tiger": "🐯", "koala": "🐨", "bear": "🐻",
    "pig": "🐷", "cow": "🐮", "monkey": "🐵", "horse": "🐴", "snake": "🐍",
    "bird": "🐦", "penguin": "🐧", "turtle": "🐢", "bug": "🐛", "bee": "🐝",
    "apple": "🍎", "green_apple": "🍏", "tangerine": "🍊", "lemon": "🍋", "cherries": "🍒",
    "grapes": "🍇", "watermelon": "🍉", "strawberry": "🍓", "peach": "🍑", "banana": "🍌",
    "pizza": "🍕", "hamburger": "🍔", "fries": "🍟", "hotdog": "🌭", "popcorn": "🍿",
    "coffee": "☕", "tea": "🍵", "beer": "🍺", "wine_glass": "🍷", "cocktail": "🍸",
    "checkmark": "✓", "check": "✔️", "x": "❌", "warning": "⚠️", "question": "❓",
    "exclamation": "❗", "bulb": "💡", "gear": "⚙️", "wrench": "🔧", "hammer": "🔨",
    "key": "🔑", "lock": "🔒", "unlock": "🔓", "bell": "🔔", "bookmark": "🔖",
    "link": "🔗", "paperclip": "📎", "scissors": "✂️", "pencil": "✏️", "pen": "🖊️",
    "book": "📖", "notebook": "📓", "memo": "📝", "calendar": "📅", "chart": "📊",
    "email": "📧", "phone": "📱", "computer": "💻", "keyboard": "⌨️", "desktop": "🖥️",
    "folder": "📁", "file": "📄", "trash": "🗑️", "hourglass": "⏳", "watch": "⌚",
    "100": "💯", "trophy": "🏆", "medal": "🏅", "crown": "👑", "gem": "💎"
};

function replaceEmojis(text) {
    return text.replace(/:([a-zA-Z0-9_+-]+):/g, (match, name) => {
        return EMOJI_MAP[name.toLowerCase()] || match;
    });
}

// ============================================================================
// Markdown rendering with KaTeX, emoji, and image support
// ============================================================================

function renderMath(text) {
    if (typeof katex === "undefined") return text;

    // Block math ($$...$$)
    text = text.replace(/\$\$([\s\S]*?)\$\$/g, (match, math) => {
        try {
            return katex.renderToString(math.trim(), { displayMode: true, throwOnError: false });
        } catch (e) {
            return `<span class="simple-md-katex-error">${escapeHtml(match)}</span>`;
        }
    });

    // Inline math ($...$)
    text = text.replace(/(?<!\$)\$(?!\$)((?:\\.|[^$\\])+)\$(?!\$)/g, (match, math) => {
        try {
            return katex.renderToString(math.trim(), { displayMode: false, throwOnError: false });
        } catch (e) {
            return `<span class="simple-md-katex-error">${escapeHtml(match)}</span>`;
        }
    });

    return text;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdownFull(text) {
    if (!text) return "";

    // 1. Replace emoji shortcodes with unicode
    let processed = replaceEmojis(text);

    // 2. Protect math blocks from markdown parser
    const mathBlocks = [];
    let mathIndex = 0;

    processed = processed.replace(/\$\$([\s\S]*?)\$\$/g, (match) => {
        const ph = `\x00MATH_BLOCK_${mathIndex}\x00`;
        mathBlocks.push({ ph, content: match });
        mathIndex++;
        return ph;
    });

    processed = processed.replace(/(?<!\$)\$(?!\$)((?:\\.|[^$\\])+)\$(?!\$)/g, (match) => {
        const ph = `\x00MATH_INLINE_${mathIndex}\x00`;
        mathBlocks.push({ ph, content: match });
        mathIndex++;
        return ph;
    });

    // 3. Parse markdown (GFM)
    if (typeof marked !== "undefined") {
        marked.setOptions({ gfm: true, breaks: true });
        processed = marked.parse(processed);
    }

    // 4. Restore and render math
    mathBlocks.forEach(({ ph, content }) => {
        processed = processed.replace(ph, renderMath(content));
    });

    // 5. Sanitize
    if (typeof DOMPurify !== "undefined") {
        processed = DOMPurify.sanitize(processed, {
            ADD_TAGS: [
                "math", "semantics", "mrow", "mi", "mo", "mn", "msup", "msub",
                "mfrac", "mover", "munder", "munderover", "msqrt", "mroot",
                "mtable", "mtr", "mtd", "annotation", "video", "source"
            ],
            ADD_ATTR: [
                "xmlns", "mathvariant", "class", "style", "align",
                "controls", "autoplay", "loop", "muted", "preload", "poster",
                "target", "rel"
            ],
            ALLOW_DATA_ATTR: true
        });
    }

    return processed;
}

// ============================================================================
// CSS injection
// ============================================================================

function injectStyles() {
    if (document.getElementById("simple-markdown-styles")) return;
    const style = document.createElement("style");
    style.id = "simple-markdown-styles";
    style.textContent = `
        .simple-md-render {
            word-wrap: break-word;
            overflow-wrap: break-word;
            font-size: 13px;
            line-height: 1.5;
            color: #e0e0e0;
            padding: 8px;
        }
        .simple-md-render h1, .simple-md-render h2,
        .simple-md-render h3, .simple-md-render h4,
        .simple-md-render h5, .simple-md-render h6 {
            margin: 0.5em 0 0.3em 0; padding: 0;
            font-weight: 600; line-height: 1.25; color: #fff;
        }
        .simple-md-render h1 { font-size: 1.6em; border-bottom: 1px solid #444; padding-bottom: 0.2em; }
        .simple-md-render h2 { font-size: 1.4em; border-bottom: 1px solid #333; padding-bottom: 0.2em; }
        .simple-md-render h3 { font-size: 1.2em; }
        .simple-md-render h4 { font-size: 1.1em; }
        .simple-md-render h5 { font-size: 1em; }
        .simple-md-render h6 { font-size: 0.9em; color: #888; }
        .simple-md-render p { margin: 0.5em 0; }
        .simple-md-render a { color: #58a6ff; text-decoration: none; }
        .simple-md-render a:hover { text-decoration: underline; }
        .simple-md-render code {
            background: rgba(110, 118, 129, 0.4); padding: 0.15em 0.3em;
            border-radius: 3px; font-family: 'Consolas','Monaco','Courier New',monospace; font-size: 0.9em;
        }
        .simple-md-render pre {
            background: rgba(30, 30, 30, 0.8); padding: 10px;
            border-radius: 6px; overflow-x: auto; margin: 0.5em 0;
        }
        .simple-md-render pre code { background: transparent; padding: 0; }
        .simple-md-render blockquote {
            border-left: 3px solid #4a9eff; margin: 0.5em 0; padding: 0.25em 1em;
            color: #aaa; background: rgba(74, 158, 255, 0.1);
        }
        .simple-md-render ul, .simple-md-render ol { margin: 0.5em 0; padding-left: 1.5em; }
        .simple-md-render li { margin: 0.2em 0; }
        .simple-md-render table { border-collapse: collapse; width: 100%; margin: 0.5em 0; }
        .simple-md-render th, .simple-md-render td { border: 1px solid #444; padding: 6px 10px; }
        .simple-md-render th { background: rgba(74, 158, 255, 0.2); font-weight: 600; }
        .simple-md-render tr:nth-child(even) { background: rgba(255, 255, 255, 0.03); }
        .simple-md-render img { max-width: 100%; height: auto; border-radius: 4px; }
        .simple-md-render hr { border: none; border-top: 1px solid #444; margin: 1em 0; }
        .simple-md-render input[type="checkbox"] { margin-right: 0.5em; }
        .simple-md-render .katex { font-size: 1em; }
        .simple-md-render .katex-display { margin: 0.5em 0; overflow-x: auto; overflow-y: hidden; }
        .simple-md-render del { text-decoration: line-through; color: #888; }
        .simple-md-render mark { background: rgba(255, 255, 0, 0.3); padding: 0.1em 0.2em; border-radius: 2px; }
        .simple-md-katex-error {
            color: #ff6b6b; background: rgba(255, 107, 107, 0.1);
            padding: 2px 4px; border-radius: 3px;
        }
    `;
    document.head.appendChild(style);
}

// ============================================================================
// Enhanced markdown DOM widget
// Mirrors the addDOMWidget pattern used by ComfyWidgets but renders with
// KaTeX + emoji + image support via marked.js.
// ============================================================================

function addEnhancedMarkdownWidget(node, name) {
    const container = document.createElement("div");
    container.className = "simple-md-render comfy-multiline-input";
    container.style.cssText =
        "width:100%;min-height:50px;box-sizing:border-box;overflow:auto;background:transparent;";

    // Internal state — the raw markdown string
    let _value = "";

    function renderToContainer() {
        loadLibraries().then(() => {
            container.innerHTML = renderMarkdownFull(_value);
        }).catch((err) => {
            container.innerHTML =
                `<pre style="color:#ff6b6b;">Markdown render error: ${escapeHtml(err.message)}\n\n${escapeHtml(_value)}</pre>`;
        });
    }

    // Use addDOMWidget exactly like the core widgets do.
    // getValue / setValue are the only interface the framework needs.
    const widget = node.addDOMWidget(name, "enhanced_markdown", container, {
        getValue() {
            return _value;
        },
        setValue(v) {
            _value = v;
            renderToContainer();
        }
    });

    // Match the property name the core uses for multiline STRING widgets
    widget.inputEl = container;

    // Do NOT redefine widget.value — addDOMWidget already defines a
    // getter/setter that delegates to getValue/setValue above.
    widget.serialize = false;

    return widget;
}

// ============================================================================
// Extension registration
// ============================================================================

injectStyles();

app.registerExtension({
    name: "SimpleUtility.StringNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {

        // ==================================================================
        // SimpleMarkdownString
        //   Editable markdown note with string output.
        //   Click-to-edit behaviour: single-click the rendered markdown to
        //   switch to a raw-text editor; click elsewhere or press ESC to
        //   re-render the markdown. No toggle button is needed.
        //
        //   The Python node has a normal "text" STRING multiline widget
        //   (auto-created by the framework). We hide it and layer a custom
        //   DOM widget on top that alternates between rendered markdown and
        //   an editing textarea. Both share the same backing value through
        //   the original "text" widget.
        // ==================================================================
        if (nodeData.name === "SimpleMarkdownString") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated
                    ? onNodeCreated.apply(this, [])
                    : undefined;

                // --- Find the auto-created "text" widget (STRING multiline) ---
                const textWidget = this.widgets?.find(w => w.name === "text");

                // --- Build the click-to-edit container ---
                // Uses CSS Grid overlay (same technique as the core
                // Markdown Note): both layers share the same grid cell so
                // they always have identical dimensions.
                const container = document.createElement("div");
                container.className = "simple-md-clickedit comfy-multiline-input";
                container.style.cssText =
                    "display:grid;width:100%;box-sizing:border-box;" +
                    "overflow:hidden auto;";

                // Rendered markdown layer
                const mdDiv = document.createElement("div");
                mdDiv.className = "simple-md-render";
                mdDiv.style.cssText =
                    "grid-area:1/1/2/2;box-sizing:border-box;" +
                    "overflow-y:auto;padding:8px;min-height:50px;" +
                    "cursor:pointer;";
                container.appendChild(mdDiv);

                // Editing textarea layer (same grid cell, hidden via opacity)
                const textarea = document.createElement("textarea");
                textarea.className = "comfy-multiline-input";
                textarea.style.cssText =
                    "grid-area:1/1/2/2;box-sizing:border-box;" +
                    "resize:none;padding:8px;min-height:50px;" +
                    "opacity:0;pointer-events:none;" +
                    "font-size:var(--comfy-textarea-font-size);" +
                    "border:none;background:transparent;";
                container.appendChild(textarea);

                // --- Internal state ---
                let isEditing = false;

                function renderMarkdown() {
                    const raw = textWidget?.value ?? "";
                    loadLibraries().then(() => {
                        mdDiv.innerHTML = renderMarkdownFull(raw);
                    }).catch((err) => {
                        mdDiv.innerHTML =
                            `<pre style="color:#ff6b6b;">Markdown render error: ${escapeHtml(err.message)}\n\n${escapeHtml(raw)}</pre>`;
                    });
                }

                function enterEditMode() {
                    if (isEditing) return;
                    isEditing = true;
                    textarea.value = textWidget?.value ?? "";
                    // Show textarea, hide rendered markdown (opacity swap)
                    textarea.style.opacity = "1";
                    textarea.style.pointerEvents = "all";
                    mdDiv.style.opacity = "0";
                    mdDiv.style.pointerEvents = "none";
                    setTimeout(() => textarea.focus(), 0);
                }

                function exitEditMode() {
                    if (!isEditing) return;
                    isEditing = false;
                    // Sync edited text back to the original widget
                    if (textWidget) {
                        textWidget.value = textarea.value;
                    }
                    // Hide textarea, show rendered markdown (opacity swap)
                    textarea.style.opacity = "0";
                    textarea.style.pointerEvents = "none";
                    mdDiv.style.opacity = "1";
                    mdDiv.style.pointerEvents = "auto";
                    renderMarkdown();
                }

                // Single-click on rendered markdown → enter edit mode
                mdDiv.addEventListener("click", (e) => {
                    e.stopPropagation();
                    enterEditMode();
                });

                // Prevent click on textarea from propagating (avoids
                // re-triggering enter or canvas interactions)
                textarea.addEventListener("click", (e) => {
                    e.stopPropagation();
                });

                // ESC → exit edit mode
                textarea.addEventListener("keydown", (e) => {
                    if (e.key === "Escape") {
                        e.preventDefault();
                        e.stopPropagation();
                        exitEditMode();
                    }
                    // Stop ALL key events from reaching the canvas so that
                    // typing inside the textarea doesn't trigger shortcuts
                    e.stopPropagation();
                });

                // Blur (click elsewhere) → exit edit mode
                textarea.addEventListener("blur", () => {
                    exitEditMode();
                });

                // Stop pointer events from reaching the canvas while editing
                for (const evt of ["pointerdown", "pointermove", "pointerup"]) {
                    textarea.addEventListener(evt, (e) => e.stopPropagation());
                }

                // --- Register as a DOM widget ---
                const mdWidget = this.addDOMWidget(
                    "markdown_preview",
                    "enhanced_markdown",
                    container,
                    {
                        getValue() {
                            return textWidget?.value ?? "";
                        },
                        setValue(v) {
                            if (textWidget) textWidget.value = v;
                            renderMarkdown();
                        }
                    }
                );
                mdWidget.inputEl = container;
                mdWidget.serialize = false;
                // Match the core's minimum node size for multiline widgets
                mdWidget.options.minNodeSize = [400, 200];

                // --- Hide the original text widget ---
                // The framework-created "text" widget is still used for
                // serialization and value storage, but we don't need to show
                // it because our custom widget handles display + editing.
                if (textWidget) {
                    textWidget.hidden = true;
                    textWidget.options = textWidget.options || {};
                    textWidget.options.hidden = true;
                }

                // Initial render
                renderMarkdown();

                return result;
            };

            // Handle execution results — update the markdown preview
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                const r = onExecuted?.apply(this, [message]);
                const raw = message?.text ?? "";
                const val = Array.isArray(raw) ? raw.join("\n") : raw;
                // Sync back to the text widget (source of truth)
                const tw = this.widgets?.find(w => w.name === "text");
                if (tw) tw.value = val;
                // Re-render the markdown preview
                const mdw = this.widgets?.find(
                    w => w.name === "markdown_preview"
                );
                if (mdw) mdw.value = val;
                return r;
            };
        }

        // ==================================================================
        // SimpleMarkdownStringDisplay
        //   Display an input string as markdown or plaintext (read-only).
        //   The Python-side display_mode BOOLEAN widget controls the toggle.
        //   Two preview widgets share the name "preview".
        // ==================================================================
        if (nodeData.name === "SimpleMarkdownStringDisplay") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated
                    ? onNodeCreated.apply(this, [])
                    : undefined;

                // --- Enhanced markdown preview widget ---
                const mdWidget = addEnhancedMarkdownWidget(this, "preview");

                // --- Plaintext preview widget ---
                const plainWidget = ComfyWidgets["STRING"](
                    this,
                    "preview",
                    ["STRING", { multiline: true }],
                    app
                ).widget;

                // Sync visibility from the Python-side display_mode widget
                const syncVisibility = () => {
                    const dmw = this.widgets?.find(w => w.name === "display_mode");
                    // display_mode: True = "raw text", False = "markdown"
                    const showRaw = dmw?.value ?? false;

                    mdWidget.hidden = showRaw;
                    mdWidget.options.hidden = showRaw;
                    plainWidget.hidden = !showRaw;
                    plainWidget.options.hidden = !showRaw;
                };

                // Hook into display_mode widget callback
                const dmw = this.widgets?.find(w => w.name === "display_mode");
                if (dmw) {
                    const origCb = dmw.callback;
                    dmw.callback = (value) => {
                        if (origCb) origCb(value);
                        syncVisibility();
                    };
                }

                // Configure widgets
                mdWidget.serialize = false;

                plainWidget.options.read_only = true;
                if (plainWidget.element) {
                    plainWidget.element.readOnly = true;
                    plainWidget.element.disabled = true;
                }
                if (plainWidget.inputEl) {
                    plainWidget.inputEl.readOnly = true;
                    plainWidget.inputEl.disabled = true;
                }
                plainWidget.serialize = false;

                // Initial state: markdown visible (default display_mode = false)
                plainWidget.hidden = true;
                plainWidget.options.hidden = true;

                syncVisibility();

                return result;
            };

            // Handle execution results
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                const r = onExecuted?.apply(this, [message]);
                const previewWidgets =
                    this.widgets?.filter(w => w.name === "preview") ?? [];
                for (const w of previewWidgets) {
                    const text = message?.text ?? "";
                    w.value = Array.isArray(text) ? text.join("\n") : text;
                }
                return r;
            };
        }
    }
});
