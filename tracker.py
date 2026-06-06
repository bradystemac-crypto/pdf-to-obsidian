# tracker.py

import os
import json
from datetime import date, timedelta
from config import OBSIDIAN_VAULT_PATH

TRACKER_FILE = "review_tracker.json"

# Spaced repetition intervals in days
INTERVALS = [1, 3, 7, 14, 30, 60]

def load_tracker():
    if not os.path.exists(TRACKER_FILE):
        return {}
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tracker(tracker):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(tracker, f, indent=2)

def register_note(note_path):
    """
    Registers a new note in the tracker the first time it's created.
    Sets first review due for tomorrow.
    """
    tracker = load_tracker()
    key = os.path.basename(note_path)

    if key not in tracker:
        tracker[key] = {
            "path": note_path,
            "created": str(date.today()),
            "review_stage": 0,
            "next_review": str(date.today() + timedelta(days=INTERVALS[0]))
        }
        save_tracker(tracker)
        print(f"  📅 Review scheduled: {key} → due {tracker[key]['next_review']}")

def mark_reviewed(note_name):
    """
    Call this after you review a note.
    Advances the note to the next spaced repetition interval.
    """
    tracker = load_tracker()

    if note_name not in tracker:
        print(f"  Note '{note_name}' not found in tracker.")
        return

    entry = tracker[note_name]
    stage = entry["review_stage"]

    if stage + 1 < len(INTERVALS):
        next_stage = stage + 1
    else:
        next_stage = stage  # stay at max interval (60 days)

    next_date = date.today() + timedelta(days=INTERVALS[next_stage])
    tracker[note_name]["review_stage"] = next_stage
    tracker[note_name]["next_review"] = str(next_date)
    tracker[note_name]["last_reviewed"] = str(date.today())

    save_tracker(tracker)
    print(f"  ✅ Marked reviewed. Next review: {next_date} (stage {next_stage + 1}/{len(INTERVALS)})")

def get_due_notes():
    """Returns all notes due for review today or overdue"""
    tracker = load_tracker()
    today = date.today()
    due = []

    for name, entry in tracker.items():
        review_date = date.fromisoformat(entry["next_review"])
        if review_date <= today:
            days_overdue = (today - review_date).days
            due.append({
                "name": name,
                "path": entry["path"],
                "due": entry["next_review"],
                "days_overdue": days_overdue,
                "stage": entry["review_stage"]
            })

    # Sort by most overdue first
    due.sort(key=lambda x: x["days_overdue"], reverse=True)
    return due

def show_due_notes():
    """Prints all notes due for review"""
    due = get_due_notes()

    if not due:
        print("\n✅ No notes due for review today!")
        return

    print(f"\n📚 {len(due)} note(s) due for review:\n")
    for note in due:
        overdue_str = f" ({note['days_overdue']}d overdue)" if note['days_overdue'] > 0 else " (due today)"
        stage_str = f"Stage {note['stage'] + 1}/{len(INTERVALS)}"
        print(f"  [{stage_str}] {note['name']}{overdue_str}")

if __name__ == "__main__":
    print("Spaced Repetition Tracker\n")
    print("1. Show due notes")
    print("2. Mark a note as reviewed")
    choice = input("\nChoice: ").strip()

    if choice == "1":
        show_due_notes()
    elif choice == "2":
        show_due_notes()
        name = input("\nEnter exact note name to mark reviewed: ").strip()
        mark_reviewed(name)