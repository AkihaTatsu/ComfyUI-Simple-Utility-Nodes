import { app } from "../../scripts/app.js";

// Global state for library loading
let librariesLoaded = false;
let librariesLoading = false;
const libraryLoadCallbacks = [];

/**
 * Load external libraries for Markdown and KaTeX rendering.
 * Uses marked.js for Markdown, KaTeX for math, and other extensions.
 */
async function loadLibraries() {
    if (librariesLoaded) return Promise.resolve();
    if (librariesLoading) {
        return new Promise((resolve) => {
            libraryLoadCallbacks.push(resolve);
        });
    }
    
    librariesLoading = true;
    
    try {
        // Load KaTeX CSS
        const katexCss = document.createElement("link");
        katexCss.rel = "stylesheet";
        katexCss.href = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css";
        katexCss.crossOrigin = "anonymous";
        document.head.appendChild(katexCss);
        
        // Load KaTeX JS
        await loadScript("https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js");
        
        // Load marked.js
        await loadScript("https://cdn.jsdelivr.net/npm/marked@12.0.0/marked.min.js");
        
        // Load DOMPurify for sanitization
        await loadScript("https://cdn.jsdelivr.net/npm/dompurify@3.0.8/dist/purify.min.js");
        
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
 * Load a script from URL and return a promise.
 */
function loadScript(url) {
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = url;
        script.crossOrigin = "anonymous";
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

/**
 * Emoji map for common GitHub-style emojis.
 */
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

/**
 * Replace :emoji_name: patterns with actual emoji characters.
 */
function replaceEmojis(text) {
    return text.replace(/:([a-zA-Z0-9_+-]+):/g, (match, name) => {
        return EMOJI_MAP[name.toLowerCase()] || match;
    });
}

/**
 * Render KaTeX math expressions in text.
 * Supports both inline ($...$) and block ($$...$$) math.
 */
function renderMath(text) {
    if (typeof katex === "undefined") return text;
    
    // Block math ($$...$$)
    text = text.replace(/\$\$([\s\S]*?)\$\$/g, (match, math) => {
        try {
            return katex.renderToString(math.trim(), { displayMode: true, throwOnError: false });
        } catch (e) {
            console.warn("[SimpleMarkdown] KaTeX block error:", e);
            return `<span class="katex-error">${match}</span>`;
        }
    });
    
    // Inline math ($...$) - avoid matching $$ and be careful with escaped $
    text = text.replace(/(?<!\$)\$(?!\$)((?:\\.|[^$\\])+)\$(?!\$)/g, (match, math) => {
        try {
            return katex.renderToString(math.trim(), { displayMode: false, throwOnError: false });
        } catch (e) {
            console.warn("[SimpleMarkdown] KaTeX inline error:", e);
            return `<span class="katex-error">${match}</span>`;
        }
    });
    
    return text;
}

/**
 * Render markdown to HTML with all extensions.
 */
function renderMarkdown(text) {
    if (!text) return "";
    
    // Pre-process: Replace emojis
    let processed = replaceEmojis(text);
    
    // Pre-process: Handle math before markdown parsing (protect from markdown processing)
    const mathBlocks = [];
    let mathIndex = 0;
    
    // Protect block math
    processed = processed.replace(/\$\$([\s\S]*?)\$\$/g, (match) => {
        const placeholder = `%%MATH_BLOCK_${mathIndex}%%`;
        mathBlocks.push({ placeholder, content: match });
        mathIndex++;
        return placeholder;
    });
    
    // Protect inline math
    processed = processed.replace(/(?<!\$)\$(?!\$)((?:\\.|[^$\\])+)\$(?!\$)/g, (match) => {
        const placeholder = `%%MATH_INLINE_${mathIndex}%%`;
        mathBlocks.push({ placeholder, content: match });
        mathIndex++;
        return placeholder;
    });
    
    // Configure marked for GitHub Flavored Markdown
    if (typeof marked !== "undefined") {
        marked.setOptions({
            gfm: true,
            breaks: true,
            tables: true,
            sanitize: false,
            smartLists: true,
            smartypants: false,
            xhtml: false
        });
        
        processed = marked.parse(processed);
    }
    
    // Restore and render math
    mathBlocks.forEach(({ placeholder, content }) => {
        const rendered = renderMath(content);
        processed = processed.replace(placeholder, rendered);
    });
    
    // Sanitize HTML for security (allow safe tags and attributes)
    if (typeof DOMPurify !== "undefined") {
        processed = DOMPurify.sanitize(processed, {
            ADD_TAGS: ["math", "semantics", "mrow", "mi", "mo", "mn", "msup", "msub", "mfrac", "mover", "munder", "munderover", "msqrt", "mroot", "mtable", "mtr", "mtd", "annotation"],
            ADD_ATTR: ["xmlns", "mathvariant", "class", "style"],
            ALLOW_DATA_ATTR: true
        });
    }
    
    return processed;
}

/**
 * Create the markdown display/edit container widget.
 */
function createMarkdownWidget(node, widgetName, initialText, isEditable = true) {
    const container = document.createElement("div");
    container.className = "simple-markdown-container";
    container.style.cssText = `
        width: 100%;
        height: 100%;
        min-height: 100px;
        box-sizing: border-box;
        position: relative;
        display: flex;
        flex-direction: column;
        flex: 1;
    `;
    
    // Create render display area
    const renderArea = document.createElement("div");
    renderArea.className = "simple-markdown-render";
    renderArea.style.cssText = `
        width: 100%;
        flex: 1;
        min-height: 80px;
        padding: 10px;
        box-sizing: border-box;
        overflow: auto;
        background: rgba(0, 0, 0, 0.2);
        border-radius: 4px;
        cursor: ${isEditable ? "text" : "default"};
        font-size: 13px;
        line-height: 1.5;
        color: #e0e0e0;
    `;
    
    // Create edit textarea (only for editable mode)
    let editArea = null;
    if (isEditable) {
        editArea = document.createElement("textarea");
        editArea.className = "simple-markdown-edit";
        editArea.style.cssText = `
            width: 100%;
            flex: 1;
            min-height: 80px;
            padding: 10px;
            box-sizing: border-box;
            resize: none;
            background: rgba(30, 30, 30, 0.95);
            border: 2px solid #4a9eff;
            border-radius: 4px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            line-height: 1.5;
            color: #e0e0e0;
            display: none;
            overflow: auto;
        `;
        editArea.value = initialText;
        editArea.placeholder = "Enter markdown text here...";
    }
    
    // State management
    let isEditing = false;
    let currentText = initialText;
    
    // Update render area content
    function updateRender() {
        loadLibraries().then(() => {
            renderArea.innerHTML = renderMarkdown(currentText);
        }).catch((err) => {
            renderArea.innerHTML = `<pre style="color: #ff6b6b;">Error loading libraries: ${err.message}\n\nRaw text:\n${currentText}</pre>`;
        });
    }
    
    // Enter edit mode
    function enterEditMode() {
        if (!isEditable || isEditing) return;
        isEditing = true;
        renderArea.style.display = "none";
        editArea.style.display = "block";
        editArea.value = currentText;
        editArea.focus();
        editArea.selectionStart = editArea.value.length;
    }
    
    // Exit edit mode
    function exitEditMode() {
        if (!isEditing) return;
        isEditing = false;
        currentText = editArea.value;
        renderArea.style.display = "block";
        editArea.style.display = "none";
        updateRender();
        
        // Update the hidden text widget
        const textWidget = node.widgets?.find(w => w.name === "text");
        if (textWidget) {
            textWidget.value = currentText;
        }
        
        app.graph.setDirtyCanvas(true, true);
    }
    
    // Event listeners for editable mode
    if (isEditable && editArea) {
        // Click to edit
        renderArea.addEventListener("click", enterEditMode);
        
        // ESC to exit edit mode
        editArea.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                e.preventDefault();
                exitEditMode();
            }
        });
        
        // Click outside to exit edit mode
        editArea.addEventListener("blur", (e) => {
            // Small delay to allow for potential click on container
            setTimeout(() => {
                if (isEditing && !container.contains(document.activeElement)) {
                    exitEditMode();
                }
            }, 100);
        });
    }
    
    // Append elements
    container.appendChild(renderArea);
    if (editArea) {
        container.appendChild(editArea);
    }
    
    // Create DOM widget
    const widget = node.addDOMWidget(widgetName, "markdown", container);
    
    // Store references
    widget.markdownContainer = container;
    widget.markdownRenderArea = renderArea;
    widget.markdownEditArea = editArea;
    widget.isEditing = () => isEditing;
    
    // Public method to update content (always renders as markdown)
    widget.updateContent = (text) => {
        currentText = text;
        updateRender();
        if (editArea) {
            editArea.value = text;
        }
    };
    
    // Initial render
    updateRender();
    
    return widget;
}

/**
 * Escape HTML special characters.
 */
function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Inject CSS styles for markdown rendering.
 */
function injectStyles() {
    if (document.getElementById("simple-markdown-styles")) return;
    
    const style = document.createElement("style");
    style.id = "simple-markdown-styles";
    style.textContent = `
        .simple-markdown-render {
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        
        .simple-markdown-render h1,
        .simple-markdown-render h2,
        .simple-markdown-render h3,
        .simple-markdown-render h4,
        .simple-markdown-render h5,
        .simple-markdown-render h6 {
            margin: 0.5em 0 0.3em 0;
            padding: 0;
            font-weight: 600;
            line-height: 1.25;
            color: #fff;
        }
        
        .simple-markdown-render h1 { font-size: 1.6em; border-bottom: 1px solid #444; padding-bottom: 0.2em; }
        .simple-markdown-render h2 { font-size: 1.4em; border-bottom: 1px solid #333; padding-bottom: 0.2em; }
        .simple-markdown-render h3 { font-size: 1.2em; }
        .simple-markdown-render h4 { font-size: 1.1em; }
        .simple-markdown-render h5 { font-size: 1em; }
        .simple-markdown-render h6 { font-size: 0.9em; color: #888; }
        
        .simple-markdown-render p {
            margin: 0.5em 0;
        }
        
        .simple-markdown-render a {
            color: #58a6ff;
            text-decoration: none;
        }
        
        .simple-markdown-render a:hover {
            text-decoration: underline;
        }
        
        .simple-markdown-render code {
            background: rgba(110, 118, 129, 0.4);
            padding: 0.15em 0.3em;
            border-radius: 3px;
            font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            font-size: 0.9em;
        }
        
        .simple-markdown-render pre {
            background: rgba(30, 30, 30, 0.8);
            padding: 10px;
            border-radius: 6px;
            overflow-x: auto;
            margin: 0.5em 0;
        }
        
        .simple-markdown-render pre code {
            background: transparent;
            padding: 0;
        }
        
        .simple-markdown-render blockquote {
            border-left: 3px solid #4a9eff;
            margin: 0.5em 0;
            padding: 0.25em 1em;
            color: #aaa;
            background: rgba(74, 158, 255, 0.1);
        }
        
        .simple-markdown-render ul,
        .simple-markdown-render ol {
            margin: 0.5em 0;
            padding-left: 1.5em;
        }
        
        .simple-markdown-render li {
            margin: 0.2em 0;
        }
        
        .simple-markdown-render table {
            border-collapse: collapse;
            width: 100%;
            margin: 0.5em 0;
        }
        
        .simple-markdown-render th,
        .simple-markdown-render td {
            border: 1px solid #444;
            padding: 6px 10px;
            text-align: left;
        }
        
        .simple-markdown-render th {
            background: rgba(74, 158, 255, 0.2);
            font-weight: 600;
        }
        
        .simple-markdown-render tr:nth-child(even) {
            background: rgba(255, 255, 255, 0.03);
        }
        
        .simple-markdown-render img {
            max-width: 100%;
            height: auto;
            border-radius: 4px;
        }
        
        .simple-markdown-render hr {
            border: none;
            border-top: 1px solid #444;
            margin: 1em 0;
        }
        
        .simple-markdown-render input[type="checkbox"] {
            margin-right: 0.5em;
        }
        
        .simple-markdown-render .katex {
            font-size: 1em;
        }
        
        .simple-markdown-render .katex-display {
            margin: 0.5em 0;
            overflow-x: auto;
            overflow-y: hidden;
        }
        
        .katex-error {
            color: #ff6b6b;
            background: rgba(255, 107, 107, 0.1);
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        .simple-markdown-render del {
            text-decoration: line-through;
            color: #888;
        }
        
        .simple-markdown-render mark {
            background: rgba(255, 255, 0, 0.3);
            padding: 0.1em 0.2em;
            border-radius: 2px;
        }
    `;
    document.head.appendChild(style);
}

// Inject styles on load
injectStyles();

app.registerExtension({
    name: "SimpleUtility.StringNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        
        // SimpleMarkdownString: Editable markdown with string output
        if (nodeData.name === "SimpleMarkdownString") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;
                
                // Hide the original text widget
                const textWidget = this.widgets?.find(w => w.name === "text");
                if (textWidget) {
                    textWidget.type = "hidden";
                    textWidget.computeSize = () => [0, 0];
                    if (textWidget.element) {
                        textWidget.element.style.display = "none";
                    }
                }
                
                // Create markdown widget
                const initialText = textWidget?.value || "";
                this.markdownWidget = createMarkdownWidget(this, "markdown_display", initialText, true);
                
                // Set minimum size for the node
                // Width: 300 (reasonable for markdown content)
                // Height: 200 (title ~30 + markdown area ~150 + padding ~20)
                this.setSize([Math.max(this.size[0], 300), Math.max(this.size[1], 200)]);
                this.computeSize = ((origFunc) => {
                    return function() {
                        const size = origFunc ? origFunc.apply(this, arguments) : [300, 200];
                        return [Math.max(size[0], 300), Math.max(size[1], 200)];
                    };
                })(this.computeSize);
                
                return result;
            };
            
            // Update widget when loaded from saved workflow
            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function (info) {
                if (onConfigure) {
                    onConfigure.apply(this, arguments);
                }
                
                // Restore text from saved widget values
                setTimeout(() => {
                    const textWidget = this.widgets?.find(w => w.name === "text");
                    if (textWidget && this.markdownWidget) {
                        this.markdownWidget.updateContent(textWidget.value);
                    }
                }, 100);
            };
            
            // Handle execution results
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                const r = onExecuted?.apply(this, [message]);
                
                if (message?.text?.[0] != null && this.markdownWidget && !this.markdownWidget.isEditing()) {
                    this.markdownWidget.updateContent(message.text[0]);
                }
                
                return r;
            };
        }
        
        // SimpleMarkdownStringDisplay: Display input string as markdown or raw text
        if (nodeData.name === "SimpleMarkdownStringDisplay") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;
                
                // Create non-editable markdown display widget
                this.markdownWidget = createMarkdownWidget(this, "markdown_display", "", false);
                
                // Set minimum size for the node
                this.setSize([Math.max(this.size[0], 300), Math.max(this.size[1], 200)]);
                this.computeSize = ((origFunc) => {
                    return function() {
                        const size = origFunc ? origFunc.apply(this, arguments) : [300, 200];
                        return [Math.max(size[0], 300), Math.max(size[1], 200)];
                    };
                })(this.computeSize);
                
                // Store last received text for re-rendering on widget change
                this._lastDisplayText = "";
                
                // Listen for widget value changes to update display mode
                const displayRawWidget = this.widgets?.find(w => w.name === "display_raw_text");
                if (displayRawWidget) {
                    const originalCallback = displayRawWidget.callback;
                    displayRawWidget.callback = (value) => {
                        if (originalCallback) originalCallback(value);
                        // Re-render with the new display mode
                        this._updateDisplay();
                    };
                }
                
                return result;
            };
            
            // Helper method to update display based on current widget value
            nodeType.prototype._updateDisplay = function () {
                if (!this.markdownWidget || !this._lastDisplayText) return;
                
                const displayRawWidget = this.widgets?.find(w => w.name === "display_raw_text");
                const displayRaw = displayRawWidget?.value ?? false;
                
                if (displayRaw) {
                    // Display raw text (escaped HTML in a pre block)
                    this.markdownWidget.markdownRenderArea.innerHTML = `<pre style="white-space: pre-wrap; word-wrap: break-word; margin: 0;">${escapeHtml(this._lastDisplayText)}</pre>`;
                } else {
                    // Display rendered markdown
                    this.markdownWidget.updateContent(this._lastDisplayText);
                }
            };
            
            // Handle execution results
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                const r = onExecuted?.apply(this, [message]);
                
                if (message?.text?.[0] != null && this.markdownWidget) {
                    this._lastDisplayText = message.text[0];
                    this._updateDisplay();
                }
                
                return r;
            };
        }
    }
});
