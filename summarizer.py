# summarizer.py
#
# Takes a list of note paths, reads their content, and sends them to Gemini
# with a synthesis prompt. Returns a new .md note written to Obsidian that
# links back to its sources.
#
# Called by: app.py → /summary/generate
# Usage:
#   from summarizer import generate_summary
#   result = generate_summary(note_paths, course, title)
#   # result = { "path": "...", "filename": "...", "content": "..." }

import os
import json
from datetime import datetime
from google import genai
from model_router import get_model, log_usage
from config import OBSIDIAN_VAULT_PATH

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MAX_CHARS_PER_NOTE = 20000   # truncate long notes before sending
MAX_NOTES          = 10     # hard cap on notes per summary call


# ─────────────────────────────────────────────────────────────
# Read note content from disk
# ─────────────────────────────────────────────────────────────

def _read_note(path: str) -> str:
    """Reads a note file and returns its content, truncated if needed."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if len(content) > MAX_CHARS_PER_NOTE:
            content = content[:MAX_CHARS_PER_NOTE] + "\n\n[... truncated ...]"
        return content
    except Exception as e:
        return f"[Could not read note: {e}]"


def _extract_topic(path: str) -> str:
    """Extracts topic from frontmatter, falls back to filename."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read(500)
        if raw.startswith("---"):
            fm_end = raw.find("---", 3)
            if fm_end != -1:
                for line in raw[3:fm_end].splitlines():
                    if line.startswith("topic:"):
                        return line.replace("topic:", "").strip().strip('"')
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0].replace("_", " ")


# ─────────────────────────────────────────────────────────────
# Build the synthesis prompt
# ─────────────────────────────────────────────────────────────

def _build_prompt(notes_data: list[dict], course: str, title: str) -> str:
    sources_block = ""
    for i, note in enumerate(notes_data, 1):
        sources_block += f"\n\n--- SOURCE {i}: {note['topic']} ---\n{note['content']}"

    return f"""You are a biomedical engineering tutor helping a University of Florida student synthesize lecture notes.

You have been given {len(notes_data)} related notes from the course "{course}".
Your job is to write a single synthesis note titled "{title}" that:

1. Identifies the unifying concepts across all source notes
2. Explains how the topics connect and build on each other
3. Highlights key equations, mechanisms, or principles that appear across multiple notes
4. Points out any tensions, nuances, or common misconceptions
5. Ends with a "Connections Map" — a bullet list of how each source note relates to the others

FORMAT RULES:
- Use Obsidian markdown (## headings, bullet points, **bold** for key terms)
- Include a YAML frontmatter block at the top
- Reference source notes as wikilinks: [[Note_Name]]
- Do NOT just summarize each note individually — synthesize them into a unified understanding
- Write for a student who has already read all the notes and wants the bigger picture
- Be concise but complete — aim for 600–900 words of body content


OUTPUT FORMAT (STRICT — MUST FOLLOW)

You must return output in exactly two parts only:

------------------------------------------------------------
1. YAML FRONTMATTER (FIRST SECTION)
------------------------------------------------------------

Must be the very first content in the response.
Must NOT use code fences or backticks.

Format:

---
tags: [...]
date: YYYY-MM-DD
course: ...
topic: "..."
type: ...
---

YAML RULES:
- Only allowed keys: tags, date, course, topic, type
- tags must be a flat list only (e.g. [lecture, BME3053])
- topic must be a quoted string
- No additional fields allowed
- No markdown inside YAML
- No wiki-links [[...]] anywhere

------------------------------------------------------------
2. MARKDOWN BODY (SECOND SECTION)
------------------------------------------------------------

Must begin immediately after closing ---
Must start with a heading (# or ##)
Must be pure markdown only

ALLOWED:
- headings
- bullet points
- equations
- normal text

FORBIDDEN:
- YAML anywhere in body
- code fences (``` ```
- wiki-links [[...]]
- repeating metadata (tags/date/course/topic/type)

------------------------------------------------------------
HARD SEPARATION RULE
------------------------------------------------------------

- YAML = structure only
- Body = content only
- Never mix or repeat metadata in the body
- Output ONLY these two sections, nothing else

FRONTMATTER FORMAT:
---
title: "{title}"
course: "{course}"
type: summary
date: "{datetime.now().strftime('%Y-%m-%d')}"
sources: [{", ".join(f'[[{n["key"]}]]' for n in notes_data)}]
tags: [summary, synthesis]
---

SOURCE NOTES:
{sources_block}

Write the full synthesis note now. Start with the frontmatter block."""


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def generate_summary(note_paths: list[str], course: str, title: str) -> dict:
    """
    Synthesizes multiple notes into a single summary note.

    Args:
        note_paths: list of absolute paths to .md files
        course:     course code string e.g. "BME3503"
        title:      title for the summary note e.g. "Membrane Potential Synthesis"

    Returns:
        {
            "path":     absolute path to the written summary note,
            "filename": just the filename,
            "content":  the full markdown content
        }

    Raises:
        ValueError if note_paths is empty or too long
        RuntimeError if Gemini call fails

OUTPUT FORMAT (STRICT — MUST FOLLOW)

You must return output in exactly two parts only:

------------------------------------------------------------
1. YAML FRONTMATTER (FIRST SECTION)
------------------------------------------------------------

Must be the very first content in the response.
Must NOT use code fences or backticks.

Format:

---
tags: [...]
date: YYYY-MM-DD
course: ...
topic: "..."
type: ...
---

YAML RULES:
- Only allowed keys: tags, date, course, topic, type
- tags must be a flat list only (e.g. [lecture, BME3053])
- topic must be a quoted string
- No additional fields allowed
- No markdown inside YAML
- No wiki-links [[...]] anywhere

------------------------------------------------------------
2. MARKDOWN BODY (SECOND SECTION)
------------------------------------------------------------

Must begin immediately after closing ---
Must start with a heading (# or ##)
Must be pure markdown only

ALLOWED:
- headings
- bullet points
- equations
- normal text

FORBIDDEN:
- YAML anywhere in body
- code fences (``` ```
- wiki-links [[...]]
- repeating metadata (tags/date/course/topic/type)

------------------------------------------------------------
HARD SEPARATION RULE
------------------------------------------------------------

- YAML = structure only
- Body = content only
- Never mix or repeat metadata in the body
- Output ONLY these two sections, nothing else

    """

    print("\n=== SUMMARIZER INPUT PATHS ===")
    for p in note_paths:
        print("RAW:", repr(p))
        print("EXISTS:", os.path.exists(p))

    if not note_paths:
        raise ValueError("No note paths provided.")
    if len(note_paths) > MAX_NOTES:
        raise ValueError(f"Too many notes — max {MAX_NOTES}, got {len(note_paths)}.")

    # Read all notes
    notes_data = []
    for path in note_paths:
        key = os.path.splitext(os.path.basename(path))[0]
        notes_data.append({
            "key":     key,
            "topic":   _extract_topic(path),
            "content": _read_note(path),
            "path":    path,
        })

    print(f"\n  Summarizing {len(notes_data)} notes → '{title}'")


    print("\n=== NOTES BEING SENT TO GEMINI ===")

    for note in notes_data:
        print("\n--------------------------------")
        print("PATH:", note["path"])
        print("TOPIC:", note["topic"])
        print("CONTENT PREVIEW:")
        print(note["content"][:500])

    print("\n===============================\n")

    model  = get_model("summarization")
    prompt = _build_prompt(notes_data, course, title)

    try:
        response = client.models.generate_content(
            model=model,
            contents=[prompt]
        )
        content = response.text.strip()

        total_tokens = response.usage_metadata.total_token_count
        log_usage(model, total_tokens)
        print(f"  Summary generated  [{model}, {total_tokens} tokens]")

    except Exception as e:
        raise RuntimeError(f"Gemini summarization failed: {e}")

    # Write to Obsidian vault under the course folder
    course_folder = os.path.join(OBSIDIAN_VAULT_PATH, course)
    os.makedirs(course_folder, exist_ok=True)

    safe_title = title.replace(" ", "_").replace("/", "-")
    filename   = f"SUMMARY_{safe_title}_{datetime.now().strftime('%Y-%m-%d')}.md"
    out_path   = os.path.join(course_folder, filename)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"  Summary saved → {out_path}")

    return {
        "path":     out_path,
        "filename": filename,
        "content":  content,
    }