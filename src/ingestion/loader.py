"""Chargement des sources : PDF, HTML, TXT/MD (avec front-matter)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SUPPORTED_EXT = {".pdf", ".html", ".htm", ".txt", ".md"}


@dataclass
class LoadedDocument:
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    source_path: str = ""


# --------------------------------------------------------------------------- #
# Front-matter (--- clé: valeur ---)
# --------------------------------------------------------------------------- #
def _parse_front_matter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.lstrip().startswith("---"):
        return {}, raw
    body = raw.lstrip()
    end = body.find("\n---", 3)
    if end == -1:
        return {}, raw
    header = body[3:end].strip()
    content = body[end + 4:].lstrip("\n")

    meta: dict[str, Any] = {}
    for line in header.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value.lower() in ("true", "false"):
            meta[key] = value.lower() == "true"
        else:
            meta[key] = value
    return meta, content


# --------------------------------------------------------------------------- #
# Extracteurs
# --------------------------------------------------------------------------- #
def _load_pdf(path: Path) -> str:
    """Essaie pymupdf, retombe sur pdfplumber (meilleur sur du bilingue)."""
    try:
        import fitz  # pymupdf
        parts = []
        with fitz.open(path) as doc:
            for page in doc:
                parts.append(page.get_text("text"))
        text = "\n".join(parts)
        if text.strip():
            return text
        log.warning("pymupdf n'a rien extrait de %s, fallback pdfplumber", path)
    except Exception as exc:  # noqa: BLE001
        log.warning("pymupdf a échoué sur %s (%s)", path, exc)

    import pdfplumber
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _load_html(path: Path) -> str:
    from bs4 import BeautifulSoup
    raw = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return soup.get_text("\n")


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


_EXTRACTORS = {".pdf": _load_pdf, ".html": _load_html, ".htm": _load_html,
               ".txt": _load_text, ".md": _load_text}


def load_file(path: str | Path) -> LoadedDocument:
    path = Path(path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXT:
        raise ValueError(f"Extension non supportée : {ext} ({path})")

    raw = _EXTRACTORS[ext](path)
    meta, text = _parse_front_matter(raw)

    meta.setdefault("source_file", path.name)
    meta.setdefault("code", path.stem.replace("_", " ").title())
    meta.setdefault("langue", "fr")
    meta.setdefault("statut", "en vigueur")

    return LoadedDocument(text=text, metadata=meta, source_path=str(path))


def load_directory(directory: str | Path) -> list[LoadedDocument]:
    directory = Path(directory)
    docs: list[LoadedDocument] = []
    for path in sorted(directory.rglob("*")):
        if path.suffix.lower() in SUPPORTED_EXT and path.is_file():
            try:
                docs.append(load_file(path))
                log.info("Chargé : %s", path.name)
            except Exception as exc:  # noqa: BLE001
                log.error("Échec du chargement de %s : %s", path, exc)
    return docs
