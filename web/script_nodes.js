import { app } from "../../scripts/app.js";
import { installPassthroughTypeResolver } from "./type_resolver.js";

app.registerExtension({
    name: "SimpleUtility.ScriptNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "SimplePrintToConsole") {
            installPassthroughTypeResolver(nodeType, 0, 0);
        }

        if (nodeData.name === "SimplePythonScript") {
            // Measure the title width using a canvas context for accuracy
            const _measureTitleWidth = function () {
                const title = "⛏️ Simple Python Script";
                const fontSize = LiteGraph.NODE_TEXT_SIZE || 14;
                const font = `${fontSize}px Arial`;
                try {
                    const canvas = document.createElement("canvas");
                    const ctx = canvas.getContext("2d");
                    ctx.font = font;
                    const textWidth = ctx.measureText(title).width;
                    // Add left padding (NODE_TITLE_HEIGHT=30) + right padding (~10)
                    return Math.ceil(textWidth + 40);
                } catch (e) {
                    // Fallback: estimate based on character count
                    return Math.ceil(title.length * fontSize * 0.6 + 40);
                }
            };

            // Desired default width: 1.5x the title width
            const DEFAULT_WIDTH = Math.ceil(_measureTitleWidth() * 1.5);
            // Desired default height: enough for widgets + 5 rows in textarea
            // Title(30) + input_num widget(20) + output_num widget(20) + script textarea(5 rows * 18px = 90)
            //   + slot rows + padding
            const TEXTAREA_MIN_ROWS = 5;
            const ROW_HEIGHT = 18;
            const DEFAULT_HEIGHT = 30 + 20 + 20 + (TEXTAREA_MIN_ROWS * ROW_HEIGHT) + 60;

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;

                const node = this;
                // Mark that initial setup has not yet completed
                node._initialSetupDone = false;

                // Override minNodeSize set by the multiline STRING widget
                // so it doesn't force a 400px width
                if (this.widgets) {
                    for (const w of this.widgets) {
                        if (w.options && w.options.minNodeSize) {
                            w.options.minNodeSize = [DEFAULT_WIDTH, DEFAULT_HEIGHT];
                        }
                    }
                }

                // Find the input_num widget
                const inputNumWidget = this.widgets?.find(w => w.name === "input_num");
                if (inputNumWidget) {
                    const originalCallback = inputNumWidget.callback;
                    inputNumWidget.callback = function (value) {
                        if (originalCallback) {
                            originalCallback.apply(this, arguments);
                        }
                        node.updateInputVisibility(value);
                    };
                }

                // Find the output_num widget
                const outputNumWidget = this.widgets?.find(w => w.name === "output_num");
                if (outputNumWidget) {
                    const originalCallback = outputNumWidget.callback;
                    outputNumWidget.callback = function (value) {
                        if (originalCallback) {
                            originalCallback.apply(this, arguments);
                        }
                        node.updateOutputVisibility(value);
                    };
                }

                // Single deferred initial setup: update visibility then apply default size
                setTimeout(() => {
                    if (inputNumWidget) {
                        this.updateInputVisibility(inputNumWidget.value);
                    }
                    if (outputNumWidget) {
                        this.updateOutputVisibility(outputNumWidget.value);
                    }
                    // Apply desired default size (overrides computeSize inflation)
                    const slotRows = (this.inputs ? this.inputs.length : 0) + (this.outputs ? this.outputs.length : 0);
                    const slotHeight = LiteGraph.NODE_SLOT_HEIGHT || 20;
                    const desiredHeight = DEFAULT_HEIGHT + slotRows * slotHeight;
                    this.setSize([DEFAULT_WIDTH, desiredHeight]);
                    node._initialSetupDone = true;
                    app.graph.setDirtyCanvas(true, true);
                }, 100);

                return result;
            };

            nodeType.prototype.updateInputVisibility = function (inputNum) {
                const maxNum = 20;

                const prevInputCount = this.inputs ? this.inputs.length : 0;

                for (let i = 1; i <= maxNum; i++) {
                    const inputName = `INPUT${i}`;
                    const inputIndex = this.findInputSlot(inputName);

                    if (i <= inputNum) {
                        // Should be visible (shape: 7 = HollowCircle for optional inputs)
                        if (inputIndex === -1) {
                            this.addInput(inputName, "*", { shape: 7 });
                        }
                    } else {
                        // Should be hidden
                        if (inputIndex !== -1) {
                            this.removeInput(inputIndex);
                        }
                    }
                }

                // Skip size adjustment during initial setup (handled by onNodeCreated)
                if (!this._initialSetupDone) return;

                const newInputCount = this.inputs ? this.inputs.length : 0;
                const slotDelta = newInputCount - prevInputCount;
                const slotHeight = LiteGraph.NODE_SLOT_HEIGHT || 20;
                const currentSize = this.size;
                const minSize = this.computeSize();
                this.setSize([
                    currentSize[0],
                    Math.max(currentSize[1] + slotDelta * slotHeight, minSize[1])
                ]);
                app.graph.setDirtyCanvas(true, true);
            };

            nodeType.prototype.updateOutputVisibility = function (outputNum) {
                const maxNum = 20;

                const prevOutputCount = this.outputs ? this.outputs.length : 0;

                for (let i = 1; i <= maxNum; i++) {
                    const outputName = `OUTPUT${i}`;
                    const outputIndex = this.findOutputSlot(outputName);

                    if (i <= outputNum) {
                        // Should be visible
                        if (outputIndex === -1) {
                            this.addOutput(outputName, "*");
                        }
                    } else {
                        // Should be hidden
                        if (outputIndex !== -1) {
                            this.removeOutput(outputIndex);
                        }
                    }
                }

                // Skip size adjustment during initial setup (handled by onNodeCreated)
                if (!this._initialSetupDone) return;

                const newOutputCount = this.outputs ? this.outputs.length : 0;
                const slotDelta = newOutputCount - prevOutputCount;
                const slotHeight = LiteGraph.NODE_SLOT_HEIGHT || 20;
                const currentSize = this.size;
                const minSize = this.computeSize();
                this.setSize([
                    currentSize[0],
                    Math.max(currentSize[1] + slotDelta * slotHeight, minSize[1])
                ]);
                app.graph.setDirtyCanvas(true, true);
            };

            // Handle loading from saved workflow
            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function (info) {
                if (onConfigure) {
                    onConfigure.apply(this, arguments);
                }

                // Mark setup done so update functions preserve the saved size
                this._initialSetupDone = true;

                // Override minNodeSize for loaded nodes too
                if (this.widgets) {
                    for (const w of this.widgets) {
                        if (w.options && w.options.minNodeSize) {
                            w.options.minNodeSize = [DEFAULT_WIDTH, DEFAULT_HEIGHT];
                        }
                    }
                }

                const savedSize = info.size ? [info.size[0], info.size[1]] : null;
                const inputNumWidget = this.widgets?.find(w => w.name === "input_num");
                const outputNumWidget = this.widgets?.find(w => w.name === "output_num");

                setTimeout(() => {
                    if (inputNumWidget) {
                        this.updateInputVisibility(inputNumWidget.value);
                    }
                    if (outputNumWidget) {
                        this.updateOutputVisibility(outputNumWidget.value);
                    }
                    // Restore saved size after slot updates
                    if (savedSize) {
                        this.setSize(savedSize);
                    }
                    app.graph.setDirtyCanvas(true, true);
                }, 100);
            };
        }
    }
});
