# NoteStream

A full-stack MVP from `PRD.md` that turns a YouTube tutorial into study materials: summary, notes, quizzes, PDF exports, and an in-app AI tutor for note Q&A.

## Current Features

- YouTube processing
  - URL validation (`youtube.com/watch`, `youtu.be`, `shorts`)
  - Metadata extraction (title, channel, duration, publish date, thumbnail)
  - Transcript extraction from available captions
- Independent generation flows
  - Summary, Notes, and Quiz can be generated in any order (no forced dependency)
- Notes generation
  - Styles: `cornell`, `mind_map`, `hierarchical`, `custom`
  - Mind map style renders as a visual diagram (not plain list)
  - Hierarchical notes are rendered with clearer nested indentation
- Quiz generation
  - Enabled: `none`, `multiple_choice`, `written_answers`, `exam_style`, `custom`
  - Disabled in both frontend/backend: `flashcards`, `crossword`
- AI Tutor (inside Notes view)
  - Two-column Notes layout: left = notes, right = chat
  - Chat automatically uses notes as default context
  - Supports conversation history for follow-up questions
  - Supports **Exam Mode**: provide an exam/competition name to adapt answer style to likely syllabus and format
- PDF export
  - Notes PDF and Quiz PDF supported
  - Mind map PDF is not constrained to fixed A4 and expands with content
  - Download buttons are disabled until corresponding content is generated
- Caching
  - Local SQLite cache for videos/artifacts at `.cache/notestream.db`

## Tech Stack

- Backend: `FastAPI` + `Pydantic` + `HTTPX` + `youtube-transcript-api` + `yt-dlp`
- Core modules: `src/notestream/models.py` + `src/notestream/services.py` + `src/notestream/db.py`
- CLI: `Typer` + `Rich` + `Loguru`
- Frontend: `Vue 3` + `Vite` + `Tailwind` + `vite-plugin-pwa`
- Markdown rendering: `marked` + `DOMPurify`
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

Frontend default backend URL is `http://localhost:8000` and can be changed in the UI.

## API Endpoints

- `POST /api/summary`
- `POST /api/notes`
- `POST /api/notes/chat`
- `POST /api/notes/pdf`
- `POST /api/quiz`
- `POST /api/quiz/pdf`

### `POST /api/notes/chat` request fields

- `bailian_api_key`: string
- `model`: string | null
- `notes_markdown`: string
- `question`: string
- `history`: array of `{ role: "user" | "assistant", content: string }`
- `exam_mode`: boolean (default `false`)
- `exam_name`: string | null (required when `exam_mode=true`)

## Notes

- `quiz_type=flashcards` and `quiz_type=crossword` return `422`.
- If a video has no captions available, APIs return:
  `This video has no available captions. Please try a different video.`

## CLI Usage

```bash
uv run notestream summary "https://www.youtube.com/watch?v=VIDEO_ID" --api-key "<YOUR_BAILIAN_KEY>"
uv run notestream notes "https://www.youtube.com/watch?v=VIDEO_ID" --api-key "<YOUR_BAILIAN_KEY>" --style hierarchical
uv run notestream quiz "https://www.youtube.com/watch?v=VIDEO_ID" --api-key "<YOUR_BAILIAN_KEY>" --quiz-type multiple_choice --difficulty medium
```

## Environment Variables

Copy `.env.example` to `.env` and configure:

- `NOTESTREAM_DB_PATH`
- `NOTESTREAM_DEFAULT_MODEL`
- `NOTESTREAM_ALLOWED_ORIGINS`

## Development Checks

```bash
uv run ruff check src
cd frontend && npm run build
```
