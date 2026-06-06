# pdf_to_images.py

import fitz
import os
import numpy as np
from PIL import Image
from config import OUTPUT_DIR, PDF_DPI

# ─────────────────────────────────────────────────────────────
# White ink fix
# ─────────────────────────────────────────────────────────────

def fix_white_ink(img):
    """Remaps near-white ink to black, leaves all other colors untouched"""
    arr = np.array(img.convert("RGB")).astype(np.uint8)
    r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
    near_white       = (r > 200) & (g > 200) & (b > 200)
    pure_background  = (r > 250) & (g > 250) & (b > 250)
    white_ink_mask   = near_white & ~pure_background
    arr[white_ink_mask] = [0, 0, 0]
    return Image.fromarray(arr)


# ─────────────────────────────────────────────────────────────
# Duplicate detection
# ─────────────────────────────────────────────────────────────

def image_hash(img):
    """Returns array for duplicate comparison"""
    return np.array(img.resize((64, 64)).convert("L")).flatten().astype(int)

def is_duplicate(img, previous_arrays, threshold=5):
    """Returns True if page is visually identical to a recent page"""
    current = image_hash(img)
    for prev in previous_arrays[-3:]:
        if np.abs(current - prev).mean() < threshold:
            return True
    return False


# ─────────────────────────────────────────────────────────────
# Main pipeline function
# ─────────────────────────────────────────────────────────────

def pdf_to_images(pdf_path):
    """
    Converts each PDF page to a high quality PNG, skipping duplicates.
    Maps full pages directly to the diagram_map to ensure they embed in Obsidian.

    Returns:
        image_paths: list of full-page PNG paths
        diagram_map: dict mapping page stem → [full_page_path] for Obsidian embedding
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    doc              = fitz.open(pdf_path)
    image_paths      = []
    diagram_map      = {}  # Stores full pages so obsidian_writer can see them
    previous_arrays  = []
    skipped          = 0
    
    # Track page index gaplessly to stay matched with Gemini's array sequence
    saved_page_count = 1 

    print(f"Found {len(doc)} pages in {os.path.basename(pdf_path)}")

    for page_num in range(len(doc)):
        page = doc[page_num]
        mat  = fitz.Matrix(PDF_DPI / 72, PDF_DPI / 72)
        pix  = page.get_pixmap(matrix=mat)
        img  = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        img = fix_white_ink(img)

        current_arr = image_hash(img)
        if is_duplicate(img, previous_arrays):
            print(f"  Page {page_num + 1}: duplicate detected, skipping")
            skipped += 1
            previous_arrays.append(current_arr)
            continue

        previous_arrays.append(current_arr)

        # Use sequential count instead of absolute page_num to avoid gap desyncs
        page_stem      = f"page_{saved_page_count:03d}"
        image_filename = f"{page_stem}.png"
        image_path     = os.path.join(OUTPUT_DIR, image_filename)
        img.save(image_path, format="PNG")
        image_paths.append(image_path)
        print(f"  Saved page {page_num + 1} as → {image_filename}")

        # 🌟 THE FIX: Map the full page path to the page stem so the writer embeds it
        diagram_map[page_stem] = [image_path]

        saved_page_count += 1

    doc.close()
    print(f"\nDone. {len(image_paths)} pages kept, {skipped} duplicates skipped.")

    return image_paths, diagram_map