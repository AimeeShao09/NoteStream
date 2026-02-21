from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from loguru import logger
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)
from yt_dlp import YoutubeDL

from notestream.db import get_cache_store
from notestream.models import Difficulty, NoteStyle, QuizType, VideoMetadata
from notestream.prompts import NOTE_PROMPTS, QUIZ_PROMPTS, SUMMARY_PROMPT

BAILIAN_CHAT_COMPLETIONS_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DEFAULT_MODEL = os.getenv("NOTESTREAM_DEFAULT_MODEL", "qwen3.5-plus")


class ServiceError(Exception):
    """Base service error."""


class InvalidYouTubeUrlError(ServiceError):
    """Invalid youtube URL."""


class TranscriptUnavailableError(ServiceError):
    """Transcript cannot be retrieved."""


class LLMServiceError(ServiceError):
    """LLM API call failed."""


@dataclass
class VideoContext:
    video: VideoMetadata
    transcript: str
    video_cached: bool


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if hostname in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/")
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
            return candidate

    if hostname.endswith("youtube.com"):
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
                return candidate
        if parsed.path.startswith("/shorts/"):
            candidate = parsed.path.split("/")[2]
            if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate):
                return candidate

    raise InvalidYouTubeUrlError("Only standard YouTube video URLs are supported.")


async def fetch_video_metadata(url: str) -> dict[str, Any]:
    def _from_yt_dlp() -> dict[str, Any]:
        with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.to_thread(_from_yt_dlp)
        upload_date_raw = info.get("upload_date")
        publish_date = None
        if upload_date_raw and len(upload_date_raw) == 8:
            publish_date = datetime.strptime(upload_date_raw, "%Y%m%d").date().isoformat()

        return {
            "title": info.get("title") or "Untitled Video",
            "channel": info.get("channel") or info.get("uploader") or "Unknown Channel",
            "duration_seconds": info.get("duration"),
            "publish_date": publish_date,
            "thumbnail": info.get("thumbnail"),
            "description": info.get("description"),
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("yt-dlp metadata fetch failed: {}", exc)

    oembed_url = "https://www.youtube.com/oembed"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(oembed_url, params={"url": url, "format": "json"})
    if resp.status_code >= 400:
        raise ServiceError("The video may be unavailable, private, or invalid.")

    data = resp.json()
    return {
        "title": data.get("title") or "Untitled Video",
        "channel": data.get("author_name") or "Unknown Channel",
        "duration_seconds": None,
        "publish_date": None,
        "thumbnail": data.get("thumbnail_url"),
        "description": None,
    }


async def fetch_transcript(video_id: str) -> str:
    def _extract_text(rows: Any) -> str:
        chunks: list[str] = []
        for row in rows:
            if isinstance(row, dict):
                text = row.get("text", "")
            else:
                text = getattr(row, "text", "")
            cleaned = re.sub(r"\s+", " ", text).strip()
            if cleaned:
                chunks.append(cleaned)
        return " ".join(chunks).strip()

    def _load_transcript() -> str:
        api = YouTubeTranscriptApi()
        preferred_codes = ["en", "en-US", "en-GB"]

        # youtube-transcript-api >=1.x
        if hasattr(api, "fetch"):
            try:
                rows = api.fetch(video_id, languages=preferred_codes)
                text = _extract_text(rows)
                if text:
                    return text
            except NoTranscriptFound:
                pass

        # Fallback path compatible with both old/new versions.
        if hasattr(api, "list"):
            transcript_list = api.list(video_id)
        elif hasattr(YouTubeTranscriptApi, "list_transcripts"):
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        else:
            raise TranscriptUnavailableError(
                "This video has no available captions. Please try a different video."
            )

        for code in preferred_codes:
            try:
                rows = transcript_list.find_transcript([code]).fetch()
                text = _extract_text(rows)
                if text:
                    return text
            except Exception:  # noqa: BLE001
                continue

        # Last fallback: use any available caption track.
        for transcript in transcript_list:
            try:
                rows = transcript.fetch()
                text = _extract_text(rows)
                if text:
                    return text
            except Exception:  # noqa: BLE001
                continue

        raise TranscriptUnavailableError(
            "This video has no available captions. Please try a different video."
        )

    try:
        transcript = await asyncio.to_thread(_load_transcript)
    except (TranscriptsDisabled, VideoUnavailable, CouldNotRetrieveTranscript):
        raise TranscriptUnavailableError(
            "This video has no available captions. Please try a different video."
        ) from None
    except TranscriptUnavailableError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Transcript fetch failed: {}", exc)
        raise TranscriptUnavailableError(
            "This video has no available captions. Please try a different video."
        ) from exc

    if not transcript:
        raise TranscriptUnavailableError(
            "This video has no available captions. Please try a different video."
        )
    return transcript


async def get_video_context(youtube_url: str, force_refresh: bool = False) -> VideoContext:
    video_id = extract_video_id(youtube_url)
    cache = get_cache_store(os.getenv("NOTESTREAM_DB_PATH"))

    cached_row = None if force_refresh else cache.get_video(video_id)
    if cached_row:
        video = VideoMetadata(
            video_id=video_id,
            url=cached_row["url"],
            title=cached_row["title"],
            channel=cached_row["channel"],
            duration_seconds=cached_row["duration_seconds"],
            publish_date=cached_row["publish_date"],
            thumbnail=cached_row["thumbnail"],
            description=cached_row["description"],
        )
        return VideoContext(video=video, transcript=cached_row["transcript"], video_cached=True)

    metadata = await fetch_video_metadata(youtube_url)
    transcript = await fetch_transcript(video_id)

    cache.upsert_video(
        {
            "video_id": video_id,
            "url": youtube_url,
            "title": metadata["title"],
            "channel": metadata["channel"],
            "duration_seconds": metadata["duration_seconds"],
            "publish_date": metadata["publish_date"],
            "thumbnail": metadata["thumbnail"],
            "description": metadata["description"],
            "transcript": transcript,
        }
    )

    video = VideoMetadata(video_id=video_id, url=youtube_url, **metadata)
    return VideoContext(video=video, transcript=transcript, video_cached=False)


async def call_bailian(prompt: str, api_key: str, model: str | None = None) -> str:
    messages = [
        {
            "role": "system",
            "content": "You produce factual, structured study content in Markdown.",
        },
        {"role": "user", "content": prompt},
    ]
    return await call_bailian_messages(messages=messages, api_key=api_key, model=model)


async def call_bailian_messages(
    *,
    messages: list[dict[str, str]],
    api_key: str,
    model: str | None = None,
) -> str:
    if not api_key:
        raise LLMServiceError("Bailian API key is required.")

    payload = {
        "model": model or DEFAULT_MODEL,
        "messages": messages,
        "temperature": 0.3,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(BAILIAN_CHAT_COMPLETIONS_URL, headers=headers, json=payload)

    if response.status_code >= 400:
        try:
            detail = response.json()
        except Exception:  # noqa: BLE001
            detail = response.text
        raise LLMServiceError(f"Bailian call failed: {detail}")

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:  # noqa: BLE001
        raise LLMServiceError("Invalid response structure from Bailian API.") from exc


async def ask_notes_question(
    *,
    notes_markdown: str,
    question: str,
    history: list[dict[str, str]],
    api_key: str,
    model: str | None,
    exam_mode: bool = False,
    exam_name: str | None = None,
) -> str:
    system_prompt = """
You are an expert tutor teaching a high-school student.

Goals:
- Explain clearly, accurately, and patiently.
- Use the provided video notes/context as your primary source.
- You may extend beyond the video when helpful, especially to fill background knowledge, give intuition, or provide better examples.

Style requirements:
- Use simple language first, then add technical detail if needed.
- Break explanations into small steps.
- Define jargon the first time you use it.
- Prefer concrete examples and analogies relevant to high-school learners.
- Keep a supportive, professional tone.

Grounding rules:
- Do not invent claims about what the video said.
- If something is from the notes/video, present it as "From the notes".
- If something goes beyond the notes/video, label it as "Beyond the video".
- If uncertain, say so clearly and provide the most likely explanation.

Response format:
1) Direct answer (1-3 sentences)
2) Step-by-step explanation
3) Example
4) Quick check question for the student
""".strip()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
    ]

    context_chunks = [f"Study notes context:\n\n{notes_markdown}"]
    if exam_mode and exam_name:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Exam mode is enabled. Adapt explanations to the target exam or competition and "
                    "incorporate likely syllabus scope, question styles, and scoring expectations. "
                    "If exact official details are uncertain, state assumptions explicitly."
                ),
            }
        )
        context_chunks.append(f"Target exam or competition: {exam_name}")

    messages.append({"role": "user", "content": "\n\n".join(context_chunks)})
    messages.extend(history)
    messages.append({"role": "user", "content": question})
    return await call_bailian_messages(messages=messages, api_key=api_key, model=model)


async def _get_or_generate_artifact(
    *,
    video_id: str,
    artifact_type: str,
    style: str,
    difficulty: str | None,
    payload: dict[str, Any],
    force_refresh: bool,
    producer: Any,
) -> tuple[str, bool]:
    cache = get_cache_store(os.getenv("NOTESTREAM_DB_PATH"))
    payload_hash = cache.payload_hash(payload)

    if not force_refresh:
        cached_row = cache.get_artifact(video_id, artifact_type, style, difficulty, payload_hash)
        if cached_row:
            return cached_row["content"], True

    content = await producer()
    cache.put_artifact(
        video_id=video_id,
        artifact_type=artifact_type,
        style=style,
        difficulty=difficulty,
        payload_hash=payload_hash,
        content=content,
    )
    return content, False


async def generate_summary(
    *,
    context: VideoContext,
    api_key: str,
    model: str | None,
    force_refresh: bool,
) -> tuple[str, bool]:
    prompt = SUMMARY_PROMPT.format(
        title=context.video.title,
        channel=context.video.channel,
        transcript=context.transcript,
    )

    return await _get_or_generate_artifact(
        video_id=context.video.video_id,
        artifact_type="summary",
        style="auto",
        difficulty=None,
        payload={"model": model or DEFAULT_MODEL},
        force_refresh=force_refresh,
        producer=lambda: call_bailian(prompt, api_key=api_key, model=model),
    )


async def generate_notes(
    *,
    context: VideoContext,
    note_style: NoteStyle,
    custom_style_description: str | None,
    api_key: str,
    model: str | None,
    force_refresh: bool,
) -> tuple[str, bool]:
    template = NOTE_PROMPTS[note_style]
    prompt = template.format(
        title=context.video.title,
        channel=context.video.channel,
        transcript=context.transcript,
        custom_style_description=custom_style_description or "",
    )

    payload = {
        "model": model or DEFAULT_MODEL,
        "style": note_style.value,
        "custom": custom_style_description or "",
    }
    return await _get_or_generate_artifact(
        video_id=context.video.video_id,
        artifact_type="notes",
        style=note_style.value,
        difficulty=None,
        payload=payload,
        force_refresh=force_refresh,
        producer=lambda: call_bailian(prompt, api_key=api_key, model=model),
    )


async def generate_quiz(
    *,
    context: VideoContext,
    quiz_type: QuizType,
    difficulty: Difficulty,
    exam_name: str | None,
    custom_quiz_description: str | None,
    api_key: str,
    model: str | None,
    force_refresh: bool,
) -> tuple[str, bool]:
    if quiz_type == QuizType.NONE:
        return "# Quiz Skipped\n\nUser chose not to generate a quiz.", False
    if quiz_type in {QuizType.FLASHCARDS, QuizType.CROSSWORD}:
        raise ServiceError("Quiz types 'flashcards' and 'crossword' are disabled.")

    template = QUIZ_PROMPTS[quiz_type]
    prompt = template.format(
        title=context.video.title,
        channel=context.video.channel,
        transcript=context.transcript,
        difficulty=difficulty.value,
        exam_name=exam_name or "",
        custom_quiz_description=custom_quiz_description or "",
    )

    payload = {
        "model": model or DEFAULT_MODEL,
        "quiz_type": quiz_type.value,
        "difficulty": difficulty.value,
        "exam_name": exam_name or "",
        "custom": custom_quiz_description or "",
    }
    return await _get_or_generate_artifact(
        video_id=context.video.video_id,
        artifact_type="quiz",
        style=quiz_type.value,
        difficulty=difficulty.value,
        payload=payload,
        force_refresh=force_refresh,
        producer=lambda: call_bailian(prompt, api_key=api_key, model=model),
    )
