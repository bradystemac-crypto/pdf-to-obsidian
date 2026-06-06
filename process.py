# process.py

import os
import time
from google import genai
from datetime import date

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.0-flash"

TRANSCRIBE_PROMPT = """
You are a highly accurate note transcription assistant. You are given multiple images of academic note pages exported from OneNote. Each page may contain:
- PowerPoint slide content (typed text, diagrams, images)
- Handwritten annotations in multiple ink colors
- Mathematical equations
- Diagrams or figures

Transcribe ALL pages in order. For each page use this exact format:

--- PAGE 1 ---
[full transcription of page 1]

--- PAGE 2 ---
[full transcription of page 2]

...and so on for every page.

Rules:
1. SLIDE CONTENT: Extract all typed text exactly as written
2. HANDWRITTEN NOTES: Transcribe all handwriting. Label ink color in brackets like [red], [blue] only when color changes
3. EQUATIONS: Convert all equations to LaTeX. Use $$ for display equations, $ for inline
4. DIAGRAMS: Describe any diagram as [IMAGE: description]
5. Do not summarize or add commentary. Return only the raw transcribed content.
"""

def build_format_prompt(course, topic):
    today = date.today().strftime("%Y-%m-%d")
    return f"""
You are an academic note formatter for a biomedical engineering student at the University of Florida.

You will receive raw transcribed content from lecture note pages. Organize everything into this exact Obsidian markdown template:

---
tags: [lecture, {course}]
date: {today}
course: {course}
topic: "{topic}"
---

# 📌 Key Concepts
- Bullet point summary of the main ideas

# 📐 Equations
All equations in LaTeX. Use $$ for display equations. Write "None." if no equations.

# 🖊️ My Annotations
Bullet points of all handwritten content, cleaned up. Preserve color labels like [red] or [blue].

# 🖼️ Slide Content
Transcribed typed text from slides, organized logically.

# 🔗 Connections
- [ ] Add connections

# ❓ Questions / Gaps
Bullet points of anything incomplete, unclear, or worth following up on.

Rules:
- Use proper markdown
- Convert all equations to LaTeX
- Do not invent content that was not in the notes
- Return only the formatted markdown, nothing else
"""

def call_gemini(model, contents, max_retries=5):
    """Calls a Gemini model with retry logic"""
    attempt = 0
    while attempt < max_retries:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents
            )
            return response
        except Exception as e:
            if "429" in str(e):
                attempt += 1
                wait = min(2 ** attempt, 60)
                print(f"    [{model}] Rate limited. Waiting {wait}s... (attempt {attempt}/{max_retries})")
                time.sleep(wait)
            else:
                print(f"    [{model}] Error: {e}")
                return None
    return None

def process_pdf(images, course, topic):
    """
    Two calls:
    - Call 1: images → raw transcription (simple prompt, accurate reading)
    - Call 2: raw text → formatted Obsidian note (no images, clean formatting)
    """

    # --- Call 1: Transcription ---
    print(f"  Transcribing with {PRIMARY_MODEL}...")
    transcribe_contents = [TRANSCRIBE_PROMPT] + images
    response = call_gemini(PRIMARY_MODEL, transcribe_contents)

    if response is None:
        print(f"  ⚠️ {PRIMARY_MODEL} failed. Trying {FALLBACK_MODEL}...")
        response = call_gemini(FALLBACK_MODEL, transcribe_contents)

    if response is None:
        raise RuntimeError("Transcription failed. Check your API quota.")

    raw_transcription = response.text
    transcription_tokens = getattr(response.usage_metadata, "total_token_count", 0)
    print(f"  ✅ Transcription done — {transcription_tokens} tokens")

    # --- Call 2: Formatting (text only, no images) ---
    print(f"  Formatting with {PRIMARY_MODEL}...")
    format_prompt = build_format_prompt(course, topic)
    format_contents = [format_prompt, raw_transcription]
    response2 = call_gemini(PRIMARY_MODEL, format_contents)

    if response2 is None:
        print(f"  ⚠️ {PRIMARY_MODEL} failed. Trying {FALLBACK_MODEL}...")
        response2 = call_gemini(FALLBACK_MODEL, format_contents)

    if response2 is None:
        raise RuntimeError("Formatting failed. Check your API quota.")

    formatting_tokens = getattr(response2.usage_metadata, "total_token_count", 0)
    print(f"  ✅ Formatting done — {formatting_tokens} tokens")

    total_tokens = transcription_tokens + formatting_tokens

    usage_log = [{
        "model_used": PRIMARY_MODEL,
        "total_tokens": total_tokens
    }]

    return response2.text, usage_log


# Test directly
if __name__ == "__main__":
    from pdf_to_images import pdf_to_images

    test_pdf = input("Enter path to a test PDF: ").strip().strip('"')
    course = input("Course: ").strip()
    topic = input("Topic: ").strip()

    images = pdf_to_images(test_pdf)
    result, usage_log = process_pdf(images, course, topic)

    print("\n--- OUTPUT ---\n")
    print(result)