# pdf-to-obsidian

Turn lecture PDFs into formatted, interconnected Obsidian notes — powered by Gemini.

Upload a PDF, and the pipeline extracts each page, transcribes handwritten and typed content with AI, formats it as Obsidian-friendly markdown, finds connections to your existing notes, and writes the result into your vault.

## Features

- PDF to image extraction with diagram detection
- AI-powered transcription (Gemini)
- Smart formatting with Obsidian-flavored markdown
- Automatic cross-note connections and wikilinks
- Intelligent tagging and theme detection
- Built-in flashcard engine with spaced repetition
- Exam question generator
- Web UI for uploading and tracking pipeline progress

## Requirements

- Python 3.10 or newer
- A [Gemini API key](https://aistudio.google.com/apikey) (free tier works)
- An Obsidian vault on your computer

No hosting required. Everything runs locally on your machine with your own API key.

## Quick Start

### 1. Get the code

```bash
git clone https://github.com/bradystemac-crypto/pdf-to-obsidian.git
cd pdf-to-obsidian
```

Or download the ZIP from GitHub and extract it.

### 2. Run setup

```bash
python setup.py
```

The setup wizard will:

1. Create a Python virtual environment
2. Install dependencies
3. Ask for your Gemini API key
4. Ask for your Obsidian vault path (type it or use the folder picker)
5. Write a `.env` file with your settings
6. **(Windows)** Create `PDF-to-Obsidian.bat` on your Desktop

### 3. Start the app

**Windows:** double-click `PDF-to-Obsidian.bat` on your Desktop, double-click `run.bat` in the project folder, or:

```bat
venv\Scripts\activate
python app.py
```

**Mac / Linux:**

```bash
chmod +x run.sh
./run.sh
```

Or manually:

```bash
source venv/bin/activate
python app.py
```

### 4. Open the web UI

Go to [http://localhost:5000](http://localhost:5000), upload a PDF, and run the pipeline.

## Manual configuration

If you prefer not to use the setup wizard, copy the example env file and edit it:

```bash
cp .env.example .env
```

Then fill in:

```env
GEMINI_API_KEY=your-key-here
OBSIDIAN_VAULT_PATH=/full/path/to/your/obsidian/vault
```

Install dependencies yourself:

```bash
python -m venv venv
source venv/bin/activate      # Mac/Linux
# venv\Scripts\activate       # Windows
pip install -r requirements.txt
```

## How it works

```
PDF upload
   ↓
Page images (PyMuPDF)
   ↓
AI transcription (Gemini)
   ↓
Formatted markdown
   ↓
Connection finder + tag indexer
   ↓
Written to your Obsidian vault
```

## Project structure

| File / folder | Purpose |
|---|---|
| `app.py` | Flask web server and upload UI |
| `main.py` | CLI pipeline runner |
| `setup.py` | Interactive first-time setup |
| `config.py` | Loads settings from `.env` |
| `pdf_to_images.py` | PDF page extraction |
| `transcribe.py` | AI transcription |
| `format_notes.py` | Markdown formatting |
| `connections.py` | Cross-note linking |
| `obsidian_writer.py` | Writes notes into your vault |
| `flashcards.py` | Flashcard generation and review |
| `exam_gen.py` | Practice exam generation |
| `templates/` | Web UI templates |
| `prompts/` | AI prompt templates |

## API costs

You bring your own Gemini API key. Usage is billed to your Google AI account (or consumed from the free tier). The app author does not pay for your usage.

## Troubleshooting

**"Missing OBSIDIAN_VAULT_PATH" or "Missing GEMINI_API_KEY"**

Run `python setup.py` again, or create a `.env` file from `.env.example`.

**Virtual environment not found**

Run `python setup.py` before using `run.bat` or `run.sh`.

**Port 5000 already in use**

Stop the other process using port 5000, or change the port in `app.py`.

## License

MIT
