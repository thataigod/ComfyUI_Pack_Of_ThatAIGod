/**
 * @fileoverview Frontend extension for the "Upscale By Size" node.
 *
 * Remembers the last Target value used for each Limit By mode (Max Side /
 * Min Side / Total Pixels) inside the hidden Size Config JSON, and recalls it
 * when the mode is switched.  Mirrors the per-mode memory used by the
 * DynamicResolutionSelector node (see js/resolution_selector.js).
 */
import { app } from "../../scripts/app.js";

// Per-mode Target memory: config keys holding the last Target per Limit By mode.
// Must stay in sync with _DEFAULT_SIZE_CONFIG_JSON in Upscale_By_Max_Side.py.
const MODE_SIZE_KEYS = {
    "Max Side": "size_max",
    "Min Side": "size_min",
    "Total Pixels": "size_total",
};

const MODE_SIZE_DEFAULTS = {
    "Max Side": 1024,
    "Min Side": 1024,
    "Total Pixels": 1000000,
};

function readConfig(widget) {
    try {
        const cfg = JSON.parse(widget.value);
        return {
            size_max: cfg.size_max,
            size_min: cfg.size_min,
            size_total: cfg.size_total,
        };
    } catch (_) {
        return {};
    }
}

function writeConfig(widget, cfg) {
    widget.value = JSON.stringify(cfg);
}

const toPositiveNumber = (v) => {
    const n = typeof v === "number" ? v : parseFloat(v);
    return Number.isFinite(n) && n > 0 ? n : null;
};

app.registerExtension({
    name: "ThatAIGod.UpscaleBySize",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "UpscaleByMaxSide") return;

        const origOnCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = origOnCreated ? origOnCreated.apply(this, arguments) : undefined;
            try { this._hookSizeMemory(); }
            catch (e) { console.warn("ThatAIGod: size memory init error", e); }
            return r;
        };

        // Per-mode Target memory: store the last Target per mode in the Size
        // Config JSON and recall it when Limit By changes.
        nodeType.prototype._hookSizeMemory = function () {
            if (this._sizeMemoryHooked) return;
            this._sizeMemoryHooked = true;

            const configWidget = this.widgets.find(w => w.name === "Size Config");
            const limitWidget = this.widgets.find(w => w.name === "Limit By");
            const targetWidget = this.widgets.find(w => w.name === "Target");
            if (!configWidget || !limitWidget || !targetWidget) return;

            // Hide the config widget — it is pure storage driven by this extension.
            configWidget.computeSize = function (width) { return [width, 0]; };
            if (configWidget.element) configWidget.element.style.display = "none";

            const memKeyFor = (mode) => MODE_SIZE_KEYS[mode] || MODE_SIZE_KEYS["Max Side"];
            const defaultFor = (mode) => MODE_SIZE_DEFAULTS[mode] || MODE_SIZE_DEFAULTS["Max Side"];

            // Seed memory: keep stored values, fill gaps (current mode inherits the live Target).
            const seed = () => {
                const cfg = readConfig(configWidget);
                let touched = false;
                for (const mode of Object.keys(MODE_SIZE_KEYS)) {
                    if (toPositiveNumber(cfg[MODE_SIZE_KEYS[mode]]) === null) {
                        const live = (mode === limitWidget.value) ? toPositiveNumber(targetWidget.value) : null;
                        cfg[MODE_SIZE_KEYS[mode]] = live ?? defaultFor(mode);
                        touched = true;
                    }
                }
                if (touched) writeConfig(configWidget, cfg);
            };
            seed();

            // Push a recalled value into the Target box (value + visible input).
            const recall = (mode) => {
                const cfg = readConfig(configWidget);
                const stored = toPositiveNumber(cfg[memKeyFor(mode)]) ?? defaultFor(mode);
                try {
                    targetWidget.value = Math.round(stored);
                    const el = targetWidget.inputEl || targetWidget.element;
                    if (el && "value" in el && document.activeElement !== el) el.value = targetWidget.value;
                } catch (_) { /* display sync is best-effort */ }
            };

            let lastMode = limitWidget.value;
            const origLimitCb = limitWidget.callback;
            limitWidget.callback = (...args) => {
                try {
                    const nextMode = (typeof args[0] === "string" && MODE_SIZE_KEYS[args[0]])
                        ? args[0]
                        : limitWidget.value;
                    if (nextMode !== lastMode) {
                        // Remember the outgoing mode's value, then recall the incoming one.
                        const outgoing = toPositiveNumber(targetWidget.value);
                        if (outgoing !== null) {
                            const cfg = readConfig(configWidget);
                            cfg[memKeyFor(lastMode)] = outgoing;
                            writeConfig(configWidget, cfg);
                        }
                        recall(nextMode);
                        lastMode = nextMode;
                    }
                } catch (e) { console.warn("ThatAIGod: size memory switch error", e); }
                if (origLimitCb) return origLimitCb.apply(limitWidget, args);
            };

            const origTargetCb = targetWidget.callback;
            targetWidget.callback = (...args) => {
                try {
                    const n = toPositiveNumber(targetWidget.value);
                    if (n !== null) {
                        const cfg = readConfig(configWidget);
                        cfg[memKeyFor(limitWidget.value)] = n;
                        writeConfig(configWidget, cfg);
                    }
                } catch (e) { console.warn("ThatAIGod: size memory save error", e); }
                if (origTargetCb) return origTargetCb.apply(targetWidget, args);
            };
        };
    },
});
