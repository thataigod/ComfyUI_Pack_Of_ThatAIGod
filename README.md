# ComfyUI Pack Of ThatAIGod

[![CI](https://github.com/thataigod/ComfyUI-Pack-Of-ThatAIGod/actions/workflows/python-package.yml/badge.svg)](https://github.com/thataigod/ComfyUI-Pack-Of-ThatAIGod/actions/workflows/python-package.yml)

A custom node pack for [ComfyUI](https://github.com/comfyanonymous/ComfyUI) providing LLM integration, image utilities, resolution management, and wildcard-based prompt generation.

## Features

- **LLM Chat** - Connect to OpenRouter API or local LLM servers (LM Studio) with streaming responses
- **Image Saver Plus** - Save images with format selection, quality control, template variables, and text sidecars
- **Dynamic Resolution Picker** - Calculate optimal width/height for any aspect ratio
- **Dynamic Resolution Selector** - Multi-select aspect ratios with max/min side constraint and custom W:H ratio support
- **Wildcard Reader** - Resolve `__wildcard__` placeholders from curated text files with `{A|B|C}` choice syntax
- **Sequential Image Loader** - Iterate through directory images with natural sorting
- **Upscale By Max Side** - Aspect-ratio-preserving upscaler
- **Truncate LLM Thinking** - Strip thinking/reasoning blocks from LLM output

## Installation

### Option 1: Git Clone

Navigate to your ComfyUI `custom_nodes` directory and clone:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/thataigod/ComfyUI-Pack-Of-ThatAIGod.git
```

### Option 2: ComfyUI Manager

Search for "Pack Of ThatAIGod" in ComfyUI Manager and install directly.

### Option 3: Manual Download

1. Download the ZIP from GitHub
2. Extract to `ComfyUI/custom_nodes/ComfyUI_Pack_Of_ThatAIGod`

## API Key Setup

### OpenRouter (Recommended)

Set your API key as an environment variable:

```bash
# Windows (PowerShell)
[System.Environment]::SetEnvironmentVariable('OPENROUTER_API_KEY', 'sk-or-v1-your-key-here', 'User')

# Linux/macOS
export OPENROUTER_API_KEY='sk-or-v1-your-key-here'
```

The node supports three environment variable names:
- `OPENROUTER_API_KEY` (default)
- `OPENROUTER_API_KEY_BACKUP`
- `OPENROUTER_API_KEY_EXTRA`

This allows switching between multiple API keys without modifying system variables.

### Local LLM (LM Studio)

1. Start [LM Studio](https://lmstudio.ai/) with a loaded model
2. Enable the local server (default: `http://localhost:1234/v1`)
3. In ComfyUI, set Mode to **Local**

## Node Reference

### LLM Chat (OpenRouter/Local)

Category: `ThatAIGod/LLM`

Connects to OpenRouter or a local LLM server for text generation with streaming responses.

| Input | Type | Description |
|-------|------|-------------|
| Mode | Dropdown | `OpenRouter` or `Local` |
| Model | Dropdown | Auto-fetched model list from OpenRouter, or local model |
| System Prompt | STRING | System instructions for the LLM |
| User Prompt | STRING | Your input text (supports dynamic connections) |
| Temperature | FLOAT | Randomness (0.0 = deterministic, 2.0 = max creative) |
| Max Tokens | INT | Maximum response length (1-128000) |
| seed | INT | For deterministic generation. **Note:** seed `0` is treated as "no seed" and is omitted from the request payload; use any non-zero value for reproducible outputs |
| Timeout (Seconds) | INT | Request timeout (1-300) |
| API Key Env Var | Dropdown | Which environment variable holds your API key |
| Local URL | STRING | Local LLM server endpoint |
| Image(s) | IMAGE | Optional image input for vision models. Images larger than 8192×8192 pixels will raise an error |

| Output | Type | Description |
|--------|------|-------------|
| Generated Text | STRING | The LLM response |
| Status (Boolean) | BOOLEAN | `True` if generation succeeded |
| Information | STRING | Latency and credit info |
| Reasoning Content | STRING | Model's reasoning/thinking text (if provided) |

**Features:**
- Streaming responses displayed in real-time via WebSocket
- Response caching (last 10 requests) for faster re-runs
- Vision support - connect images for multimodal models
- Credit balance display for OpenRouter
- Reasoning content extracted separately from the clean response

### LLM Fallback Switch

Category: `ThatAIGod/LLM`

Passes generated text through if the LLM succeeded, otherwise falls back to the original input.

| Input | Type | Description |
|-------|------|-------------|
| Original Input | STRING | The fallback text (required) |
| Generated Text | STRING | LLM output (optional) |
| Status (Boolean) | BOOLEAN | LLM success status (optional) |

| Output | Type | Description |
|--------|------|-------------|
| Final Text | STRING | Generated text if successful, otherwise original input |

### Dynamic Resolution Picker

Category: `ThatAIGod/Image Utils`

Calculates optimal image dimensions based on aspect ratio and scale factor.

| Input | Type | Description |
|-------|------|-------------|
| Max Side Pixels | INT | Target resolution (256-16384) |
| Aspect Ratio | Dropdown | 15 presets including random portrait/landscape |
| Scale Factor | FLOAT | Multiplier for upscale dimensions |
| seed | INT | For random ratio selection |

| Output | Type | Description |
|--------|------|-------------|
| Width | INT | Base width (rounded to 8px) |
| Height | INT | Base height (rounded to 8px) |
| Scaled Width | INT | Width after scale factor |
| Scaled Height | INT | Height after scale factor |
| Scale Factor | FLOAT | The applied multiplier |
| Keywords | STRING | Aspect ratio description for prompts |
| Guide Size | INT | Min(width, height) |
| Max Size | INT | Max(width, height) |

**Aspect Ratio Presets:**
- Square 1:1
- Portrait: 2:3, 3:4, 4:5, 9:16
- Landscape: 3:2, 4:3, 5:4, 16:9, 16:10, 21:9, 1.85:1
- Random (Any, Portrait, or Landscape)

### Image Saver Plus

Category: `ThatAIGod/Image Utils`

Saves images with format selection, quality/compression control, filename template variables, and optional text sidecar files.

| Input | Type | Description |
|-------|------|-------------|
| images | IMAGE | The images to save |
| filename_prefix | STRING | Prefix with template variables. Supports `%width%`, `%height%`, `%date:FORMAT%` (e.g. `%date:yyyy_MM_dd%`), `%year%`, `%month%`, `%day%`, `%hour%`, `%minute%`, `%second%` (shorthand for the most common date parts), `%counter%` (sequential number, place anywhere in the filename), and `%batch_num%` |
| file_format | Dropdown | `png`, `jpeg`, or `webp` |
| quality | INT | Quality for JPEG/WebP (1-100, default 95) |
| compress_level | INT | PNG compression (0-9, default 4) |
| save_text | STRING | Optional text to save as a `.txt` sidecar alongside each image |

**Examples:**
- `ComfyUI/Chroma/%date:yyyy_MM_dd%/PiX_%date:yyyyMMdd%_%counter%_PreFaceFix` produces `ComfyUI/Chroma/2026_05_30/PiX_20260530_00001_PreFaceFix.png`
- Using `%counter%` in the filename prevents overwrites — the counter scans existing files and increments automatically

### Wildcard Reader

Category: `ThatAIGod/Text Utils`

Resolves `__wildcard__` placeholders by randomly selecting lines from `.txt` files in the `wildcards/` directory.

| Input | Type | Description |
|-------|------|-------------|
| text | STRING | Text containing `__wildcard__` tags |
| Select to add Wildcard | Dropdown | Quick-insert wildcard tags |
| mode | Dropdown | `Deterministic (Seed)`, `Full Random`, or `Random (No Repeat)` |
| seed | INT | For deterministic mode |
| delimiter | STRING | Separator when combining prepend/main/append text |
| Prependable Text | STRING | Text added before the result |
| Appendable Text | STRING | Text added after the result |

| Output | Type | Description |
|--------|------|-------------|
| Text | STRING | Resolved text with wildcards replaced |

**Modes:**
- **Deterministic (Seed)** - Same seed = same output every time
- **Full Random** - Completely random selection each run
- **Random (No Repeat)** - Shuffles and draws without replacement until depleted

**Inline Choice Syntax:**
Use `{option1|option2|option3}` in your text to randomly pick one option (separated by `|`). Works alongside `__wildcard__` tags and respects the same mode/seed settings.

**Nested Wildcards:**
Wildcard files can reference other wildcards. For example, `all_colors_male.txt` contains:
```
__neutral_colors_male__
__earthtone_colors_male__
__jeweltone_colors_male__
```
These are recursively resolved up to 50 iterations.

**Built-in Wildcard Files:**
- Color palettes (8 categories x 2 genders)
- Outfit components (traditional, formal, casual, athletic, costume, swimwear, lingerie)
- Subject descriptions (male/female)
- Complete scene assemblers

### Sequential Image Loader

Category: `ThatAIGod/Image Utils`

Iterates through images in a directory using a seed-based index.

| Input | Type | Description |
|-------|------|-------------|
| Directory Path | STRING | Absolute path to image directory |
| seed | INT | Index of the image to load |

| Output | Type | Description |
|--------|------|-------------|
| Image | IMAGE | The loaded image tensor |
| Filename | STRING | Filename without extension |
| Stats | STRING | Current index / total files (e.g., "3/50") |

**Tip:** Set "Control After Generate" to "Increment" on the node to auto-advance through images.

### Dynamic Resolution Selector

Category: `ThatAIGod/Image Utils`

Multi-select aspect ratios with constraint mode (max side or min side) and optional custom W:H ratio with scaling.

| Input | Type | Description |
|-------|------|-------------|
| Limit By | Dropdown | `Max Side` or `Min Side` constraint for the Pixels value |
| Pixels | INT | Pixel budget for the constrained side (1-16384) |
| Scale Factor | FLOAT | Multiplier for Scaled Width/Height outputs |
| Aspect Ratio Config | STRING | JSON config managed by the frontend UI with toggle buttons for each ratio, batch selectors (All/Portraits/Landscapes), and a custom W:H ratio input |
| seed | INT | Seed for random ratio selection from the active set |

| Output | Type | Description |
|--------|------|-------------|
| Width | INT | Base width (rounded to 8px) |
| Height | INT | Base height (rounded to 8px) |
| Scaled Width | INT | Width after scale factor |
| Scaled Height | INT | Height after scale factor |
| Scale Factor | FLOAT | The applied multiplier |
| Keywords | STRING | Aspect ratio description for prompts |
| Guide Size | INT | Min(width, height) |
| Max Size | INT | Max(width, height) |

### Upscale By Max Side

Category: `ThatAIGod/Image Utils`

Upscales an image so its longest side matches the target, preserving aspect ratio.

| Input | Type | Description |
|-------|------|-------------|
| Image | IMAGE | Input image |
| Max Side | INT | Target pixel count for longest side |
| Divisibility | INT | Round dimensions to this value |
| Method | Dropdown | `lanczos`, `bicubic`, `bilinear`, `nearest-exact`, `area` |

| Output | Type | Description |
|--------|------|-------------|
| Image | IMAGE | Upscaled image |
| Width | INT | Final width |
| Height | INT | Final height |

### Truncate LLM Thinking

Category: `ThatAIGod/Text Utils`

Removes content between configurable start/end tokens from LLM output.

| Input | Type | Description |
|-------|------|-------------|
| Text | STRING | LLM output containing thinking blocks |
| Start Token | STRING | Beginning marker (default: `<think>`) |
| End Token | STRING | Ending marker (default: `</think>`) |

| Output | Type | Description |
|--------|------|-------------|
| Cleaned Text | STRING | Text with thinking blocks removed |
| Thinking Content | STRING | Extracted thinking content |

## Wildcard System

### Directory Structure

```
wildcards/
  autowildcards/          # Generated wildcard files
    neutral_colors_male.txt
    neutral_colors_female.txt
    earthtone_colors_male.txt
    ... (36 files total)
  wildcard_generator.bat  # Regenerate all wildcard files
  colors.bat              # Simplified color list generator
  find.bat                # Search utility for wildcards
```

### Adding Custom Wildcards

1. Create a `.txt` file in `wildcards/` or `wildcards/autowildcards/`
2. Add one entry per line
3. Use `#` at the start of a line for comments
4. Reference it in your prompt as `__filename__` (without `.txt`)

### Example Prompt

```
A woman wearing a __female_casual_outfit__ in __bright_colors_female__ colors,
standing in a __subject_female__ pose, {smiling|looking serious|laughing}
```

## UI Features

### LLM Node
- **Streaming Preview** - Watch tokens appear in real-time
- **Refresh Models** - Fetch latest available models from OpenRouter
- **Live Credit Display** - See remaining OpenRouter credits

### Wildcard Reader
- **Dropdown Selector** - Browse and insert wildcard tags directly
- **Auto-insert** - Selected wildcards append to the text field

## Troubleshooting

### "No API Key found"
Set the `OPENROUTER_API_KEY` environment variable or select a different one from the dropdown.

### "Local URL must be localhost"
The Local URL field only accepts `localhost` or `127.0.0.1` for security. Ensure your LLM server is running locally.

### Wildcards not resolving
- Check that your `.txt` files are in the `wildcards/` directory
- Ensure wildcard tags use double underscores: `__tag__`
- Verify the filename matches (case-insensitive on Windows)

### Images not loading
- Use absolute paths for the Sequential Image Loader
- Supported formats: `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.tiff`

## License

MIT
