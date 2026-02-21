from __future__ import annotations

import os
from io import BytesIO

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from notestream.models import (
    ChatMessage,
    NoteStyle,
    NotesChatRequest,
    NotesChatResponse,
    NotesGenerateRequest,
    NotesResponse,
    QuizGenerateRequest,
    QuizResponse,
    SummaryRequest,
    SummaryResponse,
)
from notestream.mindmap_renderer import render_mind_map_svg
from notestream.pdf_renderer import render_document_pdf
from notestream.services import (
    InvalidYouTubeUrlError,
    LLMServiceError,
    ServiceError,
    ask_notes_question,
    TranscriptUnavailableError,
    generate_notes,
    generate_quiz,
    generate_summary,
    get_video_context,
)

load_dotenv()

app = FastAPI(title="NoteStream API", version="0.1.0")

allowed_origins = [
    origin.strip()
    for origin in os.getenv("NOTESTREAM_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/summary", response_model=SummaryResponse)
async def create_summary(payload: SummaryRequest) -> SummaryResponse:
    try:
        context = await get_video_context(str(payload.youtube_url), force_refresh=payload.force_refresh)
        summary, summary_cached = await generate_summary(
            context=context,
            api_key=payload.bailian_api_key,
            model=payload.model,
            force_refresh=payload.force_refresh,
        )
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TranscriptUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SummaryResponse(
        video=context.video,
        summary=summary,
        transcript_word_count=len(context.transcript.split()),
        cached=context.video_cached and summary_cached,
    )


@app.post("/api/notes", response_model=NotesResponse)
async def create_notes(payload: NotesGenerateRequest) -> NotesResponse:
    try:
        context = await get_video_context(str(payload.youtube_url), force_refresh=payload.force_refresh)
        summary, _ = await generate_summary(
            context=context,
            api_key=payload.bailian_api_key,
            model=payload.model,
            force_refresh=payload.force_refresh,
        )
        notes, note_cached = await generate_notes(
            context=context,
            note_style=payload.note_style,
            custom_style_description=payload.custom_style_description,
            api_key=payload.bailian_api_key,
            model=payload.model,
            force_refresh=payload.force_refresh,
        )
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TranscriptUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    mind_map_svg: str | None = None
    if payload.note_style == NoteStyle.MIND_MAP:
        mind_map_svg = render_mind_map_svg(notes)

    return NotesResponse(
        video=context.video,
        summary=summary,
        note_style=payload.note_style,
        content_markdown=notes,
        mind_map_svg=mind_map_svg,
        cached=context.video_cached and note_cached,
    )


@app.post("/api/quiz", response_model=QuizResponse)
async def create_quiz(payload: QuizGenerateRequest) -> QuizResponse:
    try:
        context = await get_video_context(str(payload.youtube_url), force_refresh=payload.force_refresh)
        summary, _ = await generate_summary(
            context=context,
            api_key=payload.bailian_api_key,
            model=payload.model,
            force_refresh=payload.force_refresh,
        )
        quiz, quiz_cached = await generate_quiz(
            context=context,
            quiz_type=payload.quiz_type,
            difficulty=payload.difficulty,
            exam_name=payload.exam_name,
            custom_quiz_description=payload.custom_quiz_description,
            api_key=payload.bailian_api_key,
            model=payload.model,
            force_refresh=payload.force_refresh,
        )
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TranscriptUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return QuizResponse(
        video=context.video,
        summary=summary,
        quiz_type=payload.quiz_type,
        difficulty=payload.difficulty,
        content_markdown=quiz,
        cached=context.video_cached and quiz_cached,
    )


@app.post("/api/notes/chat", response_model=NotesChatResponse)
async def create_notes_chat(payload: NotesChatRequest) -> NotesChatResponse:
    try:
        history = [ChatMessage.model_validate(item).model_dump() for item in payload.history]
        answer = await ask_notes_question(
            notes_markdown=payload.notes_markdown,
            question=payload.question,
            history=history,
            api_key=payload.bailian_api_key,
            model=payload.model,
            exam_mode=payload.exam_mode,
            exam_name=payload.exam_name,
        )
    except LLMServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return NotesChatResponse(answer=answer)


@app.post("/api/notes/pdf")
async def download_notes_pdf(payload: NotesGenerateRequest) -> StreamingResponse:
    notes_result = await create_notes(payload)
    pdf_bytes = render_document_pdf(
        kind="notes",
        video_title=notes_result.video.title,
        channel=notes_result.video.channel,
        youtube_url=str(notes_result.video.url),
        summary=notes_result.summary,
        content_markdown=notes_result.content_markdown,
        note_style=payload.note_style.value,
    )
    filename = f"notes-{notes_result.video.video_id}-{payload.note_style.value}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/quiz/pdf")
async def download_quiz_pdf(payload: QuizGenerateRequest) -> StreamingResponse:
    quiz_result = await create_quiz(payload)
    pdf_bytes = render_document_pdf(
        kind="quiz",
        video_title=quiz_result.video.title,
        channel=quiz_result.video.channel,
        youtube_url=str(quiz_result.video.url),
        summary=quiz_result.summary,
        content_markdown=quiz_result.content_markdown,
    )
    filename = f"quiz-{quiz_result.video.video_id}-{payload.quiz_type.value}-{payload.difficulty.value}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
