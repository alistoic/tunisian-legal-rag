"""Retrieval hybride : similarité vectorielle + filtres métadonnées."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings
from ..lang import detect_lang
from .embeddings import embed_query

log = logging.getLogger(__name__)


@dataclass
class RetrievedArticle:
    id: str
    text: str
    metadata: dict[str, Any]
    distance: float
    collection: str
    rerank_score: float | None = field(default=None, compare=False)

    @property
    def score(self) -> float:
        """Plus petit = plus pertinent (distance cosinus)."""
        return self.distance

    @property
    def citation(self) -> dict[str, str]:
        label = self.metadata.get("article_label") or self.metadata.get("article_num", "")
        return {
            "source": str(self.metadata.get("code", "")),
            "article": str(label),
            "url": str(self.metadata.get("source_url", "")),
            "statut": str(self.metadata.get("statut", "")),
            "date": str(self.metadata.get("date_derniere_maj")
                        or self.metadata.get("date_publication", "")),
        }


def _build_where(status: str | None, collections_langue: list[str] | None = None
                 ) -> dict | None:
    clauses: list[dict] = []
    if status:
        clauses.append({"statut": status})
    if collections_langue:
        clauses.append({"langue": {"$in": collections_langue}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


class Retriever:
    def __init__(self, persist_dir: str | None = None):
        self.client = chromadb.PersistentClient(
            path=str(persist_dir or settings.chroma_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    # ------------------------------------------------------------------ #
    #def collections(self) -> list[str]:
       # return sorted(c.name for c in self.client.list_collections())
        
    def collections(self) -> list[str]:
        raw = self.client.list_collections()
        names = [c if isinstance(c, str) else c.name for c in raw]
        return sorted(names)

    def _query_one(self, name: str, vector: list[float], n: int,
                   where: dict | None) -> list[RetrievedArticle]:
        try:
            coll = self.client.get_collection(name)
        except Exception:  # noqa: BLE001
            return []
        if coll.count() == 0:
            return []
        try:
            res = coll.query(
                query_embeddings=[vector],
                n_results=min(n, coll.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Query échouée sur '%s' : %s", name, exc)
            return []

        out: list[RetrievedArticle] = []
        for doc, meta, dist, cid in zip(
            res["documents"][0], res["metadatas"][0],
            res["distances"][0], res["ids"][0],
        ):
            out.append(RetrievedArticle(
                id=cid, text=doc, metadata=meta or {},
                distance=float(dist), collection=name,
            ))
        return out

    # ------------------------------------------------------------------ #
    """
    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        collections: list[str] | None = None,
        statut: str | None = None,
        prefer_langue: bool | None = None,
        include_abrogated: bool = False,
    ) -> list[RetrievedArticle]:
        top_k = top_k or settings.top_k
        target_collections = collections or self.collections()
        if not target_collections:
            return []

        statut_filter = None if include_abrogated else (statut or settings.default_status)
        vector = embed_query(query)

        # 1er passage : filtre langue si activé (et si la requête est monolingue)
        langue_filter = None
        if prefer_langue is None:
            qlang = detect_lang(query)
            if qlang in ("ar", "fr"):
                langue_filter = [qlang, "bilingue", "mix"]

        where = _build_where(statut_filter, langue_filter)
        results: list[RetrievedArticle] = []
        for name in target_collections:
            results.extend(self._query_one(name, vector, top_k * 2, where))

        # Repli : pas assez de résultats -> on retire le filtre langue
        if langue_filter and len(results) < max(2, top_k // 2):
            log.info("Repli sans filtre de langue (seulement %d résultats)", len(results))
            where = _build_where(statut_filter, None)
            results = []
            for name in target_collections:
                results.extend(self._query_one(name, vector, top_k * 2, where))

        # Dédoublonnage (même article FR/AR indexé deux fois)
        seen: set[str] = set()
        deduped: list[RetrievedArticle] = []
        for art in sorted(results, key=lambda a: a.distance):
            key = f"{art.metadata.get('code')}::{art.metadata.get('article_num')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(art)

        # Reranking optionnel
        if settings.enable_rerank and len(deduped) > top_k:
            from .reranker import rerank
            return rerank(query, deduped, top_k)

        return deduped[:top_k]
        """
        # ------------------------------------------------------------------ #
    def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        collections: list[str] | None = None,
        statut: str | None = None,
        prefer_langue: bool | None = None,
        include_abrogated: bool = False,
    ) -> list[RetrievedArticle]:
        top_k = top_k or settings.top_k
        target_collections = collections or self.collections()
        if not target_collections:
            return []

        statut_filter = None if include_abrogated else (statut or settings.default_status)
        vector = embed_query(query)

        # Détection de langue de la requête : sert à ordonner les résultats,
        # jamais à les exclure. Un modèle d'embedding multilingue peut très
        # bien faire correspondre une question en arabe à un article en
        # français (et inversement) — restreindre par langue avant la
        # recherche masquerait ces correspondances valides, surtout sur un
        # corpus déséquilibré où peu de textes existent dans les deux langues.
        langue_filter = None
        if prefer_langue is None:
            qlang = detect_lang(query)
            if qlang in ("ar", "fr"):
                langue_filter = [qlang, "bilingue", "mix"]

        where_all = _build_where(statut_filter, None)
        results: list[RetrievedArticle] = []
        for name in target_collections:
            results.extend(self._query_one(name, vector, top_k * 2, where_all))

        # Dédoublonnage (même article FR/AR indexé deux fois, ou même article
        # retrouvé par plusieurs sous-parties) — on garde la meilleure distance.
        seen: set[str] = set()
        deduped: list[RetrievedArticle] = []
        for art in sorted(results, key=lambda a: a.distance):
            key = f"{art.metadata.get('code')}::{art.metadata.get('article_num')}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(art)

        # À distance égale (à une petite marge près), on préfère un article
        # dans la langue de la question — sans jamais l'imposer au détriment
        # d'un bien meilleur score dans l'autre langue.
        if langue_filter:
            preferred = set(langue_filter)
            margin = 0.05
            deduped.sort(key=lambda a: (round(a.distance / margin), 0
                                        if a.metadata.get("langue") in preferred else 1,
                                        a.distance))

        # Reranking optionnel
        if settings.enable_rerank and len(deduped) > top_k:
            from .reranker import rerank
            return rerank(query, deduped, top_k)

        return deduped[:top_k]

    # ------------------------------------------------------------------ #
    def is_out_of_corpus(self, articles: list[RetrievedArticle]) -> bool:
        if not articles:
            return True
        return min(a.distance for a in articles) > settings.max_distance
