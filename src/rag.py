"""Orchestrateur RAG : question -> retrieval -> LLM -> réponse citée."""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from config import settings
from .lang import detect_lang, looks_like_derja
from .llm import LLMClient, SYSTEM_PROMPT, build_context_block
from .retrieval import Retriever, RetrievedArticle

log = logging.getLogger(__name__)


@dataclass
class RAGResponse:
    answer: str
    citations: list[dict[str, str]] = field(default_factory=list)
    confidence_note: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)
    reformulated_query: str | None = None
    out_of_corpus: bool = False
    detected_lang: str = "fr"
    is_derja: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class LegalRAG:
    def __init__(self, retriever: Retriever | None = None,
                 llm: LLMClient | None = None):
        self.retriever = retriever or Retriever()
        self._llm = llm  # initialisation paresseuse (clé API optionnelle en test)

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            self._llm = LLMClient()
        return self._llm

    # ------------------------------------------------------------------ #
    def answer(
        self,
        question: str,
        *,
        history: list[dict] | None = None,
        collections: list[str] | None = None,
        top_k: int | None = None,
        include_abrogated: bool = False,
    ) -> RAGResponse:
        question = (question or "").strip()
        if not question:
            return RAGResponse(answer="Veuillez poser une question.",
                               confidence_note="Question vide.")

        detected = detect_lang(question)
        is_derja = looks_like_derja(question)

        # --- Étape 1 : reformulation Derja (contournement documenté) ---
        search_query = question
        reformulated: str | None = None
        if is_derja:
            reformulated = self.llm.reformulate_derja(question)
            search_query = reformulated
            log.info("Derja détecté -> reformulation : %s", reformulated)

        # --- Étape 2 : retrieval ---
        articles = self.retriever.retrieve(
            search_query,
            top_k=top_k,
            collections=collections,
            include_abrogated=include_abrogated,
        )
        out_of_corpus = self.retriever.is_out_of_corpus(articles)

        if not articles:
            return RAGResponse(
                answer=(
                    "Aucun article du corpus indexé ne correspond à cette question. "
                    "Le corpus de démonstration est volontairement restreint : "
                    "consultez le texte officiel au JORT ou un avocat."
                ),
                confidence_note="Aucun contexte récupéré — réponse non générée.",
                out_of_corpus=True,
                detected_lang=detected,
                is_derja=is_derja,
                reformulated_query=reformulated,
            )

        # --- Étape 3 : génération ---
        context = build_context_block(articles)
        try:
            data = self.llm.answer(SYSTEM_PROMPT, context, question, history)
        except Exception as exc:  # noqa: BLE001
            log.error("Génération LLM échouée : %s", exc)
            return RAGResponse(
                answer="La génération de la réponse a échoué. Réessayez.",
                sources=[self._source_dict(a) for a in articles],
                confidence_note="Erreur technique.",
                detected_lang=detected,
                is_derja=is_derja,
                reformulated_query=reformulated,
                error=str(exc),
            )

        citations = data.get("citations") or []
        # Garantit que les citations renvoyées existent bien dans le contexte
        allowed = {
            (a.metadata.get("code", ""), a.metadata.get("article_num", ""))
            for a in articles
        }
        cleaned: list[dict[str, str]] = []
        for c in citations:
            if not isinstance(c, dict):
                continue
            src = str(c.get("source", ""))
            art = str(c.get("article", ""))
            if not src and not art:
                continue
            cleaned.append({
                "source": src, "article": art,
                "url": str(c.get("url", "") or ""),
                "date": str(c.get("date", "") or ""),
            })
        if not cleaned:
            cleaned = [a.citation for a in articles[:3]]

        note = data.get("confidence_note", "")
        if out_of_corpus:
            note = (note + " " if note else "") + (
                "Attention : la similarité des articles récupérés est faible, "
                "la question est peut-être hors du corpus indexé."
            )

        return RAGResponse(
            answer=data.get("answer", "").strip() or "Réponse vide.",
            citations=cleaned,
            confidence_note=note.strip(),
            sources=[self._source_dict(a) for a in articles],
            reformulated_query=reformulated,
            out_of_corpus=out_of_corpus,
            detected_lang=detected,
            is_derja=is_derja,
        )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _source_dict(a: RetrievedArticle) -> dict[str, Any]:
        return {
            "id": a.id,
            "collection": a.collection,
            "code": a.metadata.get("code", ""),
            "article": a.metadata.get("article_label")
                       or a.metadata.get("article_num", ""),
            "statut": a.metadata.get("statut", ""),
            "date": a.metadata.get("date_derniere_maj")
                    or a.metadata.get("date_publication", ""),
            "url": a.metadata.get("source_url", ""),
            "distance": round(a.distance, 4),
            "extrait": a.text[:400],
        }
