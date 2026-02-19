from __future__ import annotations

import asyncio

import typer
from loguru import logger
from rich.console import Console
from rich.markdown import Markdown

from notestream.models import Difficulty, NoteStyle, QuizType
from notestream.services import (
    generate_notes,
    generate_quiz,
    generate_summary,
    get_video_context,
)

app = typer.Typer(help="NoteStream CLI")
console = Console()


@app.command()
def summary(
    youtube_url: str = typer.Argument(..., help="YouTube URL"),
    bailian_api_key: str = typer.Option(..., "--api-key", help="Bailian API key"),
    model: str | None = typer.Option(None, help="Model name"),
) -> None:
    async def _run() -> None:
        context = await get_video_context(youtube_url)
        summary_text, _ = await generate_summary(
            context=context,
            api_key=bailian_api_key,
            model=model,
            force_refresh=False,
        )
        console.print(f"[bold]{context.video.title}[/bold]")
        console.print(Markdown(summary_text))

    asyncio.run(_run())


@app.command()
def notes(
    youtube_url: str = typer.Argument(..., help="YouTube URL"),
    style: NoteStyle = typer.Option(NoteStyle.HIERARCHICAL, "--style", case_sensitive=False),
    bailian_api_key: str = typer.Option(..., "--api-key", help="Bailian API key"),
    custom_style_description: str | None = typer.Option(None, "--custom-style"),
    model: str | None = typer.Option(None, help="Model name"),
) -> None:
    async def _run() -> None:
        context = await get_video_context(youtube_url)
        notes_text, _ = await generate_notes(
            context=context,
            note_style=style,
            custom_style_description=custom_style_description,
            api_key=bailian_api_key,
            model=model,
            force_refresh=False,
        )
        console.print(Markdown(notes_text))

    asyncio.run(_run())


@app.command()
def quiz(
    youtube_url: str = typer.Argument(..., help="YouTube URL"),
    quiz_type: QuizType = typer.Option(QuizType.MULTIPLE_CHOICE, "--quiz-type", case_sensitive=False),
    difficulty: Difficulty = typer.Option(Difficulty.MEDIUM, "--difficulty", case_sensitive=False),
    bailian_api_key: str = typer.Option(..., "--api-key", help="Bailian API key"),
    exam_name: str | None = typer.Option(None, "--exam-name"),
    custom_quiz_description: str | None = typer.Option(None, "--custom-quiz"),
    model: str | None = typer.Option(None, help="Model name"),
) -> None:
    async def _run() -> None:
        context = await get_video_context(youtube_url)
        quiz_text, _ = await generate_quiz(
            context=context,
            quiz_type=quiz_type,
            difficulty=difficulty,
            exam_name=exam_name,
            custom_quiz_description=custom_quiz_description,
            api_key=bailian_api_key,
            model=model,
            force_refresh=False,
        )
        console.print(Markdown(quiz_text))

    asyncio.run(_run())


@app.command()
def serve(host: str = "0.0.0.0", port: int = 8000, reload: bool = True) -> None:
    """Start FastAPI server."""
    import uvicorn

    logger.info("Starting API at http://{}:{}", host, port)
    uvicorn.run("notestream.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
