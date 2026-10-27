"""Nettoyage et normalisation (FR + AR)."""
from __future__ import annotations

import re
import unicodedata

# --- Diacritiques arabes (tashkeel) + tatweel ---
_TASHKEEL_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_TATWEEL_RE = re.compile(r"\u0640")
# --- Lettres arabes à normaliser ---
_ALEF_RE = re.compile(r"[\u0622\u0623\u0625\u0671]")   # آ أ إ ٱ -> ا
_YAA_RE = re.compile(r"[\u0649\u06CC]")                 # ى -> ي
_HAMZA_STANDALONE_RE = re.compile(r"\u0621")

# --- Chiffres arabes orientaux -> latins ---
_ARABIC_INDIC = {ord(c): str(i) for i, c in enumerate("٠١٢٣٤٥٦٧٨٩")}
_EXT_ARABIC_INDIC = {ord(c): str(i) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹")}

# --- En-têtes / pieds de page JORT ---
_JORT_NOISE = [
    re.compile(r"^\s*Journal Officiel de la R[ée]publique Tunisienne.*$", re.I | re.M),
    re.compile(r"^\s*Page\s+\d+\s*$", re.I | re.M),
    re.compile(r"^\s*\d+\s*/\s*\d+\s*$", re.M),
    re.compile(r"^\s*الرائد الرسمي للجمهورية التونسية.*$", re.M),
    re.compile(r"^\s*صفحة\s+\d+\s*$", re.M),
    re.compile(r"^\s*[-—_=]{4,}\s*$", re.M),
]

_WS_RE = re.compile(r"[ \t\u00A0\u200B]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def strip_jort_headers(text: str) -> str:
    """Supprime les artefacts d'impression JORT (en-têtes, pieds, folios)."""
    for pattern in _JORT_NOISE:
        text = pattern.sub("", text)
    return text


def clean_text(text: str) -> str:
    """Nettoyage non destructif, appliqué AVANT le découpage en articles.

    Ne touche pas aux lettres arabes : le splitter doit encore pouvoir
    reconnaître « الفصل الأول ».
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = strip_jort_headers(text)
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def normalize_arabic(text: str, *, unify_teh_marbuta: bool = False) -> str:
    """Normalisation arabe appliquée APRÈS le découpage, avant l'embedding."""
    text = unicodedata.normalize("NFKC", text)
    text = _TASHKEEL_RE.sub("", text)
    text = _TATWEEL_RE.sub("", text)
    text = _ALEF_RE.sub("\u0627", text)        # -> ا
    text = _YAA_RE.sub("\u064A", text)         # -> ي
    text = _HAMZA_STANDALONE_RE.sub("", text)
    if unify_teh_marbuta:
        text = text.replace("\u0629", "\u0647")  # ة -> ه
    text = text.translate(_ARABIC_INDIC).translate(_EXT_ARABIC_INDIC)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def normalize_text(text: str, langue: str = "fr") -> str:
    """Point d'entrée unique : normalise selon la langue du document."""
    if langue in ("ar", "bilingue", "mix"):
        return normalize_arabic(text)
    return text.strip()
