"""Embeddings multilingues (singleton paresseux)."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Sequence

from config import settings

log = logging.getLogger(__name__)
_model = None


def get_model():
    """Charge (une seule fois) le modèle Sentence-Transformers."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        log.info("Chargement du modèle d'embedding : %s", settings.embedding_model)
        _model = SentenceTransformer(settings.embedding_model)
    return _model


def embed_documents(texts: Sequence[str], batch_size: int = 32) -> list[list[float]]:
    model = get_model()
    vectors = model.encode(
        list(texts),
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=len(texts) > 64,
        convert_to_numpy=True,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    model = get_model()
    return model.encode(text, normalize_embeddings=True,
                        convert_to_numpy=True).tolist()
