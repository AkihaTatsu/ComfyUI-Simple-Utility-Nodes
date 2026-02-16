import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "SimpleUtility.ScriptNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "SimplePythonScript") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;

                const node = this;

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
                    setTimeout(() => {
                        this.updateInputVisibility(inputNumWidget.value);
                    }, 100);
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
                    setTimeout(() => {
                        this.updateOutputVisibility(outputNumWidget.value);
                    }, 100);
                }

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

                const newInputCount = this.inputs ? this.inputs.length : 0;
                const slotDelta = newInputCount - prevInputCount;
                const slotHeight = LiteGraph.NODE_SLOT_HEIGHT || 20;
                const currentSize = this.size;
                const minSize = this.computeSize();
                this.setSize([
                    Math.max(currentSize[0], minSize[0]),
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

                const newOutputCount = this.outputs ? this.outputs.length : 0;
                const slotDelta = newOutputCount - prevOutputCount;
                const slotHeight = LiteGraph.NODE_SLOT_HEIGHT || 20;
                const currentSize = this.size;
                const minSize = this.computeSize();
                this.setSize([
                    Math.max(currentSize[0], minSize[0]),
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

                const inputNumWidget = this.widgets?.find(w => w.name === "input_num");
                if (inputNumWidget) {
                    setTimeout(() => {
                        this.updateInputVisibility(inputNumWidget.value);
                    }, 100);
                }

                const outputNumWidget = this.widgets?.find(w => w.name === "output_num");
                if (outputNumWidget) {
                    setTimeout(() => {
                        this.updateOutputVisibility(outputNumWidget.value);
                    }, 100);
                }
            };
        }
    }
});
