"""Indexation dans ChromaDB (une collection par corpus)."""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Iterable

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings
from .loader import LoadedDocument, load_directory
from .splitter import Chunk, _slugify, split_document
from ..retrieval.embeddings import embed_documents

log = logging.getLogger(__name__)


class Indexer:
    def __init__(self, persist_dir: str | None = None):
        self.persist_dir = str(persist_dir or settings.chroma_dir)
        self.client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

    # ------------------------------------------------------------------ #
    #def list_collections(self) -> list[str]:
        #return sorted(c.name for c in self.client.list_collections())
        
    def list_collections(self) -> list[str]:
        raw = self.client.list_collections()
        names = [c if isinstance(c, str) else c.name for c in raw]
        return sorted(names)

    def reset(self, names: Iterable[str] | None = None) -> None:
        targets = list(names) if names else self.list_collections()
        for name in targets:
            try:
                self.client.delete_collection(name)
                log.info("Collection supprimée : %s", name)
            except Exception:  # noqa: BLE001
                pass

    def _get_collection(self, name: str):
        return self.client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine", "description": f"Corpus {name}"},
        )

    # ------------------------------------------------------------------ #
    def index_documents(self, docs: list[LoadedDocument]) -> dict[str, int]:
        """Découpe, vectorise et stocke. Retourne {collection: nb_chunks}."""
        by_collection: dict[str, list[Chunk]] = defaultdict(list)

        for doc in docs:
            collection = _slugify(str(doc.metadata.get("code", "corpus")))
            chunks = split_document(doc, collection=collection)
            by_collection[collection].extend(chunks)

        stats: dict[str, int] = {}
        for collection_name, chunks in by_collection.items():
            if not chunks:
                continue
            coll = self._get_collection(collection_name)

            texts = [c.text for c in chunks]
            embeddings = embed_documents(texts)

            coll.add(
                ids=[c.id for c in chunks],
                documents=texts,
                metadatas=[c.metadata for c in chunks],
                embeddings=embeddings,
            )
            stats[collection_name] = len(chunks)
            log.info("Collection '%s' : %d chunks indexés", collection_name, len(chunks))
        return stats

    def index_directory(self, directory: str | None = None,
                        reset: bool = False,
                        only: list[str] | None = None) -> dict[str, int]:
        directory = directory or str(settings.raw_dir)
        docs = load_directory(directory)

        if only:
            keep = {_slugify(o) for o in only}
            docs = [d for d in docs
                    if _slugify(str(d.metadata.get("code", ""))) in keep]

        if reset:
            collections = {_slugify(str(d.metadata.get("code", ""))) for d in docs}
            self.reset(collections)

        return self.index_documents(docs)

    # ------------------------------------------------------------------ #
    def stats(self) -> list[dict]:
        out = []
        for name in self.list_collections():
            coll = self.client.get_collection(name)
            out.append({"collection": name, "count": coll.count()})
        return out
