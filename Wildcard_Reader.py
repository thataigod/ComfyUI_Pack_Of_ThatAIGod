import os
import random
import re

class WildcardReader:
    def __init__(self):
        self._deck_cache = {}

    @classmethod
    def INPUT_TYPES(s):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        wildcards_dir = os.path.join(current_dir, "wildcards")
        
        wildcard_files = []
        
        if os.path.exists(wildcards_dir):
            # 1. Get files in the root directory first
            root_files = [
                f"__{f.replace('.txt', '')}__" 
                for f in os.listdir(wildcards_dir) 
                if os.path.isfile(os.path.join(wildcards_dir, f)) and f.endswith('.txt')
            ]
            wildcard_files.extend(sorted(root_files))

            # 2. Walk through subdirectories for the dropdown list
            sub_entries = []
            for root, dirs, files in os.walk(wildcards_dir):
                dirs.sort() 
                
                rel_path = os.path.relpath(root, wildcards_dir)
                if rel_path == ".":
                    continue

                for f in files:
                    if f.endswith('.txt'):
                        sub_path = os.path.join(rel_path, f).replace("\\", "/")
                        entry = f"__{sub_path.replace('.txt', '')}__"
                        sub_entries.append(entry)
            
            wildcard_files.extend(sorted(sub_entries))

        options_list = ["Select a file from the wildcards directory"] + wildcard_files

        return {
            "required": {
                "text": ("STRING", {"multiline": True, "dynamic": True, "placeholder": "Text in this field is evaluated for wildcards. Example: 'A woman wearing a __colors__ top'"}),
                "Select to add Wildcard": (options_list, ),
                # ADDED: "Random (No Repeat)" mode
                "mode": (["Deterministic (Seed)", "Full Random", "Random (No Repeat)"], {"default": "Deterministic (Seed)"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "delimiter": ("STRING", {"default": ", "}),
            },
            "optional": {
                "Prependable Text": ("STRING", {"forceInput": True}),
                "Appendable Text": ("STRING", {"forceInput": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("Text",)
    FUNCTION = "process"
    CATEGORY = "ThatAIGod/Text Utils"

    @classmethod
    def IS_CHANGED(s, text, mode, seed, delimiter, **kwargs):
        # Force re-run for Random modes so state updates
        if mode != "Deterministic (Seed)":
            return float("nan")
        return seed

    def process(self, text, mode, seed, delimiter, **kwargs):
        # 1. Handle Inputs
        prepend_text = kwargs.get("Prependable Text", "")
        append_text = kwargs.get("Appendable Text", "")

        # 2. Setup Random Generator
        # For "No Repeat", we use the seed to shuffle the deck initially if needed,
        # but the drawing process is stateful.
        if mode == "Deterministic (Seed)":
            rng = random.Random(seed)
        else:
            rng = random.Random() # System random for Full Random / Shuffle

        # 3. Setup Directory & Build Global Search Index
        current_dir = os.path.dirname(os.path.realpath(__file__))
        wildcards_dir = os.path.join(current_dir, "wildcards")
        
        file_index = {}
        
        if not os.path.exists(wildcards_dir):
            os.makedirs(wildcards_dir, exist_ok=True)
        
        for root, dirs, files in os.walk(wildcards_dir):
            dirs.sort()
            files.sort()
            for f in files:
                if f.endswith(".txt"):
                    if f not in file_index:
                        file_index[f] = []
                    
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, wildcards_dir)
                    rel_path = rel_path.replace("\\", "/")
                    file_index[f].append(rel_path)

        # 4. Smart Resolver Function
        def get_line_from_file(wildcard_tag):
            clean_tag = wildcard_tag.strip("_")
            
            if not clean_tag.endswith(".txt"):
                search_filename = clean_tag + ".txt"
            else:
                search_filename = clean_tag

            # Resolve Path
            direct_path = os.path.join(wildcards_dir, search_filename)
            final_path = None

            if os.path.exists(direct_path):
                final_path = direct_path
            else:
                base_name = os.path.basename(search_filename)
                if base_name in file_index:
                    candidate_rel_path = file_index[base_name][0]
                    final_path = os.path.join(wildcards_dir, candidate_rel_path)
                else:
                    return f"__{wildcard_tag}__"

            # Prevent path traversal: ensure resolved path stays within wildcards_dir
            real_wildcards = os.path.realpath(wildcards_dir)
            real_final = os.path.realpath(final_path)
            if not real_final.startswith(real_wildcards + os.sep) and real_final != real_wildcards:
                return f"__{wildcard_tag}__"

            # --- SELECTION LOGIC ---
            
            # Logic A: "Random (No Repeat)" -> The Deck System
            if mode == "Random (No Repeat)":
                # Check if this specific file is in our cache and has cards left
                if final_path not in self._deck_cache or len(self._deck_cache[final_path]) == 0:
                    try:
                        with open(final_path, 'r', encoding='utf-8') as f:
                            lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                        
                        if not lines: return ""
                        
                        # Shuffle and store a fresh deck
                        rng.shuffle(lines)
                        self._deck_cache[final_path] = lines
                        # print(f"[WildcardReader] Refilled deck for: {final_path}")
                    except Exception:
                        return f"__{wildcard_tag}__"

                # Pop one card from the deck
                return self._deck_cache[final_path].pop(0)

            # Logic B: Standard Random (Seed or Full)
            else:
                try:
                    with open(final_path, 'r', encoding='utf-8') as f:
                        lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
                    if not lines:
                        return ""
                    # Use the pre-configured RNG
                    if mode == "Deterministic (Seed)":
                        return rng.choice(sorted(lines)) # Sort for strict seed adherence
                    else:
                        return rng.choice(lines)
                except Exception:
                    return f"__{wildcard_tag}__"

        # 5. Recursive Processing
        processed_text = text if text else ""
        pattern = re.compile(r"__([a-zA-Z0-9_\-\/\\\.]+)__")
        
        iteration = 0
        max_iterations = 50 

        while iteration < max_iterations:
            matches = list(set(pattern.findall(processed_text)))
            if not matches:
                break
            
            matches.sort() 

            found_replacement = False
            for match in matches:
                replacement = get_line_from_file(match)
                tag_str = f"__{match}__"
                
                if replacement == tag_str:
                    continue 

                # IMPORTANT: Replace 1 at a time.
                # If text is "__color__ __color__", and mode is "No Repeat",
                # we want to pop 'Red' for the first one, then loop, and pop 'Blue' for the second.
                if tag_str in processed_text:
                    processed_text = processed_text.replace(tag_str, replacement, 1)
                    found_replacement = True
                    break 
            
            if not found_replacement:
                break
            iteration += 1

        processed_text = processed_text.strip()
        
        # 6. Concatenation
        parts = []
        if prepend_text and prepend_text.strip():
            parts.append(prepend_text.strip())
        
        if processed_text:
            parts.append(processed_text)
            
        if append_text and append_text.strip():
            parts.append(append_text.strip())
            
        final_output = delimiter.join(parts)

        return (final_output,)

NODE_CLASS_MAPPINGS = {
    "WildcardReader": WildcardReader
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "WildcardReader": "Wildcard Reader"
}