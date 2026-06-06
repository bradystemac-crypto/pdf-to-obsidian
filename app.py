# app.py

import os
import sys
import json
import time
import queue
import threading
import tempfile
from datetime import date, datetime
from flask import Flask, request, jsonify, send_file, Response, render_template
from matplotlib.pylab import rint
from exam_routes import exam_bp
from config import OBSIDIAN_VAULT_PATH
from flashcards import FlashcardEngine

app = Flask(__name__)

app.register_blueprint(exam_bp)

# Initialize Flashcard Engine
fc_engine = FlashcardEngine()

# Thread-safe queue for streaming progress updates
progress_queues = {}

def stream_progress(job_id, message, stage=None, done=False, error=False, download_url=None, stats=None):
    """Push a progress event into the job's queue"""
    if job_id not in progress_queues:
        return
    progress_queues[job_id].put({
        "message": message,
        "stage": stage,
        "done": done,
        "error": error,
        "download_url": download_url,
        "stats": stats
    })


def run_pipeline_threaded(job_id, pdf_path, course, topic, output_path):
    """Runs the full pipeline in a background thread, pushing progress updates"""
    try:
        # --- Import pipeline modules ---
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from pdf_to_images import pdf_to_images
        from transcribe import transcribe_images, PRIMARY_MODEL, FALLBACK_MODEL
        from format_notes import format_notes
        from cache import get_cached_transcription, save_transcription_to_cache
        from connections import find_connections, inject_connections, register_note_tags
        from obsidian_writer import write_to_obsidian
        from tracker import register_note
        from config import OBSIDIAN_VAULT_PATH, OUTPUT_DIR

        stats = {
            "model": PRIMARY_MODEL,
            "fallback_model": FALLBACK_MODEL,
            "total_tokens": 0,
            "cached": False,
            "pages": 0,
            "connections": 0
        }

        # --- Stage 1: PDF to Images ---
        stream_progress(job_id, "Converting PDF to images...", stage=1)
        images, diagram_map = pdf_to_images(pdf_path)
        stats["pages"] = len(images)
        stream_progress(job_id, f"Converted {len(images)} pages", stage=1)
        time.sleep(0.3)

        # --- Stage 2: Transcription ---
        stream_progress(job_id, "Checking transcription cache...", stage=2)
        transcriptions = get_cached_transcription(pdf_path)

        if transcriptions is not None:
            stats["cached"] = True
            stream_progress(job_id, "Cache hit — skipping Gemini transcription", stage=2)
        else:
            stream_progress(job_id, f"Transcribing with {PRIMARY_MODEL}...", stage=2)
            transcriptions, usage_log = transcribe_images(images, sleep_between_calls=2.0, max_retries=5)
            save_transcription_to_cache(pdf_path, transcriptions)

            total_tokens = sum(u.get("total_tokens", 0) or 0 for u in usage_log)
            stats["total_tokens"] += total_tokens
            model_used = usage_log[0].get("model_used", PRIMARY_MODEL) if usage_log else PRIMARY_MODEL
            stats["model"] = model_used
            stream_progress(job_id, f"Transcription complete — {total_tokens:,} tokens used", stage=2)

        time.sleep(0.3)

        # --- Stage 3: Formatting ---
        stream_progress(job_id, "Formatting notes into Obsidian template...", stage=3)
        formatted = format_notes(transcriptions, course, topic)
        stream_progress(job_id, "Formatting complete", stage=3)
        time.sleep(0.3)

        # --- Stage 4: Connections ---
        stream_progress(job_id, "Scanning tag index for connections...", stage=4)
        wikilinks, new_tags, new_themes = find_connections(formatted, OBSIDIAN_VAULT_PATH, course=course, topic=topic)
        if wikilinks:
            formatted = inject_connections(formatted, wikilinks, new_tags, new_themes)
            stats["connections"] = len(wikilinks)
            stream_progress(job_id, f"Found {len(wikilinks)} connection(s) via tag overlap", stage=4)
        else:
            stream_progress(job_id, "No connections yet — tags saved for future notes", stage=4)
        time.sleep(0.3)

        # --- Stage 5: Write to Obsidian + save download copy ---
        stream_progress(job_id, "Writing to Obsidian vault...", stage=5)
        note_path = write_to_obsidian(formatted, course, topic, diagram_map=diagram_map)

        # Register tags in index after note is saved
        if new_tags or new_themes:
            register_note_tags(note_path, new_tags, new_themes, course, topic)

        # Also save to output_path for browser download
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(formatted)

        stream_progress(job_id, "Saved to Obsidian vault", stage=5)
        time.sleep(0.3)

        # --- Stage 6: Tracker ---
        stream_progress(job_id, "Registering in spaced repetition tracker...", stage=6)
        register_note(note_path)
        stream_progress(job_id, "Registered in tracker", stage=6)

        # --- Done ---
        stream_progress(
            job_id,
            "Pipeline complete",
            stage=6,
            done=True,
            download_url=f"/download/{job_id}",
            stats=stats
        )

    except Exception as e:
        stream_progress(job_id, f"Error: {str(e)}", error=True, done=True)
    finally:
        # Clean up the uploaded PDF
        try:
            os.remove(pdf_path)
        except Exception:
            pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    """Receives the uploaded PDF and form inputs, starts pipeline thread"""
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF uploaded"}), 400

    pdf_file = request.files["pdf"]
    course = request.form.get("course", "").strip()
    topic = request.form.get("topic", "").strip()

    if not course or not topic:
        return jsonify({"error": "Course and topic are required"}), 400

    # Save uploaded PDF to a temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf_file.save(tmp.name)
    tmp.close()

    # Create output path for the .md file
    job_id = f"{int(time.time() * 1000)}"
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_outputs")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{job_id}.md")

    # Set up progress queue for this job
    progress_queues[job_id] = queue.Queue()

    # Start pipeline in background thread
    thread = threading.Thread(
        target=run_pipeline_threaded,
        args=(job_id, tmp.name, course, topic, output_path),
        daemon=True
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>")
def progress(job_id):
    """Server-Sent Events stream for live progress updates"""
    def generate():
        if job_id not in progress_queues:
            yield f"data: {json.dumps({'error': 'Job not found', 'done': True})}\n\n"
            return

        while True:
            try:
                event = progress_queues[job_id].get(timeout=60)
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("done"):
                    # Clean up queue after job is done
                    del progress_queues[job_id]
                    break
            except queue.Empty:
                # Send keepalive ping
                yield f"data: {json.dumps({'message': 'waiting...'})}\n\n"

    return Response(generate(), mimetype="text/event-stream")


@app.route("/download/<job_id>")
def download(job_id):
    """Serves the finished .md file for download"""
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flask_outputs")
    output_path = os.path.join(output_dir, f"{job_id}.md")

    if not os.path.exists(output_path):
        return "File not found", 404

    return send_file(output_path, as_attachment=True, download_name="notes.md")


@app.route("/review")
def review():
    """Returns all notes due for review as JSON"""
    from tracker import get_due_notes
    due = get_due_notes()
    return jsonify(due)


@app.route("/review/mark", methods=["POST"])
def review_mark():
    """Marks a note as reviewed and returns the updated entry"""
    from tracker import mark_reviewed, load_tracker
    data = request.get_json()
    note_name = data.get("note_name", "").strip()
    if not note_name:
        return jsonify({"error": "note_name required"}), 400
    mark_reviewed(note_name)
    tracker = load_tracker()
    entry = tracker.get(note_name, {})
    return jsonify({
        "success": True,
        "note_name": note_name,
        "next_review": entry.get("next_review"),
        "review_stage": entry.get("review_stage"),
        "last_reviewed": entry.get("last_reviewed")
    })


@app.route("/review/all")
def review_all():
    """Returns all tracked notes regardless of due date"""
    from tracker import load_tracker
    from datetime import date
    tracker = load_tracker()
    today = date.today()
    result = []
    for name, entry in tracker.items():
        review_date = date.fromisoformat(entry["next_review"])
        result.append({
            "name": name,
            "path": entry.get("path", ""),
            "created": entry.get("created", ""),
            "next_review": entry.get("next_review", ""),
            "last_reviewed": entry.get("last_reviewed", ""),
            "review_stage": entry.get("review_stage", 0),
            "days_until": (review_date - today).days
        })
    result.sort(key=lambda x: x["days_until"])
    return jsonify(result)


@app.route("/vault")
def vault():
    """Scans Obsidian vault and returns structured course/note data"""
    from config import OBSIDIAN_VAULT_PATH
    from tracker import load_tracker
    import os
    from datetime import date

    tracker = load_tracker()
    today = date.today()
    courses = {}

    for root, dirs, files in os.walk(OBSIDIAN_VAULT_PATH):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for file in files:
            if not file.endswith(".md"):
                continue

            course = os.path.basename(root)
            if course == os.path.basename(OBSIDIAN_VAULT_PATH):
                course = "Uncategorized"

            full_path = os.path.join(root, file)
            full_path = os.path.normpath(os.path.abspath(full_path))  # normalize FIRST
            
            # ✅ MUST define modified BEFORE using it
            modified = date.fromtimestamp(os.path.getmtime(full_path))
            days_ago = (today - modified).days

            topic = ""
            tags = []
            note_type = ""
            questions = 0
            connections = 0

            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    raw = f.read()

                questions = raw.count("- [ ]")
                connections = raw.count("[[")

                if raw.startswith("---"):
                    fm_end = raw.find("---", 3)
                    if fm_end != -1:
                        fm = raw[3:fm_end]
                        for line in fm.splitlines():
                            if line.startswith("topic:"):
                                topic = line.replace("topic:", "").strip().strip('"')
                            if line.startswith("tags:"):
                                tags = line.replace("tags:", "").strip().strip("[]").split(",")
                                tags = [t.strip() for t in tags]
                            if line.startswith("type:"):
                                note_type = line.replace("type:", "").strip().strip('"')
            except Exception:
                pass

            note_key = os.path.splitext(file)[0]
            tracker_entry = tracker.get(file, tracker.get(note_key, {}))
            review_stage = tracker_entry.get("review_stage", None)
            next_review = tracker_entry.get("next_review", None)

            if next_review:
                try:
                    nr = date.fromisoformat(next_review)
                    days_until_review = (nr - today).days
                except Exception:
                    days_until_review = None
            else:
                days_until_review = None

            if course not in courses:
                courses[course] = []

            courses[course].append({
                "name": note_key,
                "path": full_path,  # ✅ REQUIRED FIX
                "topic": topic or note_key.replace("_", " "),
                "modified": str(modified),
                "days_ago": days_ago,
                "questions": questions,
                "connections": connections,
                "tags": tags,
                "type": note_type,
                "review_stage": review_stage,
                "next_review": next_review,
                "days_until_review": days_until_review
            })

    # Sort notes within each course by most recently modified
    for course in courses:
        courses[course].sort(key=lambda x: x["modified"], reverse=True)

    total_notes = sum(len(n) for n in courses.values())
    total_questions = sum(note["questions"] for notes in courses.values() for note in notes)
    total_connections = sum(note["connections"] for notes in courses.values() for note in notes)

    return jsonify({
        "courses": courses,
        "stats": {
            "total_notes": total_notes,
            "total_courses": len(courses),
            "total_questions": total_questions,
            "total_connections": total_connections
        }
    })


@app.route("/summary/generate", methods=["POST"])
def summary_generate():
    """
    Receives a list of note paths + metadata, runs summarizer,
    returns the summary content and path as JSON.

    Expected JSON body:
    {
        "note_paths": ["/abs/path/to/note1.md", ...],
        "course":     "BME3503",
        "title":      "Membrane Potential Synthesis"
    }
    """
    from summarizer import generate_summary

    data       = request.get_json()
    note_paths = data.get("note_paths", [])
    course     = data.get("course", "").strip()
    title      = data.get("title", "").strip()

    print("\n=== NOTE PATHS RECEIVED BY FLASK ===")
    for p in note_paths:
        print(repr(p))

    if not note_paths:
        return jsonify({"error": "No notes selected."}), 400
    if not course:
        return jsonify({"error": "Course is required."}), 400
    if not title:
        return jsonify({"error": "Summary title is required."}), 400

    try:
        result = generate_summary(note_paths, course, title)
        return jsonify({
            "success":  True,
            "path":     result["path"],
            "filename": result["filename"],
            "preview":  result["content"][:600] + ("..." if len(result["content"]) > 600 else "")
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


# ── Flashcard System API Endpoints ──────────────────────────────────────────

@app.route('/api/vault/files', methods=['GET'])
def list_vault_files():
    """Scans Obsidian vault and yields clean file profiles for the checklist."""
    try:
        vault_files = []
        for root, dirs, files in os.walk(OBSIDIAN_VAULT_PATH):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for file in files:
                if file.endswith('.md'):
                    full_path = os.path.normpath(os.path.abspath(os.path.join(root, file)))
                    rel_path = os.path.relpath(full_path, OBSIDIAN_VAULT_PATH)
                    display_name = rel_path.replace('.md', '').replace('\\', ' / ')
                    
                    vault_files.append({
                        "path": full_path,
                        "name": display_name
                    })
        return jsonify({"success": True, "files": sorted(vault_files, key=lambda x: x['name'])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/flashcards/generate", methods=["POST"])
def flashcards_generate():
    """Reads target notes, merges text blocks, and prompts Gemini for processing."""
    data = request.get_json() or {}
    note_paths = data.get("note_paths", [])
    difficulty = data.get("difficulty", "medium")
    count = int(data.get("count", 10))

    if not note_paths:
        return jsonify({"error": "No source notes selected for generation."}), 400

    combined_content = ""
    for path in note_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    combined_content += f.read() + "\n\n"
            except Exception as e:
                print(f"Skipping unreadable file path {path}: {e}")

    if not combined_content.strip():
        return jsonify({"error": "Selected files contain no extraction source data."}), 400

    try:
        cards = fc_engine.generate_deck_from_notes(combined_content, difficulty=difficulty, count=count)
        return jsonify({"success": True, "cards": cards})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/flashcards/review", methods=["POST"])
def flashcards_review():
    """Processes user response quality scores (0-5) and commits SM-2 updates."""
    data = request.get_json() or {}
    card_id = data.get("card_id")
    score = data.get("score")

    if card_id is None or score is None:
        return jsonify({"error": "Missing card_id or score parameters."}), 400

    try:
        updated_metadata = fc_engine.update_card_review(str(card_id), int(score))
        return jsonify({"success": True, "metadata": updated_metadata})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)