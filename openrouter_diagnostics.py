import os
import requests

API_KEY = os.getenv("OPENROUTER_API_KEY")

URL = "https://openrouter.ai/api/v1/models"

headers = {
    "Authorization": f"Bearer {API_KEY}",
}

def get_models():
    res = requests.get(URL, headers=headers)
    res.raise_for_status()
    return res.json()["data"]

def is_free(model):
    pricing = model.get("pricing", {})

    # Free models usually have zero cost
    return (
        pricing.get("prompt", 1) == 0
        and pricing.get("completion", 1) == 0
    ) or model["id"].endswith(":free")


def main():
    models = get_models()

    free_models = [
        m for m in models if is_free(m)
    ]

    print("\n=== FREE OPENROUTER MODELS ===\n")

    for m in free_models:
        print(f"- {m['id']}")
        print(f"  context: {m.get('context_length', 'unknown')}")
        print(f"  pricing: {m.get('pricing')}")
        print()

    print(f"\nTOTAL FREE MODELS: {len(free_models)}")


if __name__ == "__main__":
    main()