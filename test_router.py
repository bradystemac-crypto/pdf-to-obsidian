from model_router import MODELS, TASK_WEIGHTS, score_model, get_model

TASKS = [
    "exam_gen",
    "summarization",
    "tagging",
    "chat",
    "matching",
    "formatting",
    "transcription",
]


def print_ranking(task: str, top_k: int = 5):
    print(f"\n================ {task.upper()} ================\n")

    ranked = []

    # ─────────────────────────────────────────────
    # SCORE ALL MODELS (safe + consistent)
    # ─────────────────────────────────────────────
    for model_name, data in MODELS.items():
        score = score_model(model_name, task)
        ranked.append((score, model_name, data))

    ranked.sort(reverse=True, key=lambda x: x[0])

    # ─────────────────────────────────────────────
    # TASK WEIGHTS
    # ─────────────────────────────────────────────
    weights = TASK_WEIGHTS.get(task, TASK_WEIGHTS["chat"])

    print("Weights:")
    for k, v in weights.items():
        print(f"  {k:<25} {v}")

    print("\nTop candidates:\n")

    # ─────────────────────────────────────────────
    # TOP K MODELS
    # ─────────────────────────────────────────────
    for i, (score, model, data) in enumerate(ranked[:top_k], 1):
        print(f"{i}. {model}")
        print(f"   score: {score:.4f}")
        print(f"   speed: {data.get('speed')}")
        print(f"   reasoning: {data.get('reasoning')}")
        print(f"   instruction: {data.get('instruction_following')}")
        print(f"   cost: {data.get('cost')}")
        print("")

    # ─────────────────────────────────────────────
    # ROUTER CROSS-CHECK
    # ─────────────────────────────────────────────
    winner = ranked[0][1]
    print(f"→ SELECTED BY MANUAL RANK: {winner}")

    actual = get_model(task)
    print(f"→ get_model() RETURNS: {actual}")


def main():
    print("\n########################################################")
    print("           ROUTER DEBUG + MODEL SELECTION VIEW         ")
    print("########################################################\n")

    for task in TASKS:
        print_ranking(task)

    print("\n########################################################\n")


if __name__ == "__main__":
    main()