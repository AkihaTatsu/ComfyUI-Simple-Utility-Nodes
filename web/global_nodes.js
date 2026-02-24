import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { installPassthroughTypeResolver } from "./type_resolver.js";

app.registerExtension({
    name: "SimpleUtility.GlobalNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Apply pale_blue color to both global variable nodes
        if (nodeData.name === "SimpleGlobalVariableInput" || 
            nodeData.name === "SimpleGlobalVariableOutput") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;
                
                // Set ComfyUI's preset pale_blue color
                const paleBlueColor = LGraphCanvas.node_colors.pale_blue;
                if (paleBlueColor) {
                    this.color = paleBlueColor.color;
                    this.bgcolor = paleBlueColor.bgcolor;
                }
                
                return result;
            };
        }

        // Auto-type-resolving for SimpleGlobalVariableInput
        // Input slot 1 = 'anything' (optional passthrough), Output slot 0 = 'passthrough'
        if (nodeData.name === "SimpleGlobalVariableInput") {
            installPassthroughTypeResolver(nodeType, 1, 0);
        }

        // ── SimpleGlobalImagePreview ──────────────────────────────
        if (nodeData.name === "SimpleGlobalImagePreview") {

            // Shared state across all instances of this node type.
            // Every instance shows the same latest image.
            const shared = {
                imgEl: null,           // HTMLImageElement currently loaded
                blobUrl: null,         // Object-URL for KSampler step previews
                sourceLabel: "",       // human-readable label shown under the image
                lastKey: null,         // dedup key for executed-event images
                listeners: new Set(),  // all node instances to repaint on update
            };

            /** Notify every instance to redraw */
            function repaintAll() {
                for (const node of shared.listeners) {
                    node.setDirtyCanvas(true, true);
                }
            }

            /**
             * Show an image from an ``executed`` event.
             * @param {{filename:string, subfolder:string, type:string}} info
             */
            function showExecutedImage(info) {
                const key = `${info.type}/${info.subfolder || ""}/${info.filename}`;
                if (key === shared.lastKey) return; // no change
                shared.lastKey = key;

                const url = api.apiURL(
                    `/view?filename=${encodeURIComponent(info.filename)}`
                    + `&type=${encodeURIComponent(info.type)}`
                    + `&subfolder=${encodeURIComponent(info.subfolder || "")}`
                    + `&t=${Date.now()}`
                );

                const img = new Image();
                img.onload = () => {
                    // Revoke previous blob URL if any
                    if (shared.blobUrl) { URL.revokeObjectURL(shared.blobUrl); shared.blobUrl = null; }
                    shared.imgEl = img;
                    shared.sourceLabel = `${info.filename}  (${img.naturalWidth}×${img.naturalHeight})`;
                    repaintAll();
                };
                img.src = url;
            }

            /**
             * Show a KSampler step preview from a binary blob.
             * @param {Blob} blob
             */
            function showPreviewBlob(blob) {
                if (shared.blobUrl) URL.revokeObjectURL(shared.blobUrl);
                shared.blobUrl = URL.createObjectURL(blob);
                shared.lastKey = null; // allow next executed-event to overwrite

                const img = new Image();
                img.onload = () => {
                    shared.imgEl = img;
                    shared.sourceLabel = "KSampler step preview";
                    repaintAll();
                };
                img.src = shared.blobUrl;
            }

            // ── Global listeners (registered once, not per-node) ──
            let globalListenersInstalled = false;

            function installGlobalListeners() {
                if (globalListenersInstalled) return;
                globalListenersInstalled = true;

                // 1. Listen to "executed" events — these fire when any node
                //    returns a ui dict with images (PreviewImage, SaveImage, etc.)
                api.addEventListener("executed", (event) => {
                    const detail = event.detail;
                    if (!detail) return;
                    const output = detail.output ?? detail;
                    if (output && output.images && output.images.length > 0) {
                        const latest = output.images[output.images.length - 1];
                        showExecutedImage(latest);
                    }
                });

                // 2. Listen to "b_preview" — binary KSampler latent step previews.
                //    ComfyUI's api.js dispatches this as a CustomEvent whose detail
                //    is a Blob.
                api.addEventListener("b_preview", (event) => {
                    if (event.detail instanceof Blob) {
                        showPreviewBlob(event.detail);
                    }
                });
            }

            // ── Node lifecycle ──────────────────────────────────────

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;

                // Pale-blue colour
                const c = LGraphCanvas.node_colors?.pale_blue;
                if (c) { this.color = c.color; this.bgcolor = c.bgcolor; }

                // Register this instance for repaints
                shared.listeners.add(this);

                // "Open in New Tab" button
                this.addWidget("button", "🔎 Open Fullscreen Viewer", null, () => {
                    window.open(
                        `${window.location.origin}/simple_utility/global_image_preview/viewer`,
                        "_blank"
                    );
                });

                installGlobalListeners();

                // Reasonable initial size
                this.setSize([320, 340]);

                return result;
            };

            // Prevent ComfyUI from treating this node's (empty) ui output as
            // an image that should go into the global image feed.
            nodeType.prototype.onExecuted = function (_output) {
                // intentionally empty — do NOT set this.imgs or this.images
            };

            // ── Canvas drawing ──────────────────────────────────────
            const onDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function (ctx) {
                if (onDrawForeground) onDrawForeground.apply(this, arguments);

                const img = shared.imgEl;
                if (!img || !img.complete || !img.naturalWidth) {
                    // Placeholder
                    ctx.save();
                    ctx.fillStyle = "#556";
                    ctx.font = "13px sans-serif";
                    ctx.textAlign = "center";
                    const y0 = this.computeSize()[1];
                    ctx.fillText("⏳ Waiting for preview images…", this.size[0] / 2, y0 + 30);
                    ctx.restore();
                    return;
                }

                // Area below widgets
                const widgetH = LiteGraph.NODE_WIDGET_HEIGHT * (this.widgets ? this.widgets.length : 0) + 16;
                const pad = 6;
                const aW = this.size[0] - pad * 2;
                const aH = this.size[1] - widgetH - pad;
                if (aW <= 0 || aH <= 0) return;

                const iW = img.naturalWidth;
                const iH = img.naturalHeight;
                const scale = Math.min(aW / iW, aH / iH, 1);
                const dw = iW * scale;
                const dh = iH * scale;
                const dx = pad + (aW - dw) / 2;
                const dy = widgetH + (aH - dh) / 2;

                ctx.save();
                ctx.fillStyle = "#222";
                ctx.fillRect(dx, dy, dw, dh);
                ctx.drawImage(img, dx, dy, dw, dh);
                ctx.restore();
            };

            // ── Cleanup ─────────────────────────────────────────────
            const onRemoved = nodeType.prototype.onRemoved;
            nodeType.prototype.onRemoved = function () {
                shared.listeners.delete(this);
                if (onRemoved) onRemoved.apply(this, arguments);
            };

            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function (info) {
                if (onConfigure) onConfigure.apply(this, arguments);
                shared.listeners.add(this);
                installGlobalListeners();
            };
        }
    }
});
