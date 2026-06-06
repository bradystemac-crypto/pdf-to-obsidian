# connections.py

import os
import json
from datetime import date
from google import genai
from config import OBSIDIAN_VAULT_PATH
from model_router import get_model, log_usage

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

TAG_INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag_index.json")

MAX_CONNECTIONS  = 8   # max wikilinks injected per note
TAG_COUNT        = 25  # tags to generate per note
THEME_COUNT      = 6   # themes to generate per note
MIN_CANDIDATES   = 3   # min candidates to pass to semantic matcher


# ─────────────────────────────────────────────────────────────
# Index I/O
# ─────────────────────────────────────────────────────────────

def load_index():
    if not os.path.exists(TAG_INDEX_PATH):
        return {}
    with open(TAG_INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_index(index):
    with open(TAG_INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)


# ─────────────────────────────────────────────────────────────
# Vault bootstrap — read existing notes into index on startup
# ─────────────────────────────────────────────────────────────

def bootstrap_vault_index(vault_path):
    """
    Scans the vault for any .md files that have themes/tags
    already written in their Connections section.
    Adds them to the index if not already present.
    """
    index = load_index()
    added = 0

    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file in files:
            if not file.endswith(".md"):
                continue

            note_key = os.path.splitext(file)[0]
            if note_key in index:
                continue

            full_path = os.path.join(root, file)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    raw = f.read()
            except Exception:
                continue

            tags = []
            topic = ""
            course = ""
            if raw.startswith("---"):
                fm_end = raw.find("---", 3)
                if fm_end != -1:
                    fm = raw[3:fm_end]
                    for line in fm.splitlines():
                        if line.startswith("topic:"):
                            topic = line.replace("topic:", "").strip().strip('"')
                        if line.startswith("course:"):
                            course = line.replace("course:", "").strip().strip('"')
                        if line.startswith("tags:"):
                            raw_tags = line.replace("tags:", "").strip().strip("[]")
                            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

            themes = []
            if "## Themes" in raw:
                start = raw.find("## Themes") + len("## Themes")
                end = raw.find("##", start)
                block = raw[start:end] if end != -1 else raw[start:]
                for line in block.splitlines():
                    line = line.strip().lstrip("- ").strip()
                    if line:
                        themes.append(line)

            if tags or themes:
                index[note_key] = {
                    "tags": tags,
                    "themes": themes,
                    "course": course,
                    "topic": topic or note_key.replace("_", " "),
                    "path": full_path,
                    "date": str(date.fromtimestamp(os.path.getmtime(full_path)))
                }
                added += 1

    if added > 0:
        save_index(index)
        print(f"  Bootstrapped {added} existing note(s) into tag index")

    return index


# ─────────────────────────────────────────────────────────────
# Layer 1 — Generate tags + themes (Claude)
# ─────────────────────────────────────────────────────────────

def generate_tags_and_themes(formatted_note, course, topic):
    """
    Sends the formatted note to Claude (via model_router).
    Returns (tags, themes) — both lists of strings.
    """
    model = get_model("tagging")

    prompt = f"""You are a biomedical engineering knowledge graph assistant for a University of Florida student.

Analyze the note content below and return a JSON object with two fields:

1. "tags": exactly {TAG_COUNT} specific concept tags
   - Lowercase, hyphenated: "nernst-equation", "goldman-equation", "hodgkin-huxley-model"
   - Be maximally specific — prefer "nernst-equilibrium-potential" over "potential"
   - Cover: biological concepts, physical principles, mathematical tools, named equations,
     key variables, physiological systems, engineering principles
   - Do NOT include: course codes, professor names, generic words like "lecture" or "notes"

2. "themes": exactly {THEME_COUNT} conceptual themes written as short phrases (3-8 words)
   - These are the big ideas the note is fundamentally about
   - Written as named concepts, not sentences: "Nernst equilibrium potential derivation",
     "Membrane capacitance as RC circuit analogy", "Ion selectivity and electrochemical driving force"
   - These should be specific enough that another note on the same concept would share them

Return ONLY a valid JSON object. No preamble, no backticks, no explanation.

Example:
{{
  "tags": ["nernst-equation", "membrane-potential", "ion-channels", "electrochemical-gradient", "goldman-equation", "potassium-permeability", "sodium-permeability", "resting-potential", "action-potential", "depolarization", "hodgkin-huxley", "voltage-gated-channels", "selectivity-filter", "equilibrium-potential", "concentration-gradient", "faraday-constant", "boltzmann-constant", "ohms-law", "kirchhoffs-law", "capacitance", "resistance", "conductance", "current-density", "diffusion-coefficient", "fick-law"],
  "themes": ["Nernst equilibrium potential derivation", "Goldman equation multi-ion transport", "Membrane capacitance RC circuit analogy", "Voltage-gated ion channel selectivity", "Electrochemical driving force and current", "Hodgkin-Huxley conductance model"]
}}

Course: {course}
Topic: {topic}

--- NOTE CONTENT ---
{formatted_note[:5000]}"""

    try:
        response = client.models.generate_content(
            model=model,
            contents=[prompt]
        )
        raw = response.text.strip()

        total_tokens = response.usage_metadata.total_token_count
        log_usage(model, total_tokens)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        tags   = [t.lower().replace(" ", "-") for t in result.get("tags", []) if isinstance(t, str)]
        themes = [t.strip() for t in result.get("themes", []) if isinstance(t, str)]
        print(f"  Generated {len(tags)} tags, {len(themes)} themes  [{model}, {total_tokens} tokens]")
        return tags, themes

    except Exception as e:
        print(f"  Tag/theme generation failed: {e}")
        return [], []


# ─────────────────────────────────────────────────────────────
# Layer 2 — Semantic matching (Claude)
# ─────────────────────────────────────────────────────────────

def semantic_match(new_themes, new_tags, index):
    """
    Sends the new note's themes + all indexed notes' themes to Claude.
    Returns list of note_keys that are genuinely related.
    """
    if not index:
        return []

    model = get_model("matching")

    candidates = []
    for note_key, entry in index.items():
        candidates.append({
            "key": note_key,
            "topic": entry.get("topic", note_key),
            "course": entry.get("course", ""),
            "themes": entry.get("themes", []),
            "tags": entry.get("tags", [])[:10]
        })

    if not candidates:
        return []

    candidates_text = json.dumps(candidates, indent=2)

    prompt = f"""You are a biomedical engineering knowledge graph assistant.

A student just processed a new note. Your job is to identify which existing notes
in their vault are genuinely conceptually related to the new note.

"Genuinely related" means:
- They share a core scientific principle, mathematical framework, or physiological system
- Understanding one note would meaningfully help understand the other
- They could be studied together for a more complete understanding of a topic
- Cross-course connections count — e.g. thermodynamics ↔ metabolism, circuits ↔ membrane biophysics

Do NOT connect notes just because they are in the same course or use similar vocabulary.
Only return notes where the conceptual connection is real and non-trivial.

NEW NOTE:
Themes: {json.dumps(new_themes)}
Tags: {json.dumps(new_tags[:15])}

EXISTING NOTES:
{candidates_text}

Return ONLY a JSON array of note keys (strings) that are genuinely related.
Maximum {MAX_CONNECTIONS} results, ranked by relevance (most related first).
If nothing is genuinely related, return an empty array [].
No preamble, no explanation, no backticks.

Example: ["Membrane_Potential_2026-01-15", "RC_Circuits_2026-02-03"]"""

    try:
        response = client.models.generate_content(
            model=model,
            contents=[prompt]
        )
        raw = response.text.strip()

        total_tokens = response.usage_metadata.total_token_count
        log_usage(model, total_tokens)

        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        matched_keys = json.loads(raw.strip())
        matched_keys = [k for k in matched_keys if isinstance(k, str) and k in index]
        print(f"  Semantic matcher found {len(matched_keys)} connection(s)  [{model}, {total_tokens} tokens]")
        return matched_keys

    except Exception as e:
        print(f"  Semantic matching failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────

def find_connections(formatted_note, vault_path, course=None, topic=None):
    """
    Called by main.py and app.py.
    Returns (wikilinks, tags, themes).
    """
    index = bootstrap_vault_index(vault_path)

    tags, themes = generate_tags_and_themes(
        formatted_note, course or "", topic or ""
    )

    if not tags and not themes:
        return [], [], []

    matched_keys = []
    if index:
        matched_keys = semantic_match(themes, tags, index)

    wikilinks = [f"[[{k}]]" for k in matched_keys]

    return wikilinks, tags, themes


# ─────────────────────────────────────────────────────────────
# Save note to index after write
# ─────────────────────────────────────────────────────────────

def register_note_tags(note_path, tags, themes, course, topic):
    """
    Saves the note's tags and themes into tag_index.json.
    Called by main.py after the note is written to Obsidian.
    """
    index = load_index()
    note_key = os.path.splitext(os.path.basename(note_path))[0]

    index[note_key] = {
        "tags": tags,
        "themes": themes,
        "course": course,
        "topic": topic,
        "path": note_path,
        "date": str(date.today())
    }

    save_index(index)
    print(f"  Saved {len(tags)} tags + {len(themes)} themes to index for '{note_key}'")


# ─────────────────────────────────────────────────────────────
# Inject into note — connections section
# ─────────────────────────────────────────────────────────────

def inject_connections(formatted_note, wikilinks, tags, themes):
    """
    Replaces the placeholder connections section with:
    - Themes, Tags, Linked Notes
    """
    themes_block = "\n".join(f"- {t}" for t in themes) if themes else "- None identified yet"
    tags_block   = ", ".join(tags) if tags else "None"

    if wikilinks:
        links_block = "\n".join(f"- {w}" for w in wikilinks)
    else:
        links_block = "- None yet — will populate as more notes are added to the vault"

    connections_section = f"""## Themes
{themes_block}

## Tags
{tags_block}

## Linked Notes
{links_block}"""

    return formatted_note.replace("- [ ] Add connections", connections_section)


# ─────────────────────────────────────────────────────────────
# Debug utility
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    index = load_index()
    if not index:
        print("Tag index is empty. Run the pipeline on some notes first.")
    else:
        print(f"Tag index — {len(index)} notes indexed:\n")
        for key, entry in index.items():
            print(f"  {key}")
            print(f"    Course : {entry.get('course')}")
            print(f"    Topic  : {entry.get('topic')}")
            print(f"    Date   : {entry.get('date')}")
            print(f"    Themes : {'; '.join(entry.get('themes', []))}")
            print(f"    Tags   : {', '.join(entry.get('tags', [])[:8])}...\n")