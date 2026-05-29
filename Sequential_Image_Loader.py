import os
import torch
import numpy as np
import re
from PIL import Image, ImageOps

class SequentialImageLoader:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "Directory Path": ("STRING", {"default": "", "multiline": False, "placeholder": "C:\\Images\\Dataset"}),
                # Changing input name to 'seed' activates the built-in ComfyUI widget.
                # User simply selects "Control After Generate: Increment" on the node itself.
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "STRING")
    RETURN_NAMES = ("Image", "Filename", "Stats")
    FUNCTION = "load_next"
    CATEGORY = "ThatAIGod/Image Utils"

    def natural_sort_key(self, s):
        return [(0, int(text)) if text.isdigit() else (1, text.lower()) for text in re.split(r'(\d+)', s)]

    def load_next(self, **kwargs):
        directory_path = kwargs.get("Directory Path", "")
        # The 'seed' now acts as our auto-incrementing index
        index = kwargs.get("seed", 0)

        # 1. Validation
        if not directory_path or not os.path.exists(directory_path):
            print(f"[SequentialLoader] Error: Directory not found -> {directory_path}")
            return (torch.zeros((1, 64, 64, 3)), "error_no_dir", "0/0")

        # 2. Scanning
        valid_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff')
        files = [f for f in os.listdir(directory_path) if f.lower().endswith(valid_extensions)]
        
        # 3. Sorting
        files.sort(key=self.natural_sort_key)
        
        total_files = len(files)
        if total_files == 0:
            print("[SequentialLoader] No images found.")
            return (torch.zeros((1, 64, 64, 3)), "error_empty_dir", "0/0")

        # 4. Modulo Logic (The Loop)
        # This prevents out-of-bounds errors. 
        # If index > total_files, it wraps around to 0.
        safe_index = index % total_files
        current_filename = files[safe_index]
        
        filename_no_ext = os.path.splitext(current_filename)[0]
        stats = f"{safe_index + 1}/{total_files}"

        print(f"[SequentialLoader] Processing {stats}: {current_filename}")

        # 5. Loading
        try:
            img_path = os.path.join(directory_path, current_filename)
            i = Image.open(img_path)
            i = ImageOps.exif_transpose(i)
            
            if i.mode != 'RGB':
                i = i.convert('RGB')
            
            # Convert to Tensor [1, H, W, 3]
            image = np.array(i).astype(np.float32) / 255.0
            image = torch.from_numpy(image)[None,]
            
            return (image, filename_no_ext, stats)

        except Exception as e:
            print(f"[SequentialLoader] Failed to load {current_filename}: {e}")
            return (torch.zeros((1, 64, 64, 3)), "error_load", stats)

NODE_CLASS_MAPPINGS = {
    "SequentialImageLoader": SequentialImageLoader
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SequentialImageLoader": "Sequential Image Loader"
}