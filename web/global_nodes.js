import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";
import { installPassthroughTypeResolver } from "./type_resolver.js";

app.registerExtension({
    name: "SimpleUtility.GlobalNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // Apply pale_blue color to global variable and VRAM cache nodes
        if (nodeData.name === "SimpleGlobalVariableInput" || 
            nodeData.name === "SimpleGlobalVariableOutput" ||
            nodeData.name === "SimpleGlobalVRAMCacheSaving" ||
            nodeData.name === "SimpleGlobalVRAMCacheLoading" ||
            nodeData.name === "SimpleGlobalVRAMCacheRAMClearing" ||
            nodeData.name === "SimpleGlobalDeepCleanup") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;
                
                // Set ComfyUI's preset pale_blue color
                const paleBlueColor = LGraphCanvas.node_colors.pale_blue;
                if (paleBlueColor) {
                    this.color = paleBlueColor.color;
                    this.bgcolor = paleBlueColor.bgcolor;
                }

                if (nodeData.name === "SimpleGlobalDeepCleanup" && !this._simpleDeepCleanupNote) {
                    this._simpleDeepCleanupNote = true;
                    const widget = ComfyWidgets["STRING"](
                        this,
                        "cleanup_hint",
                        ["STRING", { multiline: true }],
                        app
                    ).widget;

                    widget.value = "Hint: Schedules extra cleanup after the run ends. Visible history/display state is preserved. Multiple Deep Cleanup nodes: end cleanup runs once.";
                    widget.inputEl.readOnly = true;
                    if (widget.element) {
                        widget.element.readOnly = true;
                    }
                    widget.serializeValue = async () => "";
                }
                
                return result;
            };
        }

        // Auto-type-resolving for SimpleGlobalVariableInput
        // Input slot 1 = 'anything' (optional passthrough), Output slot 0 = 'passthrough'
        if (nodeData.name === "SimpleGlobalVariableInput") {
            installPassthroughTypeResolver(nodeType, 1, 0);
        }

        // Auto-type-resolving for VRAM Cache nodes
        // Input slot 0 = 'anything' (optional passthrough), Output slot 0 = 'passthrough'
        if (nodeData.name === "SimpleGlobalVRAMCacheSaving" ||
            nodeData.name === "SimpleGlobalVRAMCacheLoading" ||
            nodeData.name === "SimpleGlobalVRAMCacheRAMClearing") {
            installPassthroughTypeResolver(nodeType, 0, 0);
        }

        // SimpleGlobalDeepCleanup input slot 1 = 'anything', output slot 0 = 'passthrough'
        if (nodeData.name === "SimpleGlobalDeepCleanup") {
            installPassthroughTypeResolver(nodeType, 1, 0);
        }

        // ── SimpleGlobalImagePreview ──────────────────────────────
        if (nodeData.name === "SimpleGlobalImagePreview") {

            // Shared state across all instances of this node type.
            // Every instance shows the same latest media.
            const shared = {
                mediaEl: null,         // HTMLImageElement or HTMLVideoElement currently loaded
                mediaKind: "image",    // "image" | "video"
                blobUrl: null,         // Object-URL for KSampler step previews
                sourceLabel: "",       // human-readable label shown under the image
                lastKey: null,         // dedup key for executed-event images
                listeners: new Set(),  // all node instances to repaint on update
                rafId: null,           // redraw loop while a video is playing
            };

            const MEDIA_KIND_KEY = "_simple_media_kind";
            const MEDIA_KEY = "_simple_media_key";
            const CACHED_URL_KEY = "_simple_cached_url";
            const VIDEO_EXTENSIONS = new Set(["mp4", "webm", "mov", "m4v", "mkv", "avi", "ogv", "ogg"]);

            function animatedIsTruthy(value) {
                if (Array.isArray(value)) return value.some(Boolean);
                return !!value;
            }

            function mediaKindForInfo(info, output = null) {
                const explicit = info?.[MEDIA_KIND_KEY];
                if (explicit === "video" || explicit === "image") return explicit;
                const fmt = String(info?.format || info?.mime_type || "").toLowerCase();
                const filename = String(info?.filename || "");
                const ext = filename.includes(".") ? filename.split(".").pop().toLowerCase() : "";
                if (fmt.startsWith("image/")) return "image";
                if (fmt.startsWith("video/") || VIDEO_EXTENSIONS.has(ext)) {
                    return "video";
                }
                return "image";
            }

            const mediaUrlState = new Map();

            function mediaKeyForInfo(info) {
                return info?.[MEDIA_KEY] || `${info?.type || ""}/${info?.subfolder || ""}/${info?.filename || ""}`;
            }

            function absoluteUrl(url) {
                if (!url) return null;
                if (/^https?:\/\//i.test(url)) return url;
                return api.apiURL(url);
            }

            function originalViewUrl(info) {
                return api.apiURL(
                    `/view?filename=${encodeURIComponent(info.filename)}`
                    + `&type=${encodeURIComponent(info.type)}`
                    + `&subfolder=${encodeURIComponent(info.subfolder || "")}`
                    + `&t=${encodeURIComponent(mediaKeyForInfo(info))}`
                );
            }

            function candidateUrlsForInfo(info) {
                const urls = [];
                const cachedUrl = absoluteUrl(info?.[CACHED_URL_KEY]);
                if (cachedUrl) urls.push(cachedUrl);
                if (info?.filename) urls.push(originalViewUrl(info));
                return [...new Set(urls)];
            }

            function urlStateForInfo(info) {
                const key = mediaKeyForInfo(info);
                const candidates = candidateUrlsForInfo(info);
                const signature = candidates.join("\n");
                let state = mediaUrlState.get(key);
                if (!state || state.signature !== signature) {
                    state = { signature, candidates, index: 0, successUrl: null };
                    mediaUrlState.set(key, state);
                }
                return state;
            }

            function extractMediaItems(output) {
                const items = [];
                const seen = new Set();
                if (!output || typeof output !== "object") return items;
                for (const value of Object.values(output)) {
                    if (!Array.isArray(value)) continue;
                    for (const item of value) {
                        if (!item || typeof item !== "object" || !item.filename) continue;
                        if (seen.has(item)) continue;
                        seen.add(item);
                        items.push(item);
                    }
                }
                return items;
            }

            /** Notify every instance to redraw */
            function repaintAll() {
                for (const node of shared.listeners) {
                    node.setDirtyCanvas(true, true);
                }
            }

            function stopVideoRedraw() {
                if (shared.rafId) {
                    cancelAnimationFrame(shared.rafId);
                    shared.rafId = null;
                }
            }

            function startVideoRedraw(video) {
                stopVideoRedraw();
                const tick = () => {
                    if (shared.mediaEl !== video || shared.mediaKind !== "video") {
                        shared.rafId = null;
                        return;
                    }
                    repaintAll();
                    shared.rafId = requestAnimationFrame(tick);
                };
                shared.rafId = requestAnimationFrame(tick);
            }

            function clearMedia() {
                stopVideoRedraw();
                if (shared.mediaKind === "video" && shared.mediaEl) {
                    try { shared.mediaEl.pause(); } catch (_) {}
                }
                shared.mediaEl = null;
                shared.mediaKind = "image";
            }

            function revokePreviewBlob() {
                if (shared.blobUrl) {
                    URL.revokeObjectURL(shared.blobUrl);
                    shared.blobUrl = null;
                }
            }

            /**
             * Show an image or video from an ``executed`` event.
             * @param {{filename:string, subfolder:string, type:string}} info
             */
            function showExecutedMedia(info, output = null) {
                const key = mediaKeyForInfo(info);
                if (key === shared.lastKey) return; // no change
                shared.lastKey = key;
                const state = urlStateForInfo(info);
                const url = state.successUrl || state.candidates[state.index];
                if (!url) return;

                const mediaKind = mediaKindForInfo(info, output);
                if (mediaKind === "video") {
                    const video = document.createElement("video");
                    video.autoplay = true;
                    video.muted = true;
                    video.loop = true;
                    video.playsInline = true;
                    video.controls = false;
                    video.preload = "auto";
                    video.onloadedmetadata = () => {
                        state.successUrl = url;
                        revokePreviewBlob();
                        clearMedia();
                        shared.mediaEl = video;
                        shared.mediaKind = "video";
                        shared.sourceLabel = `${info.filename}  (${video.videoWidth}×${video.videoHeight})`;
                        repaintAll();
                        startVideoRedraw(video);
                        video.play().catch(() => {});
                    };
                    video.onerror = () => {
                        console.warn("Global Image Preview video load failed:", url);
                        if (state.index < state.candidates.length - 1) {
                            state.index += 1;
                            shared.lastKey = null;
                            showExecutedMedia(info, output);
                        }
                    };
                    video.src = url;
                    return;
                }

                const img = new Image();
                img.onload = () => {
                    state.successUrl = url;
                    revokePreviewBlob();
                    clearMedia();
                    shared.mediaEl = img;
                    shared.mediaKind = "image";
                    shared.sourceLabel = `${info.filename}  (${img.naturalWidth}×${img.naturalHeight})`;
                    repaintAll();
                };
                img.onerror = () => {
                    console.warn("Global Image Preview image load failed:", url);
                    if (state.index < state.candidates.length - 1) {
                        state.index += 1;
                        shared.lastKey = null;
                        showExecutedMedia(info, output);
                    }
                };
                img.src = url;
            }

            async function showLatestServerMedia() {
                try {
                    const resp = await fetch(
                        api.apiURL("/simple_utility/global_image_preview/latest"),
                        { cache: "no-store" }
                    );
                    if (!resp.ok) return;
                    const data = await resp.json();
                    const items = data.images || [];
                    if (items.length > 0) {
                        showExecutedMedia(items[items.length - 1], null);
                    }
                } catch (_) {}
            }

            /**
             * Show a KSampler step preview from a binary blob.
             * @param {Blob} blob
             */
            function showPreviewBlob(blob) {
                revokePreviewBlob();
                shared.blobUrl = URL.createObjectURL(blob);
                shared.lastKey = null; // allow next executed-event to overwrite

                const img = new Image();
                img.onload = () => {
                    clearMedia();
                    shared.mediaEl = img;
                    shared.mediaKind = "image";
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
                    const mediaItems = extractMediaItems(output);
                    if (mediaItems.length > 0) {
                        const latest = mediaItems[mediaItems.length - 1];
                        showExecutedMedia(latest, output);
                        showLatestServerMedia();
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

                const media = shared.mediaEl;
                const isVideo = shared.mediaKind === "video";
                const mediaW = isVideo ? (media?.videoWidth || 0) : (media?.naturalWidth || 0);
                const mediaH = isVideo ? (media?.videoHeight || 0) : (media?.naturalHeight || 0);
                const ready = isVideo ? (media?.readyState >= 2 && mediaW > 0) : (media?.complete && mediaW > 0);
                if (!media || !ready) {
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

                const iW = mediaW;
                const iH = mediaH;
                const scale = Math.min(aW / iW, aH / iH, 1);
                const dw = iW * scale;
                const dh = iH * scale;
                const dx = pad + (aW - dw) / 2;
                const dy = widgetH + (aH - dh) / 2;

                ctx.save();
                ctx.fillStyle = "#222";
                ctx.fillRect(dx, dy, dw, dh);
                ctx.drawImage(media, dx, dy, dw, dh);
                ctx.restore();
            };

            // ── Cleanup ─────────────────────────────────────────────
            const onRemoved = nodeType.prototype.onRemoved;
            nodeType.prototype.onRemoved = function () {
                shared.listeners.delete(this);
                if (shared.listeners.size === 0) {
                    clearMedia();
                }
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
