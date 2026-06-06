import os
import re
import shutil
from datetime import datetime
from config import OBSIDIAN_VAULT_PATH


def _copy_diagrams_to_vault(diagram_map, course_folder):
    """
    Copies all full page layout PNGs from OUTPUT_DIR into the course folder.
    Returns a dict mapping original crop basename → destination path.
    """
    copied = {}
    for page_stem, crop_paths in diagram_map.items():
        for crop_path in crop_paths:
            basename = os.path.basename(crop_path)
            dest     = os.path.join(course_folder, basename)
            try:
                shutil.copy2(crop_path, dest)
                copied[basename] = dest
            except Exception as e:
                print(f"  ⚠️  Could not copy {basename}: {e}")
    return copied


def _inject_diagram_embeds(content, diagram_map):
    """
    Injects the full page layout image directly below its corresponding 
    '## Page X' header, ensuring the page image is displayed BEFORE the text.
    Also strips dangling legacy transcription [IMAGE: description] placeholders.
    
    Returns the updated content string.
    """
    if not diagram_map:
        return content

    # Split text by page headers while capturing header text and page numbers
    parts = re.split(r'(##\s+Page\s+(\d+))', content, flags=re.IGNORECASE)
    
    # Fallback to standard content if no matching page headers are present
    if len(parts) < 2:
        return content

    new_parts = [parts[0]]  # Add initial text preceding any page header
    placeholder_pattern = re.compile(r'\[IMAGE:\s*([^\]]+)\]')
    total_injected = 0

    # Step through regex chunks using a stride of 3
    for i in range(1, len(parts), 3):
        header_text  = parts[i]
        page_num_str = parts[i+1]
        page_body    = parts[i+2]

        page_num  = int(page_num_str)
        page_stem = f"page_{page_num:03d}"
        
        # Isolate layout images assigned to this page
        page_crops = sorted([os.path.basename(p) for p in diagram_map.get(page_stem, [])])
        
        # Build image markdown tags to render at the top
        image_embeds = ""
        if page_crops:
            for filename in page_crops:
                image_embeds += f"![[{filename}]]\n\n"
                total_injected += 1
        
        # Wipe legacy transcription tags from the text body to avoid visual clutter
        cleaned_body = placeholder_pattern.sub("", page_body)

        # Assemble: Header -> Image Embed -> Cleaned Transcription Text
        new_parts.extend([header_text, f"\n\n{image_embeds}{cleaned_body.lstrip()}"])

    print(f"   Injected {total_injected} full page layout image(s) above text blocks.")
    return "".join(new_parts)


def write_to_obsidian(content, course, topic, diagram_map=None):
    """
    Writes the formatted note to the Obsidian vault.
 
    Args:
        content:     formatted markdown string
        course:      course code e.g. "BME3503"
        topic:       topic string e.g. "Membrane Potential"
        diagram_map: optional dict from pdf_to_images()
 
    Returns:
        path to the written .md file
    """
    course_folder = os.path.join(OBSIDIAN_VAULT_PATH, course)
    os.makedirs(course_folder, exist_ok=True)
 
    # Copy diagram images into vault first
    if diagram_map:
        copied = _copy_diagrams_to_vault(diagram_map, course_folder)
        if copied:
            print(f"   Copied {len(copied)} layout image(s) to vault")
            # Replace placeholders using the copied filenames
            content = _inject_diagram_embeds(content, diagram_map)
 
    filename = f"{topic.replace(' ', '_')}_{datetime.now().strftime('%Y-%m-%d')}.md"
    path     = os.path.join(course_folder, filename)
 
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
 
    print(f"✅ Saved to Obsidian: {path}")
    return path