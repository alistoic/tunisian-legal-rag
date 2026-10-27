"""Évaluation du retrieval sur un jeu de questions annotées.

Format de data/eval/questions.jsonl :
{"question": "...", "lang": "fr", "expected_articles": ["88", "89"]}
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from config import settings
from src.retrieval import Retriever

logging.basicConfig(level=logging.WARNING)


def main() -> None:
    path = Path(settings.eval_dir) / "questions.jsonl"
    if not path.exists():
        print(f"Fichier introuvable : {path}")
        return

    items = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
             if line.strip()]

    retriever = Retriever()
    hits = 0
    reciprocal_ranks = []

    for item in items:
        q = item["question"]
        expected = {str(a) for a in item.get("expected_articles", [])}
        k = item.get("k", settings.top_k)

        results = retriever.retrieve(q, top_k=k)
        found = [str(r.metadata.get("article_num", "")) for r in results]
        found = [f.split("-")[0] for f in found]

        hit = bool(expected & set(found))
        hits += hit

        rr = 0.0
        for rank, art in enumerate(found, start=1):
            if art in expected:
                rr = 1.0 / rank
                break
        reciprocal_ranks.append(rr)

        status = "✓" if hit else "✗"
        print(f"{status} {q[:70]:<72} attendu={sorted(expected)} obtenu={found}")

    n = len(items) or 1
    print(f"\nRecall@{settings.top_k} : {hits}/{len(items)} = {hits/n:.1%}")
    print(f"MRR              : {sum(reciprocal_ranks)/n:.3f}")


if __name__ == "__main__":
    main()
