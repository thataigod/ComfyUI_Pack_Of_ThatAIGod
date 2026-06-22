# ComfyUI Pack Of ThatAIGod

Welcome to the API documentation for **ComfyUI_Pack_Of_ThatAIGod**, a custom node pack for
[ComfyUI](https://github.com/comfyanonymous/ComfyUI) providing LLM integration, image utilities,
resolution management, and wildcard-based prompt generation.

## Quick Links

- [GitHub Repository](https://github.com/thataigod/ComfyUI-Pack-Of-ThatAIGod)
- [README with full usage guide](https://github.com/thataigod/ComfyUI-Pack-Of-ThatAIGod/blob/master/README.md)
- [Changelog](https://github.com/thataigod/ComfyUI-Pack-Of-ThatAIGod/blob/master/CHANGELOG.md)
- [Contributing Guide](https://github.com/thataigod/ComfyUI-Pack-Of-ThatAIGod/blob/master/CONTRIBUTING.md)

## Modules

| Module | Description |
|--------|-------------|
| `__init__` | Package entry point — loads all nodes into ComfyUI |
| `_utils` | Shared utilities: dimension math, safe imports, logging |
| `llm_utils` | LLM request building, streaming, retry logic |
| `Dynamic_Resolution_Picker` | Aspect-ratio-aware resolution calculator |
| `Image_Saver_Plus` | Image saving with format/quality/template support |
| `Resolution_Selector` | Multi-select aspect ratio resolution picker |
| `Sequential_Image_Loader` | Seed-indexed image directory loader |
| `Truncate_LLM_Thinking` | Strips thinking/reasoning blocks from LLM output |
| `Upscale_By_Max_Side` | Aspect-ratio-preserving upscaler |
| `Wildcard_Reader` | Resolves `__wildcard__` placeholders from text files |
| `LLM_Node` | LLM Chat node with OpenRouter/Local server support |
| `LLM_Fallback_Node` | Falls back to original text on LLM failure |

## Building Docs

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Serve locally
mkdocs serve

# Build static site
mkdocs build
```
