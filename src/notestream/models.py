from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, HttpUrl, model_validator


class NoteStyle(str, Enum):
    CORNELL = "cornell"
    MIND_MAP = "mind_map"
    HIERARCHICAL = "hierarchical"
    CUSTOM = "custom"


class QuizType(str, Enum):
    NONE = "none"
    FLASHCARDS = "flashcards"
    MULTIPLE_CHOICE = "multiple_choice"
    WRITTEN_ANSWERS = "written_answers"
    EXAM_STYLE = "exam_style"
    CROSSWORD = "crossword"
    CUSTOM = "custom"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class VideoMetadata(BaseModel):
    video_id: str
    url: HttpUrl
    title: str
    channel: str
    duration_seconds: int | None = None
    publish_date: str | None = None
    thumbnail: HttpUrl | None = None
    description: str | None = None


class SummaryRequest(BaseModel):
    youtube_url: HttpUrl
    bailian_api_key: str = Field(min_length=10)
    model: str | None = None
    force_refresh: bool = False


class NotesGenerateRequest(SummaryRequest):
    note_style: NoteStyle
    custom_style_description: str | None = None

    @model_validator(mode="after")
    def validate_custom_style(self) -> "NotesGenerateRequest":
        if self.note_style == NoteStyle.CUSTOM and not self.custom_style_description:
            raise ValueError("When note_style is 'custom', custom_style_description is required.")
        return self


class QuizGenerateRequest(SummaryRequest):
    quiz_type: QuizType
    difficulty: Difficulty = Difficulty.MEDIUM
    exam_name: str | None = None
    custom_quiz_description: str | None = None

    @model_validator(mode="after")
    def validate_quiz_requirements(self) -> "QuizGenerateRequest":
        if self.quiz_type in {QuizType.FLASHCARDS, QuizType.CROSSWORD}:
            raise ValueError(
                "Quiz types 'flashcards' and 'crossword' are disabled."
            )
        if self.quiz_type == QuizType.EXAM_STYLE and not self.exam_name:
            raise ValueError("When quiz_type is 'exam_style', exam_name is required.")
        if self.quiz_type == QuizType.CUSTOM and not self.custom_quiz_description:
            raise ValueError(
                "When quiz_type is 'custom', custom_quiz_description is required."
            )
        return self


class SummaryResponse(BaseModel):
    video: VideoMetadata
    summary: str
    transcript_word_count: int
    cached: bool


class NotesResponse(BaseModel):
    video: VideoMetadata
    summary: str
    note_style: NoteStyle
    content_markdown: str
    mind_map_svg: str | None = None
    cached: bool


class QuizResponse(BaseModel):
    video: VideoMetadata
    summary: str
    quiz_type: QuizType
    difficulty: Difficulty
    content_markdown: str
    cached: bool


class ErrorResponse(BaseModel):
    detail: str


class CacheRecord(BaseModel):
    video_id: str
    content_type: str
    style: str
    difficulty: str | None = None
    content_markdown: str
    created_at: datetime
