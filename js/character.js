/**
 * @fileoverview Frontend extension for the Character node.
 */
import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

// Fallback spaces used only when the backend options endpoint is unreachable.
const FALLBACK = {
    occasions: ["casual", "office", "formal", "wedding", "party", "festival", "costume", "athletic", "gym", "beach", "pool", "resort", "travel", "home", "intimate", "boudoir", "traditional"],
    states: ["dressed", "revealing", "mishap", "slipping", "nude"],
    occasion_groups: [
        { text: "Everyday", members: ["casual", "travel", "home"] },
        { text: "Work", members: ["office", "formal"] },
        { text: "Social", members: ["party", "wedding", "festival"] },
        { text: "Active", members: ["athletic", "gym", "beach", "pool", "resort"] },
        { text: "Private", members: ["intimate", "boudoir"] },
        { text: "Cultural", members: ["traditional", "costume"] },
    ],
};

let _characterOptionsPromise = null;

function fetchCharacterOptions() {
    if (!_characterOptionsPromise) {
        _characterOptionsPromise = fetch("/that_aigod/character_options")
            .then((r) => {
                if (!r.ok) throw new Error("status " + r.status);
                return r.json();
            })
            .then((data) => ({
                occasions: Array.isArray(data.occasions) && data.occasions.length ? data.occasions : FALLBACK.occasions,
                states: Array.isArray(data.states) && data.states.length ? data.states : FALLBACK.states,
                occasion_groups: Array.isArray(data.occasion_groups) ? data.occasion_groups : FALLBACK.occasion_groups,
            }))
            .catch((err) => {
                console.warn("ThatAIGod: character options fetch failed; using built-in axes.", err);
                return FALLBACK;
            });
    }
    return _characterOptionsPromise;
}

function readConfig(widget, occasions, states) {
    try {
        const cfg = JSON.parse(widget.value);
        const out = {};
        for (const [key, options] of [["occasions", occasions], ["states", states]]) {
            const picked = (cfg && typeof cfg === "object" && !Array.isArray(cfg)) ? cfg[key] : undefined;
            out[key] = Array.isArray(picked) ? picked.filter((v) => options.includes(v)) : [...options];
        }
        return out;
    } catch (_) {
        return { occasions: [...occasions], states: [...states] };
    }
}

function writeConfig(widget, cfg) {
    widget.value = JSON.stringify(cfg);
}

function stateButton(label, state, onClick) {
    const btn = document.createElement("button");
    btn.textContent = label;
    btn.style.cssText = "padding:1px 8px;border:1px solid " + state +
        ";border-radius:4px;cursor:pointer;font-size:10px;background:#2a2a2a;color:#ccc;";
    btn.onclick = onClick;
    return btn;
}

app.registerExtension({
    name: "ThatAIGod.Character",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "Character") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            try {
                const r = origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined;

                if (!this._charWidgetAdded) {
                    this._charWidgetAdded = true;
                    try {
                        const w = ComfyWidgets["STRING"](
                            this, "Character Info",
                            ["STRING", { multiline: true }], app,
                        ).widget;
                        w.inputEl.readOnly = true;
                        w.inputEl.style.overflowY = "auto";
                        w.inputEl.style.height = "84px";
                        w.inputEl.style.minHeight = "84px";
                        w.inputEl.style.maxHeight = "84px";
                        w.computeSize = function () { return [0, 96]; };
                    } catch (e) {
                        console.warn("ThatAIGod: Character Info widget create error", e);
                    }
                }

                this.size[0] = Math.max(this.size[0], 340);
                this.size[1] = Math.max(this.size[1], 560);

                const origOnResize = this.onResize;
                this.onResize = function (size) {
                    if (this._charMinHeight && size[1] < this._charMinHeight) {
                        size[1] = this._charMinHeight;
                        this.size[1] = this._charMinHeight;
                    }
                    origOnResize?.apply(this, arguments);
                };

                const origComputeSize = this.computeSize;
                this.computeSize = function (out) {
                    let res = origComputeSize ? origComputeSize.apply(this, arguments) : [out ? out[0] : 320, 640];
                    if (this._charMinHeight && res[1] < this._charMinHeight) {
                        res[1] = this._charMinHeight;
                    }
                    return res;
                };

                setTimeout(() => {
                    try { this._buildCharacterUI(); }
                    catch (e) { console.warn("ThatAIGod: Character UI build error", e); }
                }, 0);

                return r;
            } catch (e) {
                console.error("ThatAIGod: Character onNodeCreated error", e);
                try { return origOnNodeCreated ? origOnNodeCreated.apply(this, arguments) : undefined; }
                catch (_) { return undefined; }
            }
        };

        nodeType.prototype._buildCharacterUI = async function () {
            const options = await fetchCharacterOptions();
            const configWidget = this.widgets.find((w) => w.name === "Character Config");
            if (!configWidget) return;

            configWidget.computeSize = function (width) {
                return [width, 0];
            };

            const infoWidget = this.widgets.find((w) => w.name === "Character Info");
            const parentEl = infoWidget && infoWidget.element
                ? infoWidget.element.parentNode
                : configWidget.element && configWidget.element.parentNode
                    ? configWidget.element.parentNode
                    : null;
            const existing = parentEl?.querySelector(".char-ui");
            if (existing) existing.remove();

            const cfg = readConfig(configWidget, options.occasions, options.states);
            const selected = {
                occasions: new Set(cfg.occasions),
                states: new Set(cfg.states),
            };

            const container = document.createElement("div");
            container.className = "char-ui";
            container.style.cssText = "padding:6px 8px;margin:4px 0;border:1px solid #444;border-radius:4px;";

            const persist = () => {
                writeConfig(configWidget, {
                    occasions: options.occasions.filter((o) => selected.occasions.has(o)),
                    states: options.states.filter((s) => selected.states.has(s)),
                });
            };

            const render = () => {
                container.innerHTML = "";

                const groups = [
                    {
                        key: "occasions",
                        label: "Occasions",
                        options: options.occasions,
                        shortcuts: options.occasion_groups,
                        selected: selected.occasions,
                    },
                    {
                        key: "states",
                        label: "State",
                        options: options.states,
                        shortcuts: [],
                        selected: selected.states,
                    },
                ];

                for (const axis of groups) {
                    const group = document.createElement("div");
                    group.style.cssText = "margin-bottom:8px;";

                    const header = document.createElement("div");
                    header.style.cssText = "display:flex;align-items:center;justify-content:space-between;margin-bottom:2px;";

                    const title = document.createElement("span");
                    title.textContent = axis.label;
                    title.style.cssText = "color:#eee;font-size:12px;font-weight:bold;";

                    const allSelected = axis.selected.size === axis.options.length;
                    const noneSelected = axis.selected.size === 0;
                    const btnAll = stateButton(
                        allSelected ? "All" : (noneSelected ? "None" : "Partial"),
                        allSelected ? "#77ee77" : (noneSelected ? "#ff5555" : "#cc8844"),
                        () => {
                            if (allSelected) {
                                axis.selected.clear();
                            } else {
                                axis.selected = new Set(axis.options);
                                if (axis.key === "occasions") selected.occasions = axis.selected;
                                else selected.states = axis.selected;
                            }
                            persist();
                            render();
                        },
                    );
                    btnAll.title = "Toggle all options on/off";

                    const btnRow = document.createElement("div");
                    btnRow.style.cssText = "display:flex;flex-wrap:wrap;gap:4px;";
                    btnRow.appendChild(btnAll);
                    for (const sc of axis.shortcuts) {
                        const btn = document.createElement("button");
                        btn.textContent = sc.text;
                        const scAll = sc.members.every((m) => axis.selected.has(m));
                        const scAny = sc.members.some((m) => axis.selected.has(m));
                        const scState = scAll ? "#77ee77" : (scAny ? "#cc8844" : "#444");
                        btn.style.cssText = "padding:1px 8px;border:1px solid " + scState +
                            ";border-radius:4px;cursor:pointer;font-size:10px;background:#2a2a2a;color:" +
                            (scAll ? "#aaffaa" : "#ccc") + ";";
                        btn.onclick = () => {
                            const members = new Set(sc.members);
                            const allActive = sc.members.every((m) => axis.selected.has(m));
                            for (const m of sc.members) {
                                if (allActive) {
                                    axis.selected.delete(m);
                                } else {
                                    axis.selected.add(m);
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
                        const active = axis.selected.has(opt);
                        chip.textContent = opt;
                        chip.style.cssText =
                            "padding:2px 8px;border:1px solid " + (active ? "#77ee77" : "#444") +
                            ";border-radius:10px;cursor:pointer;font-size:11px;background:" + (active ? "#1d331d" : "#1c1c1c") +
                            ";color:" + (active ? "#aaffaa" : "#888") + ";user-select:none;";
                        chip.onclick = () => {
                            active ? axis.selected.delete(opt) : axis.selected.add(opt);
                            persist();
                            render();
                        };
                        chips.appendChild(chip);
                    }
                    group.appendChild(chips);
                    container.appendChild(group);
                }

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
                requestAnimationFrame(updateMinHeight);
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
                const cH = container.offsetHeight > 0 ? container.offsetHeight : 420;
                this._charMinHeight = h + cH + 96 + 60;
                if (this.size[1] < this._charMinHeight) {
                    this.size[1] = this._charMinHeight;
                    if (app.graph) app.graph.setDirtyCanvas(true, true);
                }
            };

            render();
        };

        const origExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            origExecuted?.apply(this, arguments);
            if (!message) return;
            const w = this.widgets && this.widgets.find((w) => w.name === "Character Info");
            if (w && message.description && message.description[0]) w.value = message.description[0];
        };
    },
});
