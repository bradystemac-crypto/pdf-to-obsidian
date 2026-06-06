import os
import json
import math
import hashlib
import datetime
# 1. Use the modern SDK import
from google import genai
from google.genai import types

class FlashcardEngine:
    def __init__(self, log_path="vault_fc_log.json"):
        self.log_path = log_path
        self.tracking_data = self._load_log()
        
        # 2. Instantiate the unified Client object using the environment key
        api_key = os.environ.get("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key) if api_key else None
        
        # 3. Target the modern flash model
        self.model_name = "gemini-2.5-flash"

    def _load_log(self):
        """Loads the SM-2 tracking log from disk if it exists."""
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                return {}
        return {}

    def generate_deck_from_notes(self, note_contents: str, difficulty: str, count: int) -> list:
        """
        Sends the note contents to the modern Gemini client and handles 
        the structured JSON output generation for the flashcards.
        """
        if not self.client:
            raise ValueError("Gemini Client is not initialized. Check your GEMINI_API_KEY.")

        # Build a robust engineering-focused prompt
        prompt = f"""
        You are an expert educational assistant specializing in Biomedical Engineering.
        Generate a deck of exactly {count} flashcards based on the source material provided below.

        - DO NOT MAKE THE QUESTIONS OR THE ANSWERS TOO LONG. Each flashcard should be concise and focused on a single concept or fact.
        
        Target Difficulty Level: {difficulty}
        - easy: focus on core conceptual definitions and terms.
        - medium: focus on operational mechanisms, pathways, and logical relations.
        - hard: focus on multi-system synthesis, mathematical applications, and clinical/engineering tradeoffs.

        Source Material:
        \"\"\"
        {note_contents}
        \"\"\"
        """

        # 4. Use the new structured schema configuration to guarantee clean JSON output
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "front": types.Schema(type=types.Type.STRING, description="The question or active recall prompt."),
                        "back": types.Schema(type=types.Type.STRING, description="The concise, high-yield explanation or answer.")
                    },
                    required=["front", "back"]
                )
            ),
            temperature=0.2
        )

        try:
            # 5. Call generation via the unified client models service
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            
            # The response text is guaranteed to be a valid JSON array matching your schema
            return json.loads(response.text)

        except Exception as e:
            print(f"Error generating flashcards with modern SDK: {e}")
            return []

    def update_card_review(self, card_id: str, score: int) -> dict:
        """Processes user response quality scores (0-5) and commits SM-2 updates."""
        card_data = self.tracking_data.get(card_id)
        if not card_data:
            card_data = {
                "repetitions": 0,
                "interval": 1,
                "ease_factor": 2.5,
                "next_review": datetime.date.today().isoformat()
            }

        repetitions = card_data.get("repetitions", 0)
        interval = card_data.get("interval", 1)
        ease_factor = card_data.get("ease_factor", 2.5)

        if score >= 3:
            if repetitions == 0:
                interval = 1
            elif repetitions == 1:
                interval = 6
            else:
                interval = math.ceil(interval * ease_factor)
            repetitions += 1
        else:
            repetitions = 0
            interval = 1

        ease_factor = ease_factor + (0.1 - (5 - score) * (0.08 + (5 - score) * 0.02))
        if ease_factor < 1.3:
            ease_factor = 1.3

        next_review_date = datetime.date.today() + datetime.timedelta(days=interval)

        card_data["repetitions"] = repetitions
        card_data["interval"] = interval
        card_data["ease_factor"] = ease_factor
        card_data["next_review"] = next_review_date.isoformat()

        self.tracking_data[card_id] = card_data
        self._save_log()

        return card_data

    def _save_log(self):
        """Saves tracking data to disk."""
        try:
            with open(self.log_path, 'w', encoding='utf-8') as f:
                json.dump(self.tracking_data, f, indent=4)
        except Exception as e:
            print(f"Error saving flashcard log: {e}")