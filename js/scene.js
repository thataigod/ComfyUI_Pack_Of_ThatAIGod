/**
 * @fileoverview Frontend extension for the Scene node.
 */
import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "ThatAIGod.Scene",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "Scene") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            try {
                const r = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;

                if (!this._sceneWidgetAdded) {
                    this._sceneWidgetAdded = true;
                    try {
                        const w = ComfyWidgets["STRING"](
                            this, "Scene Info",
                            ["STRING", { multiline: true }], app,
                        ).widget;
                        w.inputEl.readOnly = true;
                        w.inputEl.style.overflowY = "auto";
                        w.inputEl.style.height = "84px";
                        w.inputEl.style.minHeight = "84px";
                        w.inputEl.style.maxHeight = "84px";
                        w.computeSize = function () { return [0, 96]; };
                    } catch (e) {
                        console.warn("ThatAIGod: Scene Info widget create error", e);
                    }
                }

                this.size[0] = Math.max(this.size[0], 340);
                this.size[1] = Math.max(this.size[1], 560);

                return r;
            } catch (e) {
                console.error("ThatAIGod: Scene onNodeCreated error", e);
                try { return origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined; }
                catch (_) { return undefined; }
            }
        };

        const origExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            origExecuted?.apply(this, arguments);
            if (!message) return;
            const w = this.widgets && this.widgets.find((w) => w.name === "Scene Info");
            if (w && message.description && message.description[0]) w.value = message.description[0];
        };
    },
});
