"""Reranking optionnel via cross-encoder multilingue."""
from __future__ import annotations

import logging
from typing import Sequence

from config import settings

log = logging.getLogger(__name__)
_reranker = None


def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        log.info("Chargement du reranker : %s", settings.rerank_model)
        _reranker = CrossEncoder(settings.rerank_model)
    return _reranker


def rerank(query: str, candidates: Sequence, top_k: int) -> list:
    """candidates : objets avec .text ; renvoie les top_k réordonnés."""
    if not candidates:
        return []
    model = _get_reranker()
    pairs = [(query, c.text) for c in candidates]
    scores = model.predict(pairs)
    ranked = sorted(zip(candidates, scores), key=lambda x: float(x[1]), reverse=True)
    for cand, score in ranked:
        cand.rerank_score = float(score)
    return [c for c, _ in ranked[:top_k]]
