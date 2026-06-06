# Wildcards Directory

This directory holds the wildcard `.txt` files used by the **Wildcard Reader** node.

---

## Structure

```
wildcards/
├── README.md               ← this file
├── wildcard_generator.bat  ← regenerates all autowildcard files
├── colors.bat              ← generates root-level colour files
├── *.txt                   ← root-level wildcard files (referenced as __name__)
└── autowildcards/
    └── *.txt               ← organised wildcard files (referenced as __autowildcards/name__)
```

---

## How to Reference Wildcards

In the Wildcard Reader node's text field, wrap the filename (without `.txt`) in double underscores:

| File | Tag |
|------|-----|
| `wildcards/colors.txt` | `__colors__` |
| `wildcards/autowildcards/female_casual_outfit.txt` | `__autowildcards/female_casual_outfit__` |

The node dropdown shows all available tags — click one to insert it automatically.

---

## Wildcard File Format

One entry per line. Lines starting with `#` are treated as comments and skipped.
Blank lines are ignored.

```text
# This is a comment
fiery red
ocean blue
emerald green
```

---

## Inline Choice Syntax

Use `{option1|option2|option3}` directly in text (pipe-separated) to randomly pick one option
without needing a separate file:

```
A {smiling|serious|laughing} person wearing __autowildcards/female_casual_outfit__
```

---

## Adding New Wildcards

1. Create a `.txt` file with one entry per line.
2. Place it in `wildcards/` (for root-level tags) or `wildcards/autowildcards/` (for organised tags).
3. Reference it in prompts using the appropriate tag syntax above.

---

## Regenerating autowildcards

Run `wildcard_generator.bat` from this directory to regenerate all files in `autowildcards/`:

```bat
cd wildcards
wildcard_generator.bat
```

The script sources entries from the root-level colour `.txt` files and combines them
into outfit-focused compound wildcards (e.g. `female_casual_outfit.txt` references
`__neutral_colors_female__`, which is itself a wildcard file).
