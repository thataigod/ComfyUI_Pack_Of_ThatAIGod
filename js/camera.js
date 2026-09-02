/**
 * @fileoverview Frontend extension for the Camera node.
 */
import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// Built-in axes, used only when the backend options endpoint is unreachable.
// The live option space (including wildcard-file customizations) is fetched
// from /that_aigod/camera_options.
const AXES = [
    {
        key: "sizes",
        label: "Shot Size",
        options: [
            "Extreme Close-Up",
            "Close-Up",
            "Medium Close-Up",
            "Medium",
            "Cowboy",
            "Medium Full",
            "Full",
            "Long",
            "Extreme Long",
        ],
        shortcuts: [
            {
                text: "Close-ups",
                members: ["Extreme Close-Up", "Close-Up", "Medium Close-Up"],
            },
            {
                text: "Mid-Sizes",
                members: ["Medium", "Cowboy", "Medium Full"],
            },
            {
                text: "Fulls",
                members: ["Full", "Long", "Extreme Long"],
            },
        ],
    },
    {
        key: "angles",
        label: "Camera Angle",
        options: ["Eye Level", "Low Angle", "High Angle", "Top Down", "Worm's Eye"],
        shortcuts: [
            {
                text: "Below",
                members: ["Low Angle", "Worm's Eye"],
            },
            {
                text: "Above",
                members: ["High Angle", "Top Down"],
            },
        ],
    },
    {
        key: "views",
        label: "View",
        options: ["Front", "3/4 Front", "Profile", "3/4 Back", "Back"],
        shortcuts: [
            {
                text: "Facing",
                members: ["Front", "3/4 Front"],
            },
            {
                text: "Away",
                members: ["Back", "3/4 Back"],
            },
        ],
    },
    {
        key: "movements",
        label: "Movement",
        options: ["Static", "Pan", "Tilt", "Tracking", "Handheld"],
        shortcuts: [
            {
                text: "Static",
                members: ["Static"],
            },
            {
                text: "Motion",
                members: ["Pan", "Tilt", "Tracking", "Handheld"],
            },
        ],
    },
    {
        key: "tilts",
        label: "Tilt",
        options: ["None", "Slight", "Strong"],
        shortcuts: [
            {
                text: "Level",
                members: ["None"],
            },
            {
                text: "Dutch",
                members: ["Slight", "Strong"],
            },
        ],
    },
    {
        key: "looks",
        label: "Look",
        options: [
            "Hasselblad 500C/M",
            "Rolleiflex 2.8F",
            "Pentax 67",
            "Deardorff 8x10",
            "Leica M6",
            "Nikon F3",
            "Olympus OM-1",
            "Canon AE-1 Program",
            "Contax T2",
            "Polaroid SX-70",
            "Fujifilm X100V",
            "Leica M11",
            "Sony A7R V",
            "Canon EOS R5",
            "Hasselblad X2D 100C",
            "ARRI Alexa 35",
            "RED Komodo 6K",
            "Sony Venice 2",
            "Bolex H16 Rex-5",
            "Smartphone",
        ],
        shortcuts: [
            {
                text: "Film",
                members: [
                    "Hasselblad 500C/M",
                    "Rolleiflex 2.8F",
                    "Pentax 67",
                    "Deardorff 8x10",
                    "Leica M6",
                    "Nikon F3",
                    "Olympus OM-1",
                    "Canon AE-1 Program",
                    "Contax T2",
                    "Polaroid SX-70",
                    "Bolex H16 Rex-5",
                ],
            },
            {
                text: "Digital",
                members: [
                    "Fujifilm X100V",
                    "Sony A7R V",
                    "Leica M11",
                    "Canon EOS R5",
                    "Hasselblad X2D 100C",
                    "ARRI Alexa 35",
                    "RED Komodo 6K",
                    "Sony Venice 2",
                    "Smartphone",
                ],
            },
        ],
    },
];

const AXIS_LABELS = {
    sizes: "Shot Size",
    angles: "Camera Angle",
    views: "View",
    movements: "Movement",
    tilts: "Tilt",
    looks: "Look",
};

let _cameraAxesPromise = null;

function buildAxes(data) {
    return Object.keys(AXIS_LABELS).map((key) => ({
        key,
        label: AXIS_LABELS[key],
        options: Array.isArray(data[key]?.options) ? data[key].options : [],
        shortcuts: Array.isArray(data[key]?.shortcuts)
            ? data[key].shortcuts.map((s) => ({
                text: s.text,
                members: Array.isArray(s.members) ? s.members : [],
            }))
            : [],
    }));
}

function fetchCameraAxes(force = false) {
    if (force) _cameraAxesPromise = null;
    if (!_cameraAxesPromise) {
        _cameraAxesPromise = fetch("/that_aigod/camera_options", { cache: "no-store" })
            .then((r) => {
                if (!r.ok) throw new Error("status " + r.status);
                return r.json();
            })
            .then((data) => buildAxes(data))
            .catch((err) => {
                console.warn("ThatAIGod: camera options fetch failed; using built-in axes.", err);
                return AXES;
            });
    }
    return _cameraAxesPromise;
}
fetchCameraAxes.invalidate = () => { _cameraAxesPromise = null; };

function readConfig(widget, axes) {
    try {
        const cfg = JSON.parse(widget.value);
        if (!cfg || typeof cfg !== "object" || Array.isArray(cfg)) throw new Error("not an object");
        const out = {};
        for (const axis of axes) {
            const picked = cfg[axis.key];
            if (Array.isArray(picked)) {
                const filtered = picked.filter((v) => axis.options.includes(v));
                if (filtered.length !== picked.length) {
                    const dropped = picked.filter((v) => !axis.options.includes(v));
                    console.warn(`ThatAIGod: Camera Config dropped unknown options for ${axis.key}:`, dropped);
                }
                if (picked.length > 0 && filtered.length === 0) {
                    console.warn(`ThatAIGod: Camera Config for ${axis.key} became empty after filtering — check for typos.`);
                }
                out[axis.key] = filtered;
            } else if (picked === undefined) {
                out[axis.key] = [...axis.options];
            } else {
                console.warn(`ThatAIGod: Camera Config ${axis.key} expected array, got`, typeof picked);
                out[axis.key] = [...axis.options];
            }
        }
        return out;
    } catch (e) {
        console.warn("ThatAIGod: Camera Config JSON parse failed, using all options.", e);
        const out = {};
        for (const axis of axes) out[axis.key] = [...axis.options];
        return out;
    }
}

function writeConfig(widget, cfg) {
    widget.value = JSON.stringify(cfg);
    // Notify ComfyUI that the widget value changed (marks graph dirty).
    try { widget.callback?.(widget.value); } catch (_) {}
    try { app.graph?.setDirtyCanvas?.(true, false); } catch (_) {}
}

app.registerExtension({
    name: "ThatAIGod.Camera",

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "Camera") return;
        const _app = appInstance || app;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            try {
                const r = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;

                if (!this._camWidgetAdded) {
                    this._camWidgetAdded = true;
                    try {
                        const w = ComfyWidgets["STRING"](
                            this, "Camera Info",
                            ["STRING", { multiline: true }], app,
                        ).widget;
                        w.inputEl.readOnly = true;
                        w.inputEl.style.overflowY = "auto";
                    } catch (e) {
                        console.warn("ThatAIGod: Camera Info widget create error", e);
                    }
                }

                const origOnResize = this.onResize;
                this.onResize = function (size) {
                    if (this._camMinHeight && size[1] < this._camMinHeight) {
                        size[1] = this._camMinHeight;
                        this.size[1] = this._camMinHeight;
                    }
                    origOnResize?.apply(this, arguments);
                };

                const origComputeSize = this.computeSize;
                this.computeSize = function (out) {
                    let res = origComputeSize ? origComputeSize.apply(this, arguments) : [out ? out[0] : 320, 560];
                    if (this._camMinHeight && res[1] < this._camMinHeight) {
                        res[1] = this._camMinHeight;
                    }
                    return res;
                };

                this.size[0] = Math.max(this.size[0], 320);
                this.size[1] = Math.max(this.size[1], 560);

                setTimeout(() => {
                    try { this._buildCameraUI(); }
                    catch (e) { console.warn("ThatAIGod: Camera UI build error", e); }
                }, 0);

                return r;
            } catch (e) {
                console.error("ThatAIGod: Camera onNodeCreated error", e);
                try { return origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined; }
                catch (_) { return undefined; }
            }
        };

        nodeType.prototype._buildCameraUI = async function () {
            const axes = await fetchCameraAxes();
            const configWidget = this.widgets.find((w) => w.name === "Camera Config");
            if (!configWidget) return;

            configWidget.computeSize = function (width) {
                return [width, 0];
            };

            const infoWidget = this.widgets.find((w) => w.name === "Camera Info");
            const parentEl = infoWidget && infoWidget.element
                ? infoWidget.element.parentNode
                : configWidget.element && configWidget.element.parentNode
                    ? configWidget.element.parentNode
                    : null;
            const existing = parentEl?.querySelector(".cam-ui");
            if (existing) existing.remove();

            const cfg = readConfig(configWidget, axes);
            const selected = {};
            for (const axis of axes) selected[axis.key] = new Set(cfg[axis.key]);

            const container = document.createElement("div");
            container.className = "cam-ui";
            container.style.cssText = "padding:6px 8px;margin:4px 0;border:1px solid #444;border-radius:4px;";

            const persist = () => {
                const out = {};
                for (const axis of axes) out[axis.key] = axis.options.filter((o) => selected[axis.key].has(o));
                writeConfig(configWidget, out);
            };

            const updateMinHeight = () => {
                let h = 30;
                if (typeof LiteGraph !== "undefined" && LiteGraph.NODE_TITLE_HEIGHT) {
                    h = LiteGraph.NODE_TITLE_HEIGHT;
                }
                for (const w of this.widgets) {
                    if (w === configWidget) continue;
                    if (w === infoWidget) break;
                    h += 24;
                }
                const cH = container.offsetHeight > 0 ? container.offsetHeight : 480;
                const iH = infoWidget && infoWidget.element && infoWidget.element.offsetHeight > 0
                    ? infoWidget.element.offsetHeight
                    : 110;
                this._camMinHeight = h + cH + iH + 60;
                if (this.size[1] < this._camMinHeight) {
                    this.size[1] = this._camMinHeight;
                    if (app.graph) app.graph.setDirtyCanvas(true, true);
                }
            };

            const render = () => {
                container.innerHTML = "";

                for (const axis of axes) {
                    const group = document.createElement("div");
                    group.style.cssText = "margin-bottom:8px;";

                    const header = document.createElement("div");
                    header.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-bottom:2px;";

                    const title = document.createElement("span");
                    title.textContent = axis.label;
                    title.style.cssText = "color:#eee;font-size:12px;font-weight:bold;";

                    const allSelected = selected[axis.key].size === axis.options.length;
                    const noneSelected = selected[axis.key].size === 0;
                    const btnAll = document.createElement("button");
                    btnAll.textContent = allSelected ? "All" : (noneSelected ? "None" : "Partial");
                    btnAll.style.cssText = "padding:1px 8px;border:1px solid " +
                        (allSelected ? "#77ee77" : (noneSelected ? "#ff5555" : "#cc8844")) +
                        ";border-radius:4px;cursor:pointer;font-size:10px;background:#2a2a2a;color:#ccc;";
                    btnAll.title = "Toggle all options on/off";
                    btnAll.onclick = () => {
                        if (allSelected) {
                            selected[axis.key] = new Set();
                        } else {
                            selected[axis.key] = new Set(axis.options);
                        }
                        persist();
                        render();
                    };

                    const btnRow = document.createElement("div");
                    btnRow.style.cssText = "display:flex;gap:4px;";
                    btnRow.appendChild(btnAll);
                    for (const sc of axis.shortcuts) {
                        const btn = document.createElement("button");
                        btn.textContent = sc.text;
                        const scAll = sc.members.every((m) => selected[axis.key].has(m));
                        const scAny = sc.members.some((m) => selected[axis.key].has(m));
                        const scState = scAll ? "#77ee77" : (scAny ? "#cc8844" : "#444");
                        btn.style.cssText = "padding:1px 8px;border:1px solid " + scState +
                            ";border-radius:4px;cursor:pointer;font-size:10px;background:#2a2a2a;color:" +
                            (scAll ? "#aaffaa" : "#ccc") + ";";
                        btn.title = scAll ? "All members active — click to clear" : "Click to toggle members";
                        btn.onclick = () => {
                            const members = new Set(sc.members);
                            const allActive = sc.members.every((m) => selected[axis.key].has(m));
                            for (const m of sc.members) {
                                if (allActive) {
                                    selected[axis.key].delete(m);
                                } else {
                                    selected[axis.key].add(m);
                                }
                            }
                            persist();
                            render();
                        };
                        btnRow.appendChild(btn);
                    }

                    header.appendChild(title);
                    header.appendChild(btnRow);
                    group.appendChild(header);

                    const chips = document.createElement("div");
                    chips.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;";
                    for (const opt of axis.options) {
                        const chip = document.createElement("span");
                        const active = selected[axis.key].has(opt);
                        chip.textContent = opt;
                        chip.style.cssText =
                            "padding:2px 8px;border:1px solid " + (active ? "#77ee77" : "#444") +
                            ";border-radius:10px;cursor:pointer;font-size:11px;background:" + (active ? "#1d331d" : "#1c1c1c") +
                            ";color:" + (active ? "#aaffaa" : "#888") + ";user-select:none;";
                        chip.onclick = () => {
                            active ? selected[axis.key].delete(opt) : selected[axis.key].add(opt);
                            persist();
                            render();
                        };
                        chips.appendChild(chip);
                    }
                    group.appendChild(chips);
                    container.appendChild(group);
                }

                requestAnimationFrame(updateMinHeight);
            };

            render();

            if (configWidget.element) {
                configWidget.element.style.display = "none";
            }

            const anchor = infoWidget && infoWidget.element
                ? infoWidget.element
                : configWidget.element && configWidget.element.parentNode
                    ? configWidget.element.nextSibling
                    : null;
            if (anchor && anchor.parentNode) {
                anchor.parentNode.insertBefore(container, anchor);
            }

            if (infoWidget) {
                infoWidget.computeSize = function () { return [0, 110]; };
                if (infoWidget.inputEl) {
                    infoWidget.inputEl.style.height = "100px";
                    infoWidget.inputEl.style.minHeight = "100px";
                    infoWidget.inputEl.style.maxHeight = "100px";
                }
            }
        };

        const origExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            origExecuted?.apply(this, arguments);
            if (!message) return;
            const w = this.widgets && this.widgets.find((w) => w.name === "Camera Info");
            if (w && message.description && message.description[0]) w.value = message.description[0];
        };
    },
});
