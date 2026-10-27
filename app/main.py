"""API FastAPI + service de l'interface."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.schemas import (ChatRequest, ChatResponse, CollectionInfo,
                         CorpusResponse)
from config import settings
from src.rag import LegalRAG
from src.retrieval import Retriever

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("app")

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Assistant Juridique Tunisien",
    description="RAG sur textes de loi tunisiens (ChromaDB + Claude).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_rag: LegalRAG | None = None
_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever


def get_rag() -> LegalRAG:
    global _rag
    if _rag is None:
        _rag = LegalRAG(retriever=get_retriever())
    return _rag


# --------------------------------------------------------------------------- #
@app.get("/api/health")
def health():
    return {"status": "ok", "model": settings.llm_model,
            "embedding_model": settings.embedding_model}


@app.get("/api/corpus", response_model=CorpusResponse)
def corpus():
    try:
        stats = get_retriever().client.list_collections()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"ChromaDB inaccessible : {exc}") from exc
        
    infos = []
    for c in stats:
        name = c if isinstance(c, str) else c.name
        try:
            count = get_retriever().client.get_collection(name).count()
        except Exception:
            count = 0
        infos.append(CollectionInfo(name=name, count=count))
    infos.sort(key=lambda i: i.name)
    return CorpusResponse(collections=infos,
                          total_chunks=sum(i.count for i in infos))


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    if not req.message.strip():
        raise HTTPException(400, "Message vide.")

    rag = get_rag()
    try:
        result = rag.answer(
            req.message,
            history=[t.model_dump() for t in req.history],
            collections=req.collections,
            top_k=req.top_k,
            include_abrogated=req.include_abrogated,
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Erreur pipeline RAG")
        raise HTTPException(500, f"Erreur du pipeline : {exc}") from exc

    return ChatResponse(**result.to_dict())


# --------------------------------------------------------------------------- #
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
