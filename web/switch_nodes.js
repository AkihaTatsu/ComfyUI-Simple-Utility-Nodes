import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "SimpleUtility.SwitchNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "SimpleSwitchWithRandomMode") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;
                
                // Find the input_num widget
                const inputNumWidget = this.widgets?.find(w => w.name === "input_num");
                if (inputNumWidget) {
                    const node = this;
                    const originalCallback = inputNumWidget.callback;
                    
                    inputNumWidget.callback = function (value) {
                        if (originalCallback) {
                            originalCallback.apply(this, arguments);
                        }
                        node.updateInputVisibility(value);
                    };
                    
                    // Initial update
                    setTimeout(() => {
                        this.updateInputVisibility(inputNumWidget.value);
                    }, 100);
                }
                
                return result;
            };
            
            nodeType.prototype.updateInputVisibility = function (inputNum) {
                const maxNum = 20;
                
                for (let i = 1; i <= maxNum; i++) {
                    const inputName = `input_${i}`;
                    const inputIndex = this.findInputSlot(inputName);
                    
                    if (i <= inputNum) {
                        // Should be visible
                        if (inputIndex === -1) {
                            this.addInput(inputName, "*");
                        }
                    } else {
                        // Should be hidden
                        if (inputIndex !== -1) {
                            this.removeInput(inputIndex);
                        }
                    }
                }
                
                this.setSize(this.computeSize());
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
            };
        }
        
        if (nodeData.name === "SimpleInversedSwitchWithRandomMode") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;
                
                // Find the output_num widget
                const outputNumWidget = this.widgets?.find(w => w.name === "output_num");
                if (outputNumWidget) {
                    const node = this;
                    const originalCallback = outputNumWidget.callback;
                    
                    outputNumWidget.callback = function (value) {
                        if (originalCallback) {
                            originalCallback.apply(this, arguments);
                        }
                        node.updateOutputVisibility(value);
                    };
                    
                    // Initial update
                    setTimeout(() => {
                        this.updateOutputVisibility(outputNumWidget.value);
                    }, 100);
                }
                
                return result;
            };
            
            nodeType.prototype.updateOutputVisibility = function (outputNum) {
                const maxNum = 20;
                
                for (let i = 1; i <= maxNum; i++) {
                    const outputName = `output_${i}`;
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
                
                this.setSize(this.computeSize());
                app.graph.setDirtyCanvas(true, true);
            };
            
            // Handle loading from saved workflow
            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function (info) {
                if (onConfigure) {
                    onConfigure.apply(this, arguments);
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
