import json
import os
from google import genai
from model_router import get_model, log_usage

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# ── JSON schema contract sent to Gemini ──────────────────────────────────────
SCHEMA_DESCRIPTION = """
Return ONLY a valid JSON array. No markdown, no explanation, no backticks.
Each element must follow this exact schema:

{
  "question": "<question text>",
  "type": "single" | "multiple",
  "options": ["<option A>", "<option B>", "<option C>", "<option D>"],
  "correct": [<zero-based index>, ...],
  "explanation": "<why the answer(s) are correct>"
}

Rules:
- single → exactly 1 correct answer
- multiple → 2–3 correct answers
- 4 options exactly
- no outside knowledge
"""

DIFFICULTY_GUIDANCE = {
    "easy": "Direct recall from notes.",
    "medium": "Concept relationships and application.",
    "hard": "Multi-step reasoning and synthesis."
}


def _build_prompt(note_contents, count, difficulty, q_type):
    notes_block = "\n\n---\n\n".join(note_contents)

    if q_type == "single":
        type_instruction = f"{count} single-answer MCQs."
    elif q_type == "multiple":
        type_instruction = f"{count} multi-answer MCQs."
    else:
        type_instruction = f"{count} mixed MCQs."

    return f"""
Generate exam questions.

Difficulty: {difficulty}
Type: {type_instruction}

{SCHEMA_DESCRIPTION}

NOTES:
{notes_block}

Return exactly {count} questions.
"""


def _read_notes(note_paths):
    contents = []
    for path in note_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as f:
            contents.append(f.read())
    return contents


def _parse_response(raw, expected_count):
    clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")

    questions = json.loads(clean)

    if not isinstance(questions, list):
        raise ValueError("Expected list output")

    return questions[:expected_count]


def generate_exam(note_paths, count=10, difficulty="medium", q_type="single"):
    if not note_paths:
        raise ValueError("No notes provided")

    note_contents = _read_notes(note_paths)

    prompt = _build_prompt(note_contents, count, difficulty, q_type)

    model = get_model("exam_gen")

    try:
        response = client.models.generate_content(
            model=model,
            contents=[prompt]
        )

        raw_text = response.text.strip()

        token_count = (
            response.usage_metadata.total_token_count
            if getattr(response, "usage_metadata", None)
            else 0
        )

        log_usage(model, token_count)

    except Exception as e:
        raise RuntimeError(f"Gemini exam generation failed: {e}")

    return _parse_response(raw_text, count)