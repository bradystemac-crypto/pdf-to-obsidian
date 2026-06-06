# transcribe.py

import time
import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

PRIMARY_MODEL = "gemini-3.5-flash"
FALLBACK_MODEL = "gemini-3.1-flash-lite"

PROMPT = r"""
You are a forensic note transcription assistant. Your only job is to extract every piece of content visible on each page — nothing more, nothing less.

You are given multiple images of academic note pages exported from OneNote. Each page may contain:
- PowerPoint slide content (typed text, diagrams, images)
- Handwritten annotations in multiple colors
- Mathematical equations with small subscripts, superscripts, and integral signs
- Diagrams or figures with handwritten labels
- Circled numbers used to indicate ordered steps in a derivation or solution

Transcribe ALL pages in order. For each page use this exact format:

--- PAGE 1 ---
[full transcription of page 1]

--- PAGE 2 ---
[full transcription of page 2]

...and so on for every page.

CRITICAL RULES — read carefully before transcribing:

1. COMPLETENESS: Scan every region of the page before moving on.
   - Divide each page mentally into a 3x3 grid (top-left, top-center, top-right, middle-left, center, middle-right, bottom-left, bottom-center, bottom-right).
   - Scan each of the 9 zones explicitly before moving on.
   - Top, bottom, margins, and corners all may contain content.
   - Do not skip any handwritten content even if it looks like scratch work.
   - If you are unsure what a word or symbol says, write your best guess in [brackets] like [unclear: possibly "flux"].
   - Never skip content because it seems redundant or unimportant.

2. SMALL AND DENSE MATH — THIS IS CRITICAL:
   - Actively look for small handwriting. Students often write subscripts, superscripts, and intermediate steps very small.
   - After transcribing each equation, zoom in mentally on every term and ask: "Is there a subscript, superscript, or small modifier I missed?"
   - Scrutinize every equation for:
     * Subscripts: $x_i$, $C_{HEP}$, $\dot{m}_{in}$
     * Superscripts: $x^2$, $e^{-kt}$
     * Integral signs with limits: $\int_a^b$, $\oint$
     * Derivative notation: $\frac{d}{dt}$, $\frac{\partial}{\partial x}$, $\dot{x}$, $\ddot{x}$
     * Greek letters: $\alpha$, $\beta$, $\gamma$, $\delta$, $\epsilon$, $\zeta$, $\eta$, $\theta$, $\lambda$, $\mu$, $\nu$, $\xi$, $\pi$, $\rho$, $\sigma$, $\tau$, $\phi$, $\chi$, $\psi$, $\omega$, $\Omega$, $\Delta$, $\Sigma$, $\Gamma$, $\Lambda$, $\Phi$, $\Psi$
     * Fraction bars — check both numerator and denominator carefully
     * Dot notation for rates: $\dot{V}$, $\dot{M}$, $\dot{n}$, $\dot{Q}$, $\dot{W}$
     * Summation: $\sum_{i=1}^{n}$, $\sum_{k=0}^{\infty}$
     * Product notation: $\prod_{i=1}^{n}$
     * Vector and matrix notation: $\vec{F}$, $\hat{n}$, $\mathbf{A}$, $\mathbf{x}$
     * Nabla / gradient / divergence / curl: $\nabla$, $\nabla^2$, $\nabla \cdot \vec{F}$, $\nabla \times \vec{F}$
     * Laplacian: $\nabla^2 f$, $\frac{\partial^2 f}{\partial x^2}$
     * Statistical notation: $\bar{x}$, $\hat{x}$, $\sigma^2$, $\mu \pm \sigma$, $\tilde{x}$
     * Convolution: $f * g$
     * Unit step and impulse functions: $u(t)$, $\delta(t)$
     * Infinity and limits: $\infty$, $\lim_{x \to 0}$, $\lim_{t \to \infty}$
     * Absolute value and norms: $|x|$, $\|x\|$, $\|x\|_2$
     * Piecewise / conditional notation: braces with conditions
     * Fourier / Laplace transform notation: $\mathcal{F}$, $\mathcal{L}$, $\hat{f}(\omega)$, $F(s)$
     * Transfer functions and s-domain: $H(s)$, $G(s)$, $s = j\omega$
     * Exponential and complex: $e^{j\omega t}$, $e^{st}$, $j = \sqrt{-1}$
     * Logical / set notation if present: $\in$, $\subset$, $\cup$, $\cap$, $\forall$, $\exists$
   - If a symbol is small but present, transcribe it. Do not silently drop it.
   - If genuinely illegible due to size, flag it: [illegible small text]

3. NO HALLUCINATION: Only transcribe what is physically visible on the page.
   - Do not infer, complete, or extend equations beyond what is written.
   - Do not add steps that seem mathematically correct but are not explicitly shown.
   - Do not fill in missing algebra. If a step is missing from the page, it is missing from the transcription.
   - If a value or variable appears ambiguous, note it: [unclear: x or χ?]

4. SLIDE CONTENT: Extract all typed text exactly as written, word for word.

5. HANDWRITTEN NOTES: Transcribe all handwriting completely.
   - Label color changes in brackets like [red], [blue] only when color changes.
   - Preserve the spatial relationship between annotations and the slide content they reference.
   - If a handwritten note clearly points to or annotates a specific slide element, note it: [annotation pointing to diagram: "..."]

6. EQUATIONS: Convert all equations to LaTeX.
   - Use $$ for display equations, $ for inline.
   - Transcribe every intermediate step shown — do not collapse multi-step derivations.
   - Pay close attention to whether terms are in the numerator vs denominator of a fraction.
   - If an equation is partially illegible, transcribe what is visible and flag: [partially illegible]

7. DIAGRAMS AND IMAGES: Do not skip any diagram or image.
   - Write: [IMAGE: detailed description including axis labels, units, arrows, curves, shapes, and all labeled variables or values]
   - If the diagram is part of a problem, describe it in enough detail that the problem could be fully reconstructed from your description alone.
   - Include any handwritten labels, arrows, or annotations on or around the diagram.

8. CIRCLED STEP NUMBERS AND LETTERS: If you see circled numbers (①②③) or circled letters (ⒶⒷⒸ) marking ordered steps, preserve them as:
   Step ①: [content]
   Step ②: [content]
   Do not reorder or renumber steps.

9. PROBLEM STRUCTURE: Preserve exact problem labeling (1a, 1b, 1c or a, b, c).
   Transcribe the typed question text first, then all handwritten work beneath it in order.

10. FINAL CHECK: Before submitting your transcription of each page, do two passes:
    Pass 1 — re-examine the full image and ask: "Is there any region of the 3x3 grid I have not yet captured?"
    Pass 2 — re-examine every equation and ask: "Is there any subscript, superscript, Greek letter, summation, vector, or small symbol I have not yet captured?"
    Add anything missing before moving to the next page.
"""

def call_gemini(model, contents, max_retries=5):
    attempt = 0
    while attempt < max_retries:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents
            )
            return response
        except Exception as e:
            attempt += 1
            if "429" in str(e):
                print(f"    [{model}] Rate limited — waiting 60s...")
                time.sleep(60)
            else:
                wait = min(2 ** attempt, 30)
                print(f"    [{model}] Retry {attempt}/{max_retries}: {e}")
                print(f"    Waiting {wait}s...")
                time.sleep(wait)
    return None


def transcribe_images(images, sleep_between_calls=2.0, max_retries=5):
    """
    Sends ALL images in one batch call.
    Tries PRIMARY model first, falls back to FALLBACK model if it fails.
    """

    contents = [PROMPT]

    for img_path in images:
        with open(img_path, "rb") as f:
            contents.append(
                types.Part.from_bytes(
                    data=f.read(),
                    mime_type="image/png"
                )
            )

    # Try primary model
    print(f"  Trying {PRIMARY_MODEL}...")
    response = call_gemini(PRIMARY_MODEL, contents, max_retries)

    # Fall back if primary failed
    if response is None:
        print(f"  Warning: {PRIMARY_MODEL} failed. Falling back to {FALLBACK_MODEL}...")
        response = call_gemini(FALLBACK_MODEL, contents, max_retries)

    if response is None:
        raise RuntimeError("Both primary and fallback models failed. Check your API quota.")

    model_used = PRIMARY_MODEL if response else FALLBACK_MODEL
    raw = response.text
    usage = getattr(response, "usage_metadata", None)
    total_tokens = getattr(usage, "total_token_count", 0)

    print(f"  Transcription done — {total_tokens} tokens — model: {model_used}")

    pages = split_pages(raw, len(images))

    usage_log = [{
        "page": "batch",
        "model_used": model_used,
        "total_tokens": total_tokens
    }]

    return pages, usage_log


def split_pages(raw_text, num_pages):
    pages = []

    for i in range(1, num_pages + 1):
        marker = f"--- PAGE {i} ---"
        next_marker = f"--- PAGE {i + 1} ---"

        start = raw_text.find(marker)
        if start == -1:
            pages.append(f"[Page {i} not found in response]")
            continue

        start += len(marker)
        end = raw_text.find(next_marker) if i < num_pages else len(raw_text)
        pages.append(raw_text[start:end].strip())

    return pages


# Test directly
if __name__ == "__main__":
    from pdf_to_images import pdf_to_images

    test_pdf = input("Enter path to a test PDF: ").strip().strip('"')
    images = pdf_to_images(test_pdf)
    results, usage_log = transcribe_images(images)

    for i, text in enumerate(results):
        print(f"\n--- PAGE {i+1} ---\n")
        print(text)