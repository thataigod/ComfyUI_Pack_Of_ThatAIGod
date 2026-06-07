/**
 * @fileoverview Frontend extension for DynamicResolutionSelector node.
 */
import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const ALL_LABELS = [
    "Square 1:1",
    "Portrait 2:3 (Classic)",
    "Portrait 3:4 (Standard)",
    "Portrait 4:5 (Social)",
    "Portrait 9:16 (Mobile)",
    "Landscape 3:2 (Classic)",
    "Landscape 4:3 (Standard)",
    "Landscape 5:4 (Display)",
    "Landscape 16:9 (HD)",
    "Landscape 16:10 (Monitor)",
    "Landscape 21:9 (Ultrawide)",
    "Landscape 1.85:1 (Cinema)",
];

const DISPLAY = {
    "Square 1:1": "Square 1:1",
    "Portrait 2:3 (Classic)": "Classic 2:3",
    "Portrait 3:4 (Standard)": "Standard 3:4",
    "Portrait 4:5 (Social)": "Social 4:5",
    "Portrait 9:16 (Mobile)": "Mobile 9:16",
    "Landscape 3:2 (Classic)": "Classic 3:2",
    "Landscape 4:3 (Standard)": "Standard 4:3",
    "Landscape 5:4 (Display)": "Display 5:4",
    "Landscape 16:9 (HD)": "HD 16:9",
    "Landscape 16:10 (Monitor)": "Monitor 16:10",
    "Landscape 21:9 (Ultrawide)": "Ultrawide 21:9",
    "Landscape 1.85:1 (Cinema)": "Cinema 1.85:1",
};

const LANDSCAPE_LABELS = ALL_LABELS.slice(5);
const PORTRAIT_LABELS = ALL_LABELS.slice(1, 5);

function readConfig(widget) {
    try { return JSON.parse(widget.value); }
    catch (_) { return { ratios: [...PORTRAIT_LABELS], custom_ratio: 1.0, custom_enabled: false }; }
}

function writeConfig(widget, cfg) {
    widget.value = JSON.stringify(cfg);
}

app.registerExtension({
    name: "ThatAIGod.DynamicResolutionSelector",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "DynamicResolutionSelector") return;

        const origOnCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            try {
                const r = origOnCreated ? origOnCreated.apply(this, arguments) : undefined;

                if (!this._rsWidgetAdded) {
                    this._rsWidgetAdded = true;
                    try {
                        const w = ComfyWidgets["STRING"](
                            this, "Resolution Info",
                            ["STRING", { multiline: true }], app,
                        ).widget;
                        w.inputEl.readOnly = true;
                        w.inputEl.style.overflowY = "auto";
                    } catch (e) {
                        console.warn("ThatAIGod: Info widget create error", e);
                    }
                }

                // Hook resize to enforce min height and scale Resolution Info
                const origOnResize = this.onResize;
                this.onResize = function (size) {
                    if (this._rsMinHeight && size[1] < this._rsMinHeight) {
                        size[1] = this._rsMinHeight;
                        this.size[1] = this._rsMinHeight;
                    }
                    origOnResize?.apply(this, arguments);
                    this._adjustInfoHeight(size);
                };

                // Override computeSize to ensure LiteGraph auto-layout doesn't shrink the node below the custom UI
                const origComputeSize = this.computeSize;
                this.computeSize = function(out) {
                    let res = origComputeSize ? origComputeSize.apply(this, arguments) : [out ? out[0] : 280, 430];
                    if (this._rsMinHeight && res[1] < this._rsMinHeight) {
                        res[1] = this._rsMinHeight;
                    }
                    return res;
                };

                this.size[0] = Math.max(this.size[0], 280);
                this.size[1] = Math.max(this.size[1], 430);

                setTimeout(() => {
                    try { this._buildRatioUI(); }
                    catch (e) { console.warn("ThatAIGod: Ratio UI build error", e); }
                }, 0);

                return r;
            } catch (e) {
                console.error("ThatAIGod: DynamicResolutionSelector onNodeCreated error", e);
                try { return origOnCreated ? origOnCreated.apply(this, arguments) : undefined; }
                catch (_) { return undefined; }
            }
        };

        nodeType.prototype._adjustInfoHeight = function (size) {
            // Keep as no-op to prevent any feedback loops
        };

        nodeType.prototype._buildRatioUI = function () {
            const configWidget = this.widgets.find(w => w.name === "Aspect Ratio Config");
            if (!configWidget) return;

            configWidget.computeSize = function (width) {
                return [width, 0];
            };

            const infoWidget = this.widgets.find(w => w.name === "Resolution Info");
            const parentEl = infoWidget && infoWidget.element ? infoWidget.element.parentNode : configWidget.element && configWidget.element.parentNode ? configWidget.element.parentNode : null;
            const existing = parentEl?.querySelector(".rs-ui");
            if (existing) existing.remove();

            const cfg = readConfig(configWidget);
            let selected = new Set(cfg.ratios);
            let customEnabled = !!cfg.custom_enabled;
            let customRatio = cfg.custom_ratio || 1.0;

            const container = document.createElement("div");
            container.className = "rs-ui";
            container.style.cssText = "padding:6px 8px;margin:4px 0;border:1px solid #444;border-radius:4px;";

            // Expose elements for dynamic computeSize
            this._rsContainer = container;
            this._rsConfigWidget = configWidget;
            this._rsInfoWidget = infoWidget;

            const persist = () => {
                writeConfig(configWidget, {
                    ratios: ALL_LABELS.filter(l => selected.has(l)),
                    custom_ratio: customRatio,
                    custom_enabled: customEnabled,
                });
            };

            const updateMinHeight = () => {
                // Hardcode standard UI calculation since dynamic DOM measuring was blocked
                let h = 30; // Header
                if (typeof LiteGraph !== "undefined" && LiteGraph.NODE_TITLE_HEIGHT) {
                    h = LiteGraph.NODE_TITLE_HEIGHT;
                }
                
                for (let w of this.widgets) {
                    if (w === configWidget) continue;
                    if (w === infoWidget) break;
                    h += 24; 
                }

                // Calculate dynamically if visible, else use generous fallback
                let cH = container.offsetHeight > 0 ? container.offsetHeight : 300;
                let iH = 100;
                if (infoWidget && infoWidget.element && infoWidget.element.offsetHeight > 0) {
                    iH = infoWidget.element.offsetHeight;
                }
                
                // Add generous 60px padding to cover CSS margins, gaps, and borders
                h += cH + iH + 60;

                this._rsMinHeight = h;
                
                // Bypass setSize/computeSize and enforce directly
                if (this.size[1] < h) {
                    this.size[1] = h;
                    if (this.onResize) this.onResize(this.size);
                    if (app.graph) app.graph.setDirtyCanvas(true, true);
                }
            };

            const render = () => {
                container.innerHTML = "";

                const selAll = selected.size === ALL_LABELS.length;

                const makeBtn = (text, onClick) => {
                    const b = document.createElement("button");
                    b.textContent = text;
                    b.style.cssText = "flex:1;padding:3px 6px;border:1px solid #444;border-radius:4px;cursor:pointer;font-size:11px;background:#2a2a2a;color:#ccc;";
                    b.onclick = onClick;
                    return b;
                };

                const btnAll = makeBtn(selAll ? "Deselect All" : "Select All", () => {
                    if (selAll) {
                        selected = new Set();
                        customEnabled = false;
                    } else {
                        selected = new Set(ALL_LABELS);
                        customEnabled = true;
                    }
                    persist();
                    render();
                });
                const btnPort = makeBtn(
                    PORTRAIT_LABELS.every(l => selected.has(l)) ? "Unportraits" : "Portraits",
                    () => {
                        PORTRAIT_LABELS.every(l => selected.has(l))
                            ? PORTRAIT_LABELS.forEach(l => selected.delete(l))
                            : PORTRAIT_LABELS.forEach(l => selected.add(l));
                        persist();
                        render();
                    },
                );
                const btnLand = makeBtn(
                    LANDSCAPE_LABELS.every(l => selected.has(l)) ? "Unlandscapes" : "Landscapes",
                    () => {
                        LANDSCAPE_LABELS.every(l => selected.has(l))
                            ? LANDSCAPE_LABELS.forEach(l => selected.delete(l))
                            : LANDSCAPE_LABELS.forEach(l => selected.add(l));
                        persist();
                        render();
                    },
                );

                const batchRow = document.createElement("div");
                batchRow.style.cssText = "display:flex;gap:4px;margin-bottom:6px;";
                batchRow.appendChild(btnAll);
                batchRow.appendChild(btnPort);
                batchRow.appendChild(btnLand);
                container.appendChild(batchRow);

                const createToggle = (label, parent) => {
                    const row = document.createElement("div");
                    row.style.cssText = "display:flex;align-items:center;gap:5px;padding:2px 4px;font-size:12px;user-select:none;cursor:default;";
                    const dot = document.createElement("span");
                    dot.textContent = selected.has(label) ? "\u25C9" : "\u25CB";
                    dot.style.cssText = "color:" + (selected.has(label) ? "#77ee77" : "#666") + ";flex-shrink:0;font-size:13px;cursor:pointer;";
                    const txt = document.createElement("span");
                    txt.textContent = DISPLAY[label];
                    txt.style.color = "#ccc";
                    row.appendChild(dot);
                    row.appendChild(txt);
                    row.onclick = () => {
                        selected.has(label) ? selected.delete(label) : selected.add(label);
                        persist();
                        render();
                    };
                    parent.appendChild(row);
                };

                const columns = document.createElement("div");
                columns.className = "rs-columns";
                columns.style.cssText = "display:flex;gap:10px;";

                const leftCol = document.createElement("div");
                leftCol.className = "rs-col-left";
                leftCol.style.cssText = "flex:1;min-width:0;";
                LANDSCAPE_LABELS.forEach(l => createToggle(l, leftCol));

                const rightCol = document.createElement("div");
                rightCol.className = "rs-col-right";
                rightCol.style.cssText = "flex:1;min-width:0;";
                createToggle("Square 1:1", rightCol);
                PORTRAIT_LABELS.forEach(l => createToggle(l, rightCol));

                const cr = document.createElement("div");
                cr.style.cssText = "display:flex;align-items:center;gap:5px;margin-top:4px;padding:2px 4px;";
                const ct = document.createElement("span");
                ct.textContent = customEnabled ? "\u25C9" : "\u25CB";
                ct.style.cssText = "cursor:pointer;font-size:13px;color:" + (customEnabled ? "#77ee77" : "#666") + ";flex-shrink:0;";
                ct.onclick = () => { customEnabled = !customEnabled; persist(); render(); };
                const cl = document.createElement("span");
                cl.textContent = "Custom W:H";
                cl.style.cssText = "color:#ccc;font-size:12px;flex-shrink:0;";
                const ci = document.createElement("input");
                ci.type = "text"; ci.value = String(customRatio);
                ci.style.cssText = "width:36px;padding:1px 4px;border:1px solid #444;border-radius:3px;background:#2a2a2a;color:#ccc;font-size:11px;";
                ci.onchange = () => { 
                    let val = ci.value.trim();
                    let match = val.match(/^(\d+(?:\.\d+)?)\s*[:\/]\s*(\d+(?:\.\d+)?)$/);
                    if (match) {
                        let w = parseFloat(match[1]);
                        let h = parseFloat(match[2]);
                        if (h > 0) val = (w / h).toFixed(3);
                    }
                    let v = parseFloat(val); 
                    if (!isNaN(v) && v > 0) { 
                        customRatio = v; 
                        ci.value = v; 
                        persist(); 
                    } else {
                        ci.value = customRatio;
                    }
                };
                cr.appendChild(ct); cr.appendChild(cl); cr.appendChild(ci);
                rightCol.appendChild(cr);

                columns.appendChild(leftCol);
                columns.appendChild(rightCol);
                container.appendChild(columns);

                requestAnimationFrame(updateMinHeight);
            };

            render();

            if (configWidget.element) {
                configWidget.element.style.display = "none";
            }

            const anchor = infoWidget && infoWidget.element ? infoWidget.element : configWidget.element && configWidget.element.parentNode ? configWidget.element.nextSibling : null;
            if (anchor && anchor.parentNode) {
                anchor.parentNode.insertBefore(container, anchor);
            }

            if (infoWidget) {
                infoWidget.computeSize = function (w) { return [w, 100]; };
                if (infoWidget.inputEl) {
                    infoWidget.inputEl.style.height = "90px";
                    infoWidget.inputEl.style.minHeight = "90px";
                    infoWidget.inputEl.style.maxHeight = "90px";
                }
            }

            requestAnimationFrame(() => {
                const colLeft = container.querySelector(".rs-col-left");
                const colRight = container.querySelector(".rs-col-right");
                if (colLeft && colRight) {
                    const oldLeftStyle = colLeft.style.cssText;
                    const oldRightStyle = colRight.style.cssText;
                    colLeft.style.cssText = "display:inline-block;width:max-content;";
                    colRight.style.cssText = "display:inline-block;width:max-content;";
                    void colLeft.offsetHeight;
                    const lw = colLeft.offsetWidth || colLeft.scrollWidth;
                    const rw = colRight.offsetWidth || colRight.scrollWidth;
                    colLeft.style.cssText = oldLeftStyle;
                    colRight.style.cssText = oldRightStyle;

                    this.size[0] = Math.max(this.size[0], Math.max(lw, rw) * 2 + 38);
                }

                updateMinHeight();
                // Continuously check for dynamic widgets (like 'seed') and container height changes
                setInterval(updateMinHeight, 500);
                this.onResize?.(this.size);
            });
        };

        const origExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            origExecuted?.apply(this, arguments);
            if (!message) return;
            const updateOutput = (i, val, name) => {
                if (this.outputs && this.outputs[i]) {
                    this.outputs[i].name = val + " " + name;
                    this.outputs[i].label = " ";
                }
            };
            if (message.width) updateOutput(0, message.width[0], "Width");
            if (message.height) updateOutput(1, message.height[0], "Height");
            if (message.scaled_width) updateOutput(2, message.scaled_width[0], "Scaled Width");
            if (message.scaled_height) updateOutput(3, message.scaled_height[0], "Scaled Height");
            if (message.scale_factor) updateOutput(4, message.scale_factor[0], "Scale Factor");
            if (message.guide_size) updateOutput(6, message.guide_size[0], "Guide Size");
            if (message.max_size) updateOutput(7, message.max_size[0], "Max Size");
            const w = this.widgets && this.widgets.find(w => w.name === "Resolution Info");
            if (w && message.text && message.text[0]) w.value = message.text[0];
        };

        const origDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function (ctx) {
            origDrawForeground?.apply(this, arguments);
            if (!this.outputs) return;
            ctx.save();
            ctx.font = "12px Arial";
            ctx.fillStyle = "#77ee77";
            ctx.textAlign = "right";
            ctx.textBaseline = "middle";
            for (let i = 0; i < this.outputs.length; i++) {
                const output = this.outputs[i];
                if (output.name && output.label === " ") {
                    const pos = this.getConnectionPos(false, i);
                    ctx.fillText(output.name, this.size[0] - 20, pos[1] - this.pos[1]);
                }
            }
            ctx.restore();
        };
    },
});
