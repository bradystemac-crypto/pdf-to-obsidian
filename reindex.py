# reindex.py
# Smart incremental reindexer — runs at end of every pipeline run.
# Only processes notes that are new or have changed since last reindex.
# Updates Linked Notes sections bidirectionally.

import os
import json
import re
from datetime import date, datetime
from google import genai
from config import OBSIDIAN_VAULT_PATH

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MATCHER_MODEL  = "gemini-2.5-flash-lite"
TAG_INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag_index.json")
MAX_LINKS_PER_NOTE = 20   # higher cap for dense graph
BATCH_SIZE = 15           # notes per semantic match call


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
# Read / write Linked Notes section in a .md file
# ─────────────────────────────────────────────────────────────

def get_existing_links(note_path):
    """Returns set of note keys already linked in a note's Linked Notes section"""
    try:
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return set()

    links = set()
    if "## Linked Notes" not in content:
        return links

    start = content.find("## Linked Notes") + len("## Linked Notes")
    # Find next ## heading or end of file
    next_heading = content.find("\n##", start)
    block = content[start:next_heading] if next_heading != -1 else content[start:]

    # Extract all [[wikilinks]]
    for match in re.finditer(r'\[\[([^\]]+)\]\]', block):
        links.add(match.group(1).strip())

    return links


def inject_link_into_note(note_path, new_key):
    """
    Adds [[new_key]] to the Linked Notes section of an existing note.
    Skips if already present or section doesn't exist.
    Returns True if file was modified.
    """
    try:
        with open(note_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return False

    if f"[[{new_key}]]" in content:
        return False  # already linked

    if "## Linked Notes" not in content:
        return False  # no section to inject into

    # Find the Linked Notes block
    marker = "## Linked Notes"
    start = content.find(marker) + len(marker)
    next_heading = content.find("\n##", start)
    block = content[start:next_heading] if next_heading != -1 else content[start:]

    # Don't add if at max links
    existing = re.findall(r'\[\[([^\]]+)\]\]', block)
    if len(existing) >= MAX_LINKS_PER_NOTE:
        return False

    # Replace "None yet" placeholder if present
    if "None yet" in block:
        new_block = block.replace(
            "- None yet — will populate as more notes are added to the vault",
            f"- [[{new_key}]]"
        )
    else:
        # Append to existing links
        # Find last link line and insert after it
        last_link_pos = block.rfind("- [[")
        if last_link_pos == -1:
            new_block = block.rstrip() + f"\n- [[{new_key}]]"
        else:
            end_of_last = block.find("\n", last_link_pos)
            if end_of_last == -1:
                new_block = block + f"\n- [[{new_key}]]"
            else:
                new_block = block[:end_of_last] + f"\n- [[{new_key}]]" + block[end_of_last:]

    if next_heading != -1:
        new_content = content[:start] + new_block + content[next_heading:]
    else:
        new_content = content[:start] + new_block

    try:
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# Semantic batch matcher
# ─────────────────────────────────────────────────────────────

def find_related_notes(source_key, source_themes, source_tags, candidates, index):
    """
    Sends source note themes against a batch of candidate notes.
    Returns list of candidate keys that are genuinely related.
    """
    if not candidates:
        return []

    candidate_list = []
    for key in candidates:
        entry = index.get(key, {})
        candidate_list.append({
            "key": key,
            "topic": entry.get("topic", key),
            "course": entry.get("course", ""),
            "themes": entry.get("themes", []),
            "tags": entry.get("tags", [])[:8]
        })

    prompt = f"""
You are a biomedical engineering knowledge graph assistant.

Identify which of the candidate notes are genuinely conceptually related to the source note.

"Genuinely related" means:
- They share a core scientific principle, mathematical framework, or physiological system
- Understanding one would meaningfully help understand the other
- Cross-course connections count — thermodynamics to metabolism, circuits to membrane biophysics
- Do NOT connect just because they are in the same course or use similar generic vocabulary

SOURCE NOTE:
Themes: {json.dumps(source_themes)}
Tags: {json.dumps(source_tags[:12])}

CANDIDATE NOTES:
{json.dumps(candidate_list, indent=2)}

Return ONLY a JSON array of related note keys, ranked by relevance (most related first).
Maximum {MAX_LINKS_PER_NOTE} results. Empty array [] if nothing is genuinely related.
No preamble, no backticks, no explanation.
"""

    try:
        response = client.models.generate_content(
            model=MATCHER_MODEL,
            contents=[prompt]
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        matched = json.loads(raw.strip())
        return [k for k in matched if isinstance(k, str) and k in index and k != source_key]
    except Exception as e:
        print(f"    Semantic match failed: {e}")
        return []


# ─────────────────────────────────────────────────────────────
# Main reindex function
# ─────────────────────────────────────────────────────────────

def smart_reindex(new_note_key, vault_path):
    """
    Triggered after a new note is written to the vault.
    
    1. Finds all existing notes that should link to the new note
    2. Updates their Linked Notes sections (forward links)
    3. Updates the new note's Linked Notes section with backlinks
    4. Updates timestamps in the index
    
    Only touches files that need updating — no unnecessary writes.
    """
    index = load_index()

    if new_note_key not in index:
        print("  Reindexer: new note not in index yet — skipping")
        return

    new_entry  = index[new_note_key]
    new_themes = new_entry.get("themes", [])
    new_tags   = new_entry.get("tags", [])
    new_path   = new_entry.get("path", "")

    if not new_themes and not new_tags:
        print("  Reindexer: no themes/tags on new note — skipping")
        return

    print(f"\n  Smart reindexer running for '{new_note_key}'...")

    # All other notes in index are candidates
    all_other_keys = [k for k in index.keys() if k != new_note_key]

    if not all_other_keys:
        print("  Reindexer: only one note in vault — nothing to connect yet")
        index[new_note_key]["last_reindexed"] = str(date.today())
        save_index(index)
        return

    # Run semantic matching in batches
    related_keys = []
    for i in range(0, len(all_other_keys), BATCH_SIZE):
        batch = all_other_keys[i:i + BATCH_SIZE]
        batch_related = find_related_notes(
            new_note_key, new_themes, new_tags, batch, index
        )
        related_keys.extend(batch_related)

    # Deduplicate and cap
    seen = set()
    deduped = []
    for k in related_keys:
        if k not in seen:
            seen.add(k)
            deduped.append(k)
    related_keys = deduped[:MAX_LINKS_PER_NOTE]

    print(f"  Found {len(related_keys)} related note(s) for bidirectional linking")

    forward_updates = 0
    back_updates = 0

    for related_key in related_keys:
        related_entry = index.get(related_key, {})
        related_path  = related_entry.get("path", "")

        if not related_path or not os.path.exists(related_path):
            continue

        # Forward: inject new note link into existing related note
        if inject_link_into_note(related_path, new_note_key):
            forward_updates += 1
            print(f"    → Added [[{new_note_key}]] to '{related_key}'")

        # Back: inject related note link into new note
        if new_path and os.path.exists(new_path):
            if inject_link_into_note(new_path, related_key):
                back_updates += 1
                print(f"    ← Added [[{related_key}]] to new note")

    # Update timestamps
    index[new_note_key]["last_reindexed"] = str(date.today())
    for key in related_keys:
        if key in index:
            index[key]["last_reindexed"] = str(date.today())

    save_index(index)
    print(f"  Reindex complete — {forward_updates} forward links, {back_updates} back links written")


# ─────────────────────────────────────────────────────────────
# Full vault reindex (run manually when you want a full refresh)
# ─────────────────────────────────────────────────────────────

def full_reindex(vault_path):
    """
    Re-runs semantic matching for EVERY note in the index against every other.
    Run this manually when you want to refresh all connections across the vault.
    Call: python reindex.py
    """
    index = load_index()

    if len(index) < 2:
        print("Need at least 2 indexed notes to find connections.")
        return

    print(f"\nFull reindex — {len(index)} notes\n")
    all_keys = list(index.keys())
    total_updates = 0

    for i, source_key in enumerate(all_keys):
        print(f"  [{i+1}/{len(all_keys)}] {source_key}")
        source_entry  = index[source_key]
        source_themes = source_entry.get("themes", [])
        source_tags   = source_entry.get("tags", [])
        source_path   = source_entry.get("path", "")

        if not source_themes and not source_tags:
            print("    No themes/tags — skipping")
            continue

        if not source_path or not os.path.exists(source_path):
            print("    File not found — skipping")
            continue

        candidates = [k for k in all_keys if k != source_key]
        related_keys = []

        for j in range(0, len(candidates), BATCH_SIZE):
            batch = candidates[j:j + BATCH_SIZE]
            batch_related = find_related_notes(
                source_key, source_themes, source_tags, batch, index
            )
            related_keys.extend(batch_related)

        # Deduplicate
        seen = set()
        deduped = []
        for k in related_keys:
            if k not in seen:
                seen.add(k)
                deduped.append(k)
        related_keys = deduped[:MAX_LINKS_PER_NOTE]

        for related_key in related_keys:
            related_path = index.get(related_key, {}).get("path", "")
            if not related_path or not os.path.exists(related_path):
                continue
            if inject_link_into_note(source_path, related_key):
                total_updates += 1
            if inject_link_into_note(related_path, source_key):
                total_updates += 1

        index[source_key]["last_reindexed"] = str(date.today())

    save_index(index)
    print(f"\nFull reindex complete — {total_updates} total link updates written to vault")


if __name__ == "__main__":
    print("Reindexer\n")
    print("1. Full vault reindex (refreshes ALL connections)")
    choice = input("\nChoice [1]: ").strip()
    if choice == "1" or choice == "":
        full_reindex(OBSIDIAN_VAULT_PATH)