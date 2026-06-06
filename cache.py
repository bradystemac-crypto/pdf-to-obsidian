# cache.py

import os
import json
import hashlib

CACHE_FILE = "cache.json"

def get_pdf_hash(pdf_path):
    """Returns a unique hash of the PDF file contents"""
    hasher = hashlib.md5()
    with open(pdf_path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_cache():
    """Loads the cache from disk"""
    if not os.path.exists(CACHE_FILE):
        return {}
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_cache(cache):
    """Saves the cache to disk"""
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def get_cached_transcription(pdf_path):
    """
    Returns cached transcription if this PDF was already processed.
    Returns None if not cached.
    """
    pdf_hash = get_pdf_hash(pdf_path)
    cache = load_cache()

    if pdf_hash in cache:
        print(f"  ✅ Cache hit — skipping Gemini transcription")
        return cache[pdf_hash]["transcriptions"]

    return None

def save_transcription_to_cache(pdf_path, transcriptions):
    """Saves a transcription result to cache keyed by PDF hash"""
    pdf_hash = get_pdf_hash(pdf_path)
    cache = load_cache()

    cache[pdf_hash] = {
        "transcriptions": transcriptions,
        "pdf_name": os.path.basename(pdf_path)
    }

    save_cache(cache)
    print(f"  💾 Transcription cached for future runs")