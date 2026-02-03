import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "SimpleUtility.TimeNodes",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "SimpleTimer") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;
                
                // Create a multiline string widget to display the timer value
                const widget = ComfyWidgets["STRING"](
                    this,
                    "display",
                    ["STRING", { multiline: true }],
                    app
                ).widget;
                
                widget.inputEl.readOnly = true;
                widget.serializeValue = async () => "";
                
                this.displayWidget = widget;
                
                return result;
            };
            
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                const r = onExecuted?.apply(this, [message]);
                
                if (message?.text?.[0] != null && this.displayWidget) {
                    this.displayWidget.value = message.text[0];
                }
                
                return r;
            };
        }
        
        if (nodeData.name === "SimpleCurrentDatetime") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const result = onNodeCreated ? onNodeCreated.apply(this, []) : undefined;
                
                // Create a multiline string widget to display the datetime value
                const widget = ComfyWidgets["STRING"](
                    this,
                    "display",
                    ["STRING", { multiline: true }],
                    app
                ).widget;
                
                widget.inputEl.readOnly = true;
                widget.serializeValue = async () => "";
                
                this.displayWidget = widget;
                
                return result;
            };
            
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                const r = onExecuted?.apply(this, [message]);
                
                if (message?.text?.[0] != null && this.displayWidget) {
                    this.displayWidget.value = message.text[0];
                }
                
                return r;
            };
        }
    }
});
