/**
 * type_resolver.js — Shared auto-type-resolving utilities for passthrough /
 * switch nodes whose slots are declared as "*" (anything).
 *
 * These helpers install an `onConnectionsChange` handler that propagates the
 * concrete type flowing through the node so that LiteGraph link colours match
 * the actual data type.
 *
 * Exports:
 *   installPassthroughTypeResolver(nodeType, inputSlot, outputSlot)
 *   installSwitchTypeResolver(nodeType)
 *   installInversedSwitchTypeResolver(nodeType)
 */

import { app } from "../../scripts/app.js";

// ===========================================================================
// Low-level helpers
// ===========================================================================

/**
 * Try to resolve a concrete type from a single input slot's upstream source.
 * Returns the type string, or "*" if unresolved.
 */
function resolveFromInput(node, slotIndex) {
    const inp = node.inputs?.[slotIndex];
    if (inp?.link == null) return "*";
    const link = app.graph.links[inp.link];
    if (!link) return "*";
    const srcNode = app.graph.getNodeById(link.origin_id);
    if (srcNode) {
        const srcOut = srcNode.outputs?.[link.origin_slot];
        if (srcOut?.type && srcOut.type !== "*") return srcOut.type;
    }
    // Fallback: stored link type
    if (link.type && link.type !== "*") return link.type;
    return "*";
}

/**
 * Try to resolve a concrete type from a single output slot's downstream
 * targets.  Returns the type string, or "*" if unresolved.
 */
function resolveFromOutput(node, slotIndex) {
    const out = node.outputs?.[slotIndex];
    if (!out?.links?.length) return "*";
    for (const lid of out.links) {
        const link = app.graph.links[lid];
        if (!link) continue;
        const tgtNode = app.graph.getNodeById(link.target_id);
        if (!tgtNode) continue;
        const tgtInput = tgtNode.inputs?.[link.target_slot];
        if (tgtInput?.type && tgtInput.type !== "*") return tgtInput.type;
        // If target is a Reroute with a resolved type
        if (tgtNode.outputs?.[0]?.type && tgtNode.outputs[0].type !== "*") {
            return tgtNode.outputs[0].type;
        }
    }
    return "*";
}

/**
 * Set the type on an output slot and colour all its outgoing links.
 * @param {string|null} displayName – if non-null, also overwrite the slot name.
 */
function applyTypeToOutput(node, slotIndex, resolvedType, displayName = null) {
    const out = node.outputs?.[slotIndex];
    if (!out) return;
    out.type = resolvedType;
    if (displayName !== null) out.name = displayName;
    const color = LGraphCanvas.link_type_colors?.[resolvedType];
    if (out.links) {
        for (const lid of out.links) {
            const link = app.graph.links[lid];
            if (link) {
                link.type = resolvedType;
                if (color) link.color = color;
                else delete link.color;
            }
        }
    }
}

/**
 * Colour the incoming link on an input slot.
 */
function colorInputLink(node, slotIndex, resolvedType) {
    const inp = node.inputs?.[slotIndex];
    if (inp?.link == null) return;
    const link = app.graph.links[inp.link];
    if (!link) return;
    const color = LGraphCanvas.link_type_colors?.[resolvedType];
    link.type = resolvedType;
    if (color) link.color = color;
    else delete link.color;
}

// ===========================================================================
// High-level installer functions
// ===========================================================================

/**
 * Passthrough: single `*` input → single `*` output.
 *
 * Used by SimpleTimer, SimpleCurrentDatetime, SimplePrintToConsole,
 * SimpleGlobalVariableInput, etc.
 *
 * @param {Object} nodeType               – node prototype from beforeRegisterNodeDef
 * @param {number} passthroughInputSlot    – index of the `*` typed input  (default 0)
 * @param {number} passthroughOutputSlot   – index of the `*` typed output (default 0)
 */
export function installPassthroughTypeResolver(
    nodeType,
    passthroughInputSlot = 0,
    passthroughOutputSlot = 0
) {
    const orig = nodeType.prototype.onConnectionsChange;

    nodeType.prototype.onConnectionsChange = function (...args) {
        orig?.apply(this, args);

        let type = resolveFromInput(this, passthroughInputSlot);
        if (type === "*") type = resolveFromOutput(this, passthroughOutputSlot);

        applyTypeToOutput(
            this,
            passthroughOutputSlot,
            type,
            type !== "*" ? type : "passthrough"
        );
        colorInputLink(this, passthroughInputSlot, type);
        app.graph.setDirtyCanvas(true, true);
    };
}

/**
 * Switch: many `*` inputs → one `*` output.
 *
 * Used by SimpleSwitchWithRandomMode.
 */
export function installSwitchTypeResolver(nodeType) {
    const orig = nodeType.prototype.onConnectionsChange;

    nodeType.prototype.onConnectionsChange = function (...args) {
        orig?.apply(this, args);

        let type = "*";
        // Check every input for a concrete upstream type
        if (this.inputs) {
            for (let i = 0; i < this.inputs.length; i++) {
                type = resolveFromInput(this, i);
                if (type !== "*") break;
            }
        }
        // Fallback: check the single output's downstream targets
        if (type === "*") type = resolveFromOutput(this, 0);

        applyTypeToOutput(this, 0, type, type !== "*" ? type : "output");

        // Colour all wildcard input links
        if (this.inputs) {
            for (let i = 0; i < this.inputs.length; i++) {
                if (this.inputs[i].type === "*") colorInputLink(this, i, type);
            }
        }
        app.graph.setDirtyCanvas(true, true);
    };
}

/**
 * Inversed switch: one `*` input → many `*` outputs.
 *
 * Used by SimpleInversedSwitchWithRandomMode.
 */
export function installInversedSwitchTypeResolver(nodeType) {
    const orig = nodeType.prototype.onConnectionsChange;

    nodeType.prototype.onConnectionsChange = function (...args) {
        orig?.apply(this, args);

        let type = resolveFromInput(this, 0);
        // Fallback: scan all output targets
        if (type === "*" && this.outputs) {
            for (let i = 0; i < this.outputs.length; i++) {
                type = resolveFromOutput(this, i);
                if (type !== "*") break;
            }
        }

        // Apply to every output slot
        if (this.outputs) {
            for (let i = 0; i < this.outputs.length; i++) {
                applyTypeToOutput(this, i, type);
            }
        }
        colorInputLink(this, 0, type);
        app.graph.setDirtyCanvas(true, true);
    };
}
