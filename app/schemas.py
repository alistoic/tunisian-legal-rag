from __future__ import annotations

from pydantic import BaseModel, Field


class HistoryTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryTurn] = Field(default_factory=list)
    collections: list[str] | None = None
    top_k: int | None = None
    include_abrogated: bool = False


class Citation(BaseModel):
    source: str = ""
    article: str = ""
    url: str = ""
    date: str = ""


class SourceOut(BaseModel):
    id: str
    collection: str
    code: str
    article: str
    statut: str
    date: str
    url: str
    distance: float
    extrait: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    confidence_note: str = ""
    sources: list[SourceOut] = []
    reformulated_query: str | None = None
    out_of_corpus: bool = False
    detected_lang: str = "fr"
    is_derja: bool = False
    error: str | None = None


class CollectionInfo(BaseModel):
    name: str
    count: int


class CorpusResponse(BaseModel):
    collections: list[CollectionInfo]
    total_chunks: int
