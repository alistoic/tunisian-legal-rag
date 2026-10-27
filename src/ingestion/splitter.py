"""Découpage structurel par article de loi (jamais par taille fixe)."""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .cleaner import normalize_text
from .loader import LoadedDocument

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Regex de repérage des articles
# --------------------------------------------------------------------------- #
_FR_ARTICLE = r"(?:ARTICLE|Article|Art\.?)"
_AR_ARTICLE = r"(?:الفصل|المادة)"
_FR_ORD = r"(?:premier|1\s*er|1er)"
#_FR_NUM = r"\d+(?:\s*(?:bis|ter|quater|quinquies))?"
_FR_NUM = r"\d+(?:-\d+)?(?:\s*(?:bis|ter|quater|quinquies))?"
_AR_ORD = r"(?:الأول|الأولى|الوحيد|الثاني|الثالث|الرابع|الخامس|السادس|السابع|الثامن|التاسع|العاشر)"

_ARTICLE_RE = re.compile(
    rf"(?im)^[ \t]*(?P<label>"
    rf"(?:{_FR_ARTICLE})\s*(?:{_FR_ORD}|{_FR_NUM})"
    rf"|(?:{_AR_ARTICLE})\s*(?:{_AR_ORD}|\d+)"
    rf")\s*(?P<sep>[—\-–:.\u2013\u2014]|\s)"
)

_CHAPTER_RE = re.compile(
    r"(?im)^[ \t]*(?P<label>(?:TITRE|Titre|CHAPITRE|Chapitre|SECTION|Section|"
    r"الباب|القسم)\s*[^\n]{0,140})"
)

_AR_ORDINAL_MAP = {
    "الأول": "1", "الأولى": "1", "الوحيد": "1",
    "الثاني": "2", "الثالث": "3", "الرابع": "4", "الخامس": "5",
    "السادس": "6", "السابع": "7", "الثامن": "8", "التاسع": "9",
    "العاشر": "10",
}


@dataclass
class Chunk:
    id: str
    text: str                 # texte normalisé, préfixé pour l'embedding
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_chroma(self) -> tuple[str, str, dict[str, Any]]:
        return self.id, self.text, self.metadata


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[\s_-]+", "_", value).strip("_") or "corpus"


def article_number_from_label(label: str) -> str:
    """'Article 88 bis' -> '88 bis' ; 'الفصل الأول' -> '1' ; 'Article premier' -> '1'."""
    label = label.strip()
    # Arabe : ordinal écrit en toutes lettres
    for word, num in _AR_ORDINAL_MAP.items():
        if word in label:
            return num
    # Français : ordinal écrit en toutes lettres ("premier" / "1er" sans chiffre isolé)
    if re.search(r"(?i)premier\b", label):
        return "1"
    # Chiffres arabes orientaux -> traduits AVANT la recherche ASCII, car \d
    # (Unicode) matcherait sinon ces mêmes chiffres et les renverrait tels quels.
    m = re.search(r"[\u0660-\u0669\u06F0-\u06F9]+", label)
    if m:
        trans = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
        trans.update({ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")})
        return m.group(0).translate(trans)
    # Chiffres ASCII (avec suffixe bis/ter/quater/quinquies éventuel)
    #m = re.search(r"[0-9]+(?:\s*(?:bis|ter|quater|quinquies))?", label, re.I)
    m = re.search(r"[0-9]+(?:-[0-9]+)?(?:\s*(?:bis|ter|quater|quinquies))?", label, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()
    return label


def _make_id(collection: str, article_num: str, langue: str, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{collection}_art_{_slugify(article_num)}_{langue}_{digest}"


def _detect_langue(metadata: dict[str, Any], text: str) -> str:
    declared = str(metadata.get("langue", "")).lower()
    if declared in ("ar", "fr", "bilingue", "mix"):
        return declared
    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"
    return "fr"


# --------------------------------------------------------------------------- #
# Découpage principal
# --------------------------------------------------------------------------- #
def split_document(doc: LoadedDocument, collection: str | None = None) -> list[Chunk]:
    """Découpe un document en chunks = articles (+ chunks de chapitre)."""
    meta = dict(doc.metadata)
    code = meta.get("code", "Code inconnu")
    collection = collection or _slugify(code)
    langue = _detect_langue(meta, doc.text)

    text = doc.text
    matches = list(_ARTICLE_RE.finditer(text))

    if len(matches) < 2:
        # Fallback : pas d'ancrage en début de ligne (extraction PDF capricieuse)
        loose = re.compile(
            rf"(?i)(?P<label>(?:{_FR_ARTICLE})\s*(?:{_FR_ORD}|{_FR_NUM})"
            rf"|(?:{_AR_ARTICLE})\s*(?:{_AR_ORD}|\d+))"
        )
        matches = list(loose.finditer(text))

    if not matches:
        log.warning("Aucun article détecté dans '%s' — chunk unique.", doc.source_path)
        body = normalize_text(text, langue)
        if not body:
            return []
        chunk_meta = _base_metadata(meta, code, collection, langue,
                                    article_num="", type_="document")
        return [Chunk(id=_make_id(collection, "full", langue, body),
                      text=f"[{code}]\n{body}", metadata=chunk_meta)]

    # --- Découpage par article ---
    chapter_marks = list(_CHAPTER_RE.finditer(text))
    chunks: list[Chunk] = []
    seen_articles: set[str] = set()

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        raw_body = text[start:end].strip()
        if not raw_body:
            continue

        label = re.sub(r"\s+", " ", m.group("label")).strip()
        art_num = article_number_from_label(label)
        body = normalize_text(raw_body, langue)

        # Chapitre courant (dernier marqueur avant l'article)
        chapter = ""
        for cm in chapter_marks:
            if cm.start() < start:
                chapter = re.sub(r"\s+", " ", cm.group("label")).strip()
            else:
                break

        # Sous-découpage des articles anormalement longs (> 3500 caractères)
        sub_parts = _split_long_article(body, max_chars=3500)
        for j, part in enumerate(sub_parts):
            suffix = "" if len(sub_parts) == 1 else f" (partie {j + 1}/{len(sub_parts)})"
            prefix = f"[{code} — {label}{suffix}]"
            chunk_text = f"{prefix}\n{part}"

            article_id = art_num if len(sub_parts) == 1 else f"{art_num}-{j + 1}"
            if article_id in seen_articles:
                article_id = f"{article_id}-{j}"
            seen_articles.add(article_id)

            cmeta = _base_metadata(meta, code, collection, langue,
                                   article_num=art_num, type_="article")
            cmeta["article_label"] = label
            cmeta["article_num"] = article_id
            cmeta["chapitre"] = chapter

            chunks.append(Chunk(
                id=_make_id(collection, article_id, langue, chunk_text),
                text=chunk_text,
                metadata=cmeta,
            ))

    # --- Chunks de chapitre (résumés structurels) ---
    chunks.extend(_build_chapter_chunks(
        text, chapter_marks, meta, code, collection, langue
    ))

    log.info("'%s' -> %d chunks (langue=%s)", doc.source_path, len(chunks), langue)
    return chunks


def _base_metadata(meta: dict[str, Any], code: str, collection: str,
                   langue: str, *, article_num: str, type_: str) -> dict[str, Any]:
    """Métadonnées Chroma (valeurs scalaires uniquement, pas de None)."""
    base = {
        "code": code,
        "collection": collection,
        "article_num": article_num,
        "type": type_,
        "langue": langue,
        "statut": meta.get("statut", "en vigueur"),
        "date_publication": meta.get("date_publication", ""),
        "date_derniere_maj": meta.get("date_derniere_maj", ""),
        "source_url": meta.get("source_url", ""),
        "source_file": meta.get("source_file", ""),
        "article_label": meta.get("article_label", ""),
        "chapitre": meta.get("chapitre", ""),
    }
    return {k: v for k, v in base.items() if v is not None}


def _split_long_article(body: str, max_chars: int = 3500) -> list[str]:
    """Découpe un article trop long, sans jamais perdre le contexte de citation."""
    if len(body) <= max_chars:
        return [body]
    paragraphs = [p for p in body.split("\n") if p.strip()]
    parts, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) + 1 > max_chars and current:
            parts.append(current.strip())
            current = p
        else:
            current = f"{current}\n{p}" if current else p
    if current.strip():
        parts.append(current.strip())
    return parts or [body]


def _build_chapter_chunks(text: str, chapter_marks: list[re.Match],
                          meta: dict[str, Any], code: str, collection: str,
                          langue: str) -> list[Chunk]:
    """Un chunk par chapitre : intitulé + liste des articles qu'il contient."""
    if not chapter_marks:
        return []
    out: list[Chunk] = []
    for i, cm in enumerate(chapter_marks):
        start = cm.start()
        end = chapter_marks[i + 1].start() if i + 1 < len(chapter_marks) else len(text)
        segment = text[start:end]
        heading = re.sub(r"\s+", " ", cm.group("label")).strip()
        arts = [article_number_from_label(m.group("label"))
                for m in _ARTICLE_RE.finditer(segment)]
        if not arts:
            continue
        body = normalize_text(heading, langue)
        listing = ", ".join(dict.fromkeys(arts))
        chunk_text = (f"[{code} — {heading}]\n"
                      f"Ce chapitre regroupe les articles : {listing}.")
        cmeta = _base_metadata(meta, code, collection, langue,
                               article_num="", type_="chapitre")
        cmeta["chapitre"] = heading
        cmeta["articles_list"] = listing
        out.append(Chunk(
            id=_make_id(collection, f"chap{i}", langue, chunk_text),
            text=chunk_text, metadata=cmeta,
        ))
    return out
