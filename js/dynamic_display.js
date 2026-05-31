import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const LLM_WIDGET_HEIGHT = 130;
const LLM_WIDGET_TOTAL_HEIGHT = LLM_WIDGET_HEIGHT + 20;
const SPACER_HEIGHT = 10;
const MIN_NODE_WIDTH = 400;

app.registerExtension({
    name: "ThatAIGod.DynamicFeatures",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        
        // ============================================================
        // 1. LLM Node Logic
        // ============================================================
        if (nodeData.name === "LLM_Node") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                // 1. Stream Preview Widget (Fixed Window)
                try {
                    const config = { multiline: true };
                    const w = ComfyWidgets["STRING"](this, "Full LLM Response or Any Errors", ["STRING", config], app).widget;
                    
                    w.inputEl.readOnly = true;
                    w.inputEl.style.opacity = 0.6;
                    w.inputEl.style.fontFamily = "monospace";
                    
                    // --- CSS Enforcements (Reduced Height) ---
                    w.inputEl.style.height = LLM_WIDGET_HEIGHT + "px";
                    w.inputEl.style.minHeight = LLM_WIDGET_HEIGHT + "px";
                    w.inputEl.style.maxHeight = LLM_WIDGET_HEIGHT + "px";
                    w.inputEl.style.overflowY = "scroll"; 
                    w.inputEl.style.resize = "none";      
                    w.inputEl.style.whiteSpace = "pre-wrap"; 
                    
                    w.name = "Full LLM Response or Any Errors"; 
                    
                    // --- LAYOUT: content + gap ---
                    w.computeSize = function(width) {
                        return [width, LLM_WIDGET_TOTAL_HEIGHT]; 
                    };

                } catch (e) {
                    console.error("ThatAIGod: Failed to create Stream widget", e);
                }

                // 2. Refresh Button
                this.addWidget("button", "Refresh Models", null, () => {
                    this.refreshModels().catch((err) => console.error("Refresh failed:", err));
                });

                // 3. Spacer Widget (Bottom Buffer)
                const spacer = this.addWidget("label", "", ""); 
                spacer.computeSize = function(width) {
                    return [width, SPACER_HEIGHT];
                };

                // 4. Force Resize
                requestAnimationFrame(() => {
                    const sz = this.computeSize();
                    if (this.size[0] < MIN_NODE_WIDTH) this.size[0] = MIN_NODE_WIDTH;
                    if (this.size[1] < sz[1]) this.size[1] = sz[1];
                    this.onResize?.(this.size);
                });

                // 5. WebSocket Listener
                const streamHandler = (event) => {
                    if (String(event.detail.node) !== String(this.id)) return;
                    
                    const w = this.widgets.find(w => w.name === "Full LLM Response or Any Errors");
                    if (!w) return;

                    if (event.detail.type === "start") {
                        w.value = ""; 
                    } else if (event.detail.type === "update") {
                        w.value += event.detail.delta;
                        if (w.inputEl) {
                            w.inputEl.scrollTop = w.inputEl.scrollHeight;
                        }
                    } else if (event.detail.type === "clear") {
                        w.value = "";
                    }
                };
                api.addEventListener("that_ai_god.stream", streamHandler);

                // Cleanup listener when node is removed
                const onRemoved = nodeType.prototype.onRemoved;
                nodeType.prototype.onRemoved = function () {
                    api.removeEventListener("that_ai_god.stream", streamHandler);
                    return onRemoved ? onRemoved.apply(this, arguments) : undefined;
                };

                // 6. Mode Listener
                const modeWidget = this.widgets.find(w => w.name === "Mode");
                if (modeWidget) {
                    const originalCallback = modeWidget.callback;
                    modeWidget.callback = (value) => {
                        if (originalCallback) originalCallback.call(modeWidget, value);
                        this.refreshModels();
                    };
                }

                return r;
            };

            nodeType.prototype.refreshModels = async function() {
                const modeWidget = this.widgets.find(w => w.name === "Mode");
                const modelWidget = this.widgets.find(w => w.name === "Model");
                const localUrlWidget = this.widgets.find(w => w.name === "Local URL");

                if (!modeWidget || !modelWidget) return;

                const mode = modeWidget.value;
                let fetchUrl = "";
                
                if (mode === "OpenRouter") {
                    fetchUrl = "https://openrouter.ai/api/v1/models";
                } else {
                    let rawUrl = localUrlWidget ? localUrlWidget.value : "http://localhost:1234/v1";
                    if(rawUrl) {
                        // Ensure URL has protocol for parsing
                        const normalizedUrl = rawUrl.includes("://") ? rawUrl : "http://" + rawUrl;
                        const allowedHosts = ["localhost", "127.0.0.1", "::1"];
                        const parsed = new URL(normalizedUrl);
                        if (!allowedHosts.includes(parsed.hostname)) {
                            throw new Error(`Local URL must be localhost (got ${parsed.hostname})`);
                        }
                        rawUrl = rawUrl.replace(/\/chat\/completions\/?$/, ""); 
                        rawUrl = rawUrl.replace(/\/v1\/?$/, ""); 
                        rawUrl = rawUrl.replace(/\/$/, ""); 
                        fetchUrl = rawUrl + "/v1/models";
                    } else {
                        fetchUrl = "http://localhost:1234/v1/models";
                    }
                }

                try {
                    const originalValue = modelWidget.value;
                    modelWidget.value = "Fetching...";
                    const response = await fetch(fetchUrl);
                    if (!response.ok) throw new Error(`HTTP ${response.status}`);
                    const data = await response.json();
                    let models = [];
                    if (data.data && Array.isArray(data.data)) {
                        models = data.data.map(m => m.id);
                    } else {
                        throw new Error("Invalid JSON format");
                    }
                    if (models.length > 0) {
                        modelWidget.options.values = models;
                        modelWidget.value = models[0]; 
                    } else {
                        modelWidget.value = originalValue;
                    }
                } catch (error) {
                    console.error(error);
                    const errorWidget = this.widgets.find(w => w.name === "Full LLM Response or Any Errors");
                    if (errorWidget) {
                        errorWidget.value = `[ERROR] Failed to fetch models: ${error.message || error}`;
                    }
                    if (modelWidget.value === "Fetching...") {
                        modelWidget.value = "anthropic/claude-3.5-sonnet"; 
                    }
                }
            };
        }

        // ============================================================
        // 2. Dynamic Resolution Picker
        // ============================================================
        if (nodeData.name === "DynamicResolution") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                const w = ComfyWidgets["STRING"](this, "Resolution Info", ["STRING", { multiline: true }], app).widget;
                w.inputEl.readOnly = true;
                return r;
            };

            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                onExecuted?.apply(this, arguments);
                if (message) {
                    const updateOutput = (index, val, labelName) => {
                        if (this.outputs && this.outputs[index]) {
                            this.outputs[index].name = `${val} ${labelName}`; 
                            this.outputs[index].label = " "; 
                        }
                    };
                    if (message.width) updateOutput(0, message.width[0], "Width");
                    if (message.height) updateOutput(1, message.height[0], "Height");
                    if (message.scaled_width) updateOutput(2, message.scaled_width[0], "Scaled Width");
                    if (message.scaled_height) updateOutput(3, message.scaled_height[0], "Scaled Height");
                    if (message.scale_factor) updateOutput(4, message.scale_factor[0], "Scale Factor");
                    if (message.guide_size) updateOutput(6, message.guide_size[0], "Guide Size");
                    if (message.max_size) updateOutput(7, message.max_size[0], "Max Size");
                    
                    if (message.text && message.text.length > 0) {
                        const w = this.widgets.find((w) => w.name === "Resolution Info");
                        if (w) w.value = message.text[0];
                    }
                }
            };
            
            const onDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function (ctx) {
                onDrawForeground?.apply(this, arguments);
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
        }

        // ============================================================
        // 3. Wildcard Reader
        // ============================================================
        if (nodeData.name === "WildcardReader") {
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                
                const wildSelector = this.widgets.find(w => w.name === "Select to add Wildcard");
                const textWidget = this.widgets.find(w => w.name === "text");

                if (wildSelector && textWidget) {
                    const originalCallback = wildSelector.callback;
                    wildSelector.callback = function (value) {
                        if (originalCallback) originalCallback.apply(this, arguments);
                        if (value && value !== "Select a file from the wildcards directory") {
                            if (textWidget.value && textWidget.value.length > 0 && !textWidget.value.endsWith(" ")) {
                                textWidget.value += " " + value;
                            } else {
                                textWidget.value += value;
                            }
                            queueMicrotask(() => {
                                wildSelector.value = "Select a file from the wildcards directory";
                                app.graph.setDirtyCanvas(true);
                            });
                        }
                    };
                }
                return r;
            };
        }
    },
});