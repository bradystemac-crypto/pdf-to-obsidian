from flask import Blueprint, request, jsonify
from exam_gen import generate_exam

exam_bp = Blueprint("exam", __name__)


@exam_bp.route("/exam/generate", methods=["POST"])
def generate():
    """
    POST /exam/generate
    Body (JSON):
    {
        "note_paths": ["/abs/path/to/note.md", ...],
        "count":      10,
        "difficulty": "easy" | "medium" | "hard",
        "q_type":     "single" | "multiple"
    }

    Returns:
    {
        "questions": [ ...question objects... ],
        "meta": {
            "count":      <int>,
            "difficulty": <str>,
            "q_type":     <str>,
            "note_count": <int>
        }
    }
    """
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON."}), 400

    note_paths = data.get("note_paths", [])
    count      = data.get("count", 10)
    difficulty = data.get("difficulty", "medium")
    q_type     = data.get("q_type", "single")

    # ── Input validation ──────────────────────────────────────────────────────
    if not isinstance(note_paths, list) or not note_paths:
        return jsonify({"error": "note_paths must be a non-empty list."}), 400

    if not isinstance(count, int) or not (1 <= count <= 50):
        return jsonify({"error": "count must be an integer between 1 and 50."}), 400

    if difficulty not in ("easy", "medium", "hard"):
        return jsonify({"error": "difficulty must be 'easy', 'medium', or 'hard'."}), 400

    if q_type not in ("single", "multiple"):
        return jsonify({"error": "q_type must be 'single' or 'multiple'."}), 400

    # ── Generate ──────────────────────────────────────────────────────────────
    try:
        questions = generate_exam(
            note_paths=note_paths,
            count=count,
            difficulty=difficulty,
            q_type=q_type,
        )
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        return jsonify({"error": f"Generation failed: {str(e)}"}), 500

    return jsonify({
        "questions": questions,
        "meta": {
            "count":      len(questions),
            "difficulty": difficulty,
            "q_type":     q_type,
            "note_count": len(note_paths),
        }
    }), 200