"""CLI de test : python -m scripts.query "ma question" """
from __future__ import annotations

import argparse
import json
import logging

from src.rag import LegalRAG

logging.basicConfig(level=logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("question", nargs="+")
    parser.add_argument("--no-llm", action="store_true",
                        help="Affiche seulement les articles récupérés.")
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()

    question = " ".join(args.question)
    rag = LegalRAG()

    if args.no_llm:
        arts = rag.retriever.retrieve(question, top_k=args.top_k)
        for a in arts:
            print(f"[{a.distance:.4f}] {a.metadata.get('code')} "
                  f"— {a.metadata.get('article_label')} ({a.collection})")
            print(f"    {a.text[:180].replace(chr(10), ' ')}…\n")
        return

    result = rag.answer(question, top_k=args.top_k)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
