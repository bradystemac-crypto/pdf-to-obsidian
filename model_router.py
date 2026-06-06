import os
import json
from datetime import date

# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
_QUOTA_PATH = os.path.join(_DATA_DIR, "quota.json")


# ─────────────────────────────────────────────────────────────
# MODEL CATALOG
# ─────────────────────────────────────────────────────────────

MODELS = {
    "gemini-3.5-flash": {
        "provider": "gemini",
        "reasoning": 0.8,
        "instruction_following": 0.85,
        "speed": 0.9,
        "cost": 0.0,
        "context": 1_048_576,
    },
    "gemini-3.1-flash-lite": {
        "provider": "gemini",
        "reasoning": 0.65,
        "instruction_following": 0.8,
        "speed": 0.95,
        "cost": 0.0,
        "context": 1_048_576,
    },
    "gemini-3-flash": {
        "provider": "gemini",
        "reasoning": 0.7,
        "instruction_following": 0.8,
        "speed": 0.85,
        "cost": 0.0,
        "context": 1_048_576,
    },
    "gemini-3-flash-live": {
        "provider": "gemini",
        "reasoning": 0.65,
        "instruction_following": 0.75,
        "speed": 0.98,
        "cost": 0.0,
        "context": 65_000,
    },

    "meta-llama/llama-3.3-70b-instruct:free": {
        "provider": "openrouter",
        "reasoning": 0.8,
        "instruction_following": 0.78,
        "speed": 0.7,
        "cost": 0.0,
        "context": 131_072,
    },
    "qwen/qwen3-coder:free": {
        "provider": "openrouter",
        "reasoning": 0.75,
        "instruction_following": 0.7,
        "speed": 0.8,
        "cost": 0.0,
        "context": 1_048_576,
    },
    "moonshotai/kimi-k2.6:free": {
        "provider": "openrouter",
        "reasoning": 0.82,
        "instruction_following": 0.78,
        "speed": 0.75,
        "cost": 0.0,
        "context": 262_144,
    },
}


# ─────────────────────────────────────────────────────────────
# TASK WEIGHTS
# ─────────────────────────────────────────────────────────────

TASK_WEIGHTS = {
    "exam_gen": {"reasoning": 0.4, "instruction_following": 0.4, "speed": 0.2},
    "summarization": {"reasoning": 0.3, "instruction_following": 0.5, "speed": 0.2},
    "tagging": {"instruction_following": 0.6, "speed": 0.3, "reasoning": 0.1},
    "chat": {"speed": 0.4, "instruction_following": 0.3, "reasoning": 0.3},
    "formatting": {"instruction_following": 0.7, "speed": 0.2, "reasoning": 0.1},
    "transcription": {"speed": 0.7, "instruction_following": 0.2, "reasoning": 0.1},
}


# ─────────────────────────────────────────────────────────────
# USAGE TRACKING
# ─────────────────────────────────────────────────────────────

def _load_usage():
    if not os.path.exists(_QUOTA_PATH):
        return {}
    with open(_QUOTA_PATH, "r") as f:
        return json.load(f)


def _today():
    return str(date.today())


def get_model_usage(model: str) -> int:
    data = _load_usage()
    return data.get(_today(), {}).get(model, 0)


# ─────────────────────────────────────────────────────────────
# SOFT LIMITS (usage pressure simulation)
# ─────────────────────────────────────────────────────────────

MODEL_SOFT_LIMITS = {
    "gemini-3.5-flash": 200000,
    "gemini-3.1-flash-lite": 250000,
    "gemini-3-flash": 250000,
    "gemini-3-flash-live": 150000,
    "meta-llama/llama-3.3-70b-instruct:free": 180000,
    "qwen/qwen3-coder:free": 180000,
    "moonshotai/kimi-k2.6:free": 180000,
}


# ─────────────────────────────────────────────────────────────
# SCORING ENGINE (usage-aware)
# ─────────────────────────────────────────────────────────────

def score_model(model_input, task: str) -> float:
    model = MODELS.get(model_input, {})

    weights = TASK_WEIGHTS.get(task, TASK_WEIGHTS["chat"])

    score = 0.0
    for k, w in weights.items():
        score += model.get(k, 0) * w

    if model.get("cost", 1) == 0:
        score += 0.15

    # ───── USAGE PENALTY ─────
    used = get_model_usage(model_input)
    limit = MODEL_SOFT_LIMITS.get(model_input, 200000)

    ratio = used / limit if limit else 0

    if ratio > 0.9:
        score *= 0.6
    elif ratio > 0.75:
        score *= 0.8
    elif ratio > 0.5:
        score *= 0.92

    return score


# ─────────────────────────────────────────────────────────────
# PRIMARY ROUTER (NO EXTERNAL API CHANGE REQUIRED)
# ─────────────────────────────────────────────────────────────

def get_model(task: str) -> str:
    ranked = sorted(
        MODELS.keys(),
        key=lambda m: score_model(m, task),
        reverse=True
    )

    # HARD SKIP IF OVER LIMIT
    usable = []
    for m in ranked:
        used = get_model_usage(m)
        limit = MODEL_SOFT_LIMITS.get(m, 200000)

        if used >= limit:
            continue
        usable.append(m)

    chosen = usable[0] if usable else ranked[0]

    print(f"[router] {task} → {chosen}")
    return chosen


# ─────────────────────────────────────────────────────────────
# FAILOVER EXECUTION WRAPPER (NEW CORE FEATURE)
# ─────────────────────────────────────────────────────────────

def run_with_failover(task: str, call_fn, *args, max_retries: int = 5, **kwargs):
    ranked = sorted(
        MODELS.keys(),
        key=lambda m: score_model(m, task),
        reverse=True
    )

    tried = []

    for model in ranked:
        if len(tried) >= max_retries:
            break

        tried.append(model)

        try:
            result = call_fn(model, *args, **kwargs)

            # detect "busy" response string
            if isinstance(result, str):
                if "model is busy and unavailable" in result.lower():
                    print(f"[FAILOVER] {model} busy → next")
                    continue

            return result, model

        except Exception as e:
            msg = str(e).lower()

            if "model is busy and unavailable" in msg:
                print(f"[FAILOVER] {model} busy exception → next")
                continue

            print(f"[ERROR] {model}: {e}")
            continue

    raise RuntimeError("All models failed or are busy.")


# ─────────────────────────────────────────────────────────────
# USAGE LOGGER (UNCHANGED)
# ─────────────────────────────────────────────────────────────

def log_usage(model: str, tokens: int):
    os.makedirs(_DATA_DIR, exist_ok=True)

    data = _load_usage()
    today = _today()

    if today not in data:
        data[today] = {}

    data[today][model] = data[today].get(model, 0) + tokens

    with open(_QUOTA_PATH, "w") as f:
        json.dump(data, f, indent=2)