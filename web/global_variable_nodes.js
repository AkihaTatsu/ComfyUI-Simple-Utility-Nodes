import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "SimpleUtility.GlobalVariableNodes",
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
    }
});
