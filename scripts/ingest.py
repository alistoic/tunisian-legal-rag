"""CLI d'ingestion : python -m scripts.ingest [--reset] [--only code_travail]"""
from __future__ import annotations

import argparse
import logging

from config import settings
#from src.ingestion import Indexer
from src.ingestion.indexer import Indexer

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)-7s | %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexation du corpus juridique.")
    parser.add_argument("--dir", default=str(settings.raw_dir),
                        help="Répertoire des sources (PDF/HTML/TXT).")
    parser.add_argument("--reset", action="store_true",
                        help="Supprime les collections avant réindexation.")
    parser.add_argument("--only", nargs="*", default=None,
                        help="Limiter à certaines collections.")
    parser.add_argument("--stats", action="store_true",
                        help="Affiche uniquement les statistiques.")
    args = parser.parse_args()

    indexer = Indexer()

    if args.stats:
        for s in indexer.stats():
            print(f"  {s['collection']:<28} {s['count']:>6} chunks")
        return

    stats = indexer.index_directory(args.dir, reset=args.reset, only=args.only)

    print("\n=== Indexation terminée ===")
    for name, count in sorted(stats.items()):
        print(f"  {name:<28} {count:>6} chunks")
    print(f"  {'TOTAL':<28} {sum(stats.values()):>6} chunks")


if __name__ == "__main__":
    main()
