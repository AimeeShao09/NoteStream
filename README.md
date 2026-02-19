# NoteStream

A full-stack MVP implemented from `PRD.md`: paste a YouTube URL, generate a summary, study notes, and quizzes, then export PDFs.

## Current Features

- YouTube processing
  - URL validation (`youtube.com/watch`, `youtu.be`, `shorts`)
  - Video metadata extraction (title, channel, duration, publish date, thumbnail, etc.)
  - English transcript extraction (caption-only, no Whisper fallback)
- Summary generation
  - Uses Alibaba Bailian (default model: `qwen3.5-plus`)
- Notes generation
  - `cornell`, `mind_map`, `hierarchical`, `custom`
  - `mind_map` renders as an actual diagram (not plain text list)
- Quiz generation
  - Enabled: `none`, `multiple_choice`, `written_answers`, `exam_style`, `custom`
  - Disabled: `flashcards`, `crossword` (disabled in both frontend and backend)
- PDF export
  - Export supported for both Notes and Quiz
  - Mind map notes PDF is not constrained to fixed A4 size and expands with content
- Caching
  - Local SQLite cache for videos and generated artifacts (`.cache/notestream.db`)

## Tech Stack

- Backend: `FastAPI` + `Pydantic` + `HTTPX` + `youtube-transcript-api` + `yt-dlp`
- Shared core: `src/notestream/models.py` + `src/notestream/services.py` + `src/notestream/db.py`
- CLI: `Typer` + `Rich` + `Loguru`
- Frontend: `Vue 3` + `Vite` + `Tailwind` + `vite-plugin-pwa`
- PDF: `reportlab`

## Project Structure

```text
.
├── PRD.md
├── pyproject.toml
├── uv.lock
├── src/notestream/
│   ├── api.py
│   ├── cli.py
│   ├── db.py
│   ├── mindmap_renderer.py
│   ├── models.py
│   ├── pdf_renderer.py
│   ├── prompts.py
│   └── services.py
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    └── src/
```

## Quick Start

### 1) Backend

```bash
uv sync --extra dev
uv run uvicorn notestream.api:app --reload --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend calls `http://localhost:8000` by default. You can change it in `Backend API Base` on the page.

## API Endpoints

- `POST /api/summary`
- `POST /api/notes`
- `POST /api/notes/pdf`
- `POST /api/quiz`
- `POST /api/quiz/pdf`

### Notes

- `quiz_type=flashcards` and `quiz_type=crossword` return `422`.
- If a video has no available captions, the API returns:
  `This video has no available captions. Please try a different video.`

## CLI Usage

```bash
uv run notestream summary "https://www.youtube.com/watch?v=VIDEO_ID" --api-key "<YOUR_BAILIAN_KEY>"
uv run notestream notes "https://www.youtube.com/watch?v=VIDEO_ID" --api-key "<YOUR_BAILIAN_KEY>" --style hierarchical
uv run notestream quiz "https://www.youtube.com/watch?v=VIDEO_ID" --api-key "<YOUR_BAILIAN_KEY>" --quiz-type multiple_choice --difficulty medium
```

## Environment Variables

Copy `.env.example` to `.env`:

- `NOTESTREAM_DB_PATH`
- `NOTESTREAM_DEFAULT_MODEL`
- `NOTESTREAM_ALLOWED_ORIGINS`

## Development Checks

```bash
uv run ruff check src
cd frontend && npm run build
```
