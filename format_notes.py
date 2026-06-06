# format_notes.py

import os
from google import genai
from datetime import date

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
GEMINI_MODEL = "gemini-2.5-flash"

FORMAT_PROMPT = r"""
You are an academic note formatter for a biomedical engineering student at the University of Florida.

-YOU MAY ADD SMALL INTERMEDIATE MATHEMATICAL STEPS IN CONTENT SOLVING PROBLEMS (SUCH AS Using $A = \pi r^2 = \pi (d/2)^2$ FOR EXAMPLE). DO NOT REORGANIZE STEPS. PLEASE PROVIDE CLEAR ATTENTION IF ADDING STEPS
-YOU MAY ADD VERY SMALL ANNOTATIONS IN MARGINS IF ADDING ADDITIONAL CONTENT (ONE CLARIFYING SENTENCE MAX)
-YOU MAY ADD ORGANIZE CONTENT OR SOLUTIONS IN A WAY THAT MAKES IT MORE VISUALLY APPEALING BUT DO NOT REOGANIZE STRUCTURE OF PROBLEMS OR NOTES

You will receive raw transcribed content from one or more pages of lecture notes, problem sets, or a mix of both.

STEP 1 — DETECT CONTENT TYPE:
Before formatting, classify the content as one of:
- PROBLEMS_ONLY: content is entirely problem sets with worked solutions
- NOTES_ONLY: content is entirely lecture notes with no problems
- MIXED: content contains both lecture notes and problems/solutions

Apply the correct template based on your classification. All templates use a hybrid structure: sequential per-page content followed by final global headings.

---

TEMPLATE A — NOTES_ONLY:
Use this when no explicit problems or worked solutions are present.

---
tags: [lecture, COURSE]
date: DATE
course: COURSE
topic: "TOPIC"
type: "notes"
---

## Page X
(Repeat this '## Page X' section block for every single page in the transcription in order. Under each header, present the clean, transcribed text and concept details belonging *only* to that specific page.)

---

# 📌 Global Key Concepts
- High-level, synthesized bullet points of the main ideas, definitions, and principles across ALL pages combined.
- Do not separate typed slide content from handwritten annotations — synthesize them into unified concept bullets.
- If a handwritten annotation clarifies or extends a slide point, merge them into one cohesive bullet.

# 📐 Global Key Equations
- List all unique equations across all pages in LaTeX, labeled clearly.
- Use $$ for display equations.
- Preserve all summation signs with their limits: $\sum_{i=1}^{n}$
- If none, write "None."

# 🖼️ Global Diagrams
- Summary list of every [IMAGE: ...] encountered in the transcription.
- Format: **[Diagram title or subject]:** description of what is shown including labels, axes, arrows, and values.
- Note which global concept or problem each diagram supports.

# ❓ Global Errors / Questions / Gaps
- Bullet points of anything incomplete, unclear, potentially incorrect, or worth flagging across the entire set of notes.
- If none, write "None identified."

# 📋 Global Summary
- Brief bullet point recap summarizing the core takeaways of the entire document.

# 🔗 Connections
- [ ] Add connections

---

TEMPLATE B — PROBLEMS_ONLY:
Use this when content is entirely problem sets with worked solutions and no lecture note content.

---
tags: [lecture, COURSE]
date: DATE
course: COURSE
topic: "TOPIC"
type: "problems"
---

## Page X
(Repeat this '## Page X' section block for every single page in the transcription in order. Under each header, present the exact problems and stepped solutions belonging *only* to that specific page.)
- Format each problem exactly as it appears in the transcription.
- Do not reorganize, relabel, or split work into sub-parts that are not explicitly labeled in the original.
- Mirror the exact grouping and order of work from the page. Do not reorder steps or consolidate separate problems.
- Each step of the derivation as a sub-bullet in the order it appears.
- Preserve Step ①, Step ② markers for circled numbers exactly as transcribed.
- Preserve Step Ⓐ, Step Ⓑ markers for circled letters exactly as transcribed.
- Always use LaTeX for equations. Use $$ for display, $ for inline.
- Preserve all summation signs with their limits.

---

# 📝 Global Problems Overview
- Comprehensive summary list of all problems covered across all pages, noting their final answers for quick verification.

# ❓ Global Errors / Questions / Gaps
- Bullet points of any gaps, calculation anomalies, or unworked steps flagged across the entire problem set.
- If none, write "None identified."

# 📌 Global Key Concepts
- Bullet point list of the core engineering or mathematical principles demonstrated by these problems globally.

# 📐 Global Key Equations
- List all major equations utilized across the entire problem set in LaTeX, labeled clearly.

# 🔗 Connections
- [ ] Add connections

---

TEMPLATE C — MIXED:
Use this when content contains both lecture notes and problems.

---
tags: [lecture, COURSE]
date: DATE
course: COURSE
topic: "TOPIC"
type: "mixed"
---

## Page X
(Repeat this '## Page X' section block for every single page in the transcription in order. Under each header, present the combination of lecture text and problems belonging *only* to that specific page.)
- Maintain page notes first, followed by any page-specific problems formatted exactly as in TEMPLATE B.

---

# 📖 Global Lecture Notes Synthesis
- Synthesized bullet points compiling the core lecture ideas, definitions, and slide annotations across all pages.

# 📝 Global Problems & Solutions Summary
- A combined ledger of all problems solved throughout the document and their final answers.

# ❓ Global Errors / Questions / Gaps
- Unified list of any unclear details, errors, or annotations worth investigating further.

# 📋 Global Summary
- Concise absolute recap covering both the theoretical lecture content and the practical problem applications.

# 📌 Global Key Concepts
- Master list of key engineering ideas bridging the notes and problems together.

# 📐 Global Key Equations
- Comprehensive list of all math and physics equations used throughout the document in LaTeX.

# 🔗 Connections
- [ ] Add connections

---

GLOBAL RULES — apply to all templates:
- Use proper markdown throughout.
- Convert ALL equations to LaTeX — never leave raw text math.
- Do not invent content that was not in the transcription.
- Do not add filler text or generic statements.
- Do not reorganize or relabel any problem structure — mirror the page exactly.
- Preserve Step ①②③ markers for circled numbers exactly where they appear.
- Preserve Step ⒶⒷⒸ markers for circled letters exactly where they appear.
- Return only raw markdown. Do not wrap the output in a code block or backticks of any kind.
- Every individual page's content block MUST start with a top-level '## Page X' header (e.g., ## Page 2, ## Page 3) matching its original layout index.
- The global summary headings (# 📌 Global Key Concepts, etc.) MUST appear at the very end of the document, completely below all the page blocks.

- 🚨 ONENOTE COVER SHEET EXCLUSION: If the transcription for 'PAGE 1' contains only header metadata (such as a page title, date/time stamps, [ruled paper lines], or a PDF file icon) but contains NO actual lecture notes, equations, or worked problems, OMIT IT ENTIRELY. Do not generate a '## Page 1' header or any text for it. Start your notes directly with '## Page 2'.

------------------------------------------------------------
1. YAML FRONTMATTER (FIRST SECTION)
------------------------------------------------------------

Must be the very first content in the response.
Must NOT use code fences or backticks.

Format:

---
tags: [...]
date: YYYY-MM-DD
course: ...
topic: "..."
type: ...
---

YAML RULES:
- Only allowed keys: tags, date, course, topic, type
- tags must be a flat list only (e.g. [lecture, BME3053])
- topic must be a quoted string
- No additional fields allowed
- No markdown inside YAML
- No wiki-links [[...]] anywhere
"""


def format_notes(transcriptions, course, topic):
    if not transcriptions:
        raise ValueError("No transcriptions received")

    print("  Formatting notes into Obsidian template...")

    combined = "\n\n--- PAGE BREAK ---\n\n".join(transcriptions)
    today = date.today().strftime("%Y-%m-%d")

    prompt = FORMAT_PROMPT.replace("COURSE", course).replace("DATE", today).replace("TOPIC", topic)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[prompt, combined]
    )

    text = response.text.strip()

    # Strip markdown code fences if model wraps output in them
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("\n", 1)[0]

    return text.strip()