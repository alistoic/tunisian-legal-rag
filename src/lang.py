"""Détection de langue + heuristique Derja (tunisien)."""
from __future__ import annotations

import re

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_LATIN_RE = re.compile(r"[A-Za-z]")

# Marqueurs typiques du Derja tunisien (arabe dialectal + arabizi)
_DERJA_MARKERS = [
    # arabe dialectal
    "شنوة", "شني", "شنو", "كيفاش", "كيفاش", "علاش", "قداش", "وقتاش",
    "برشا", "برشة", "باهي", "نحب", "فمّا", "فما", "خدمة", "فلوس",
    "الراجل", "المرا", "توّا", "توا", "هكّا", "هكا", "أمّا", "ياخي",
    # arabizi (translittération latine)
    "chnowa", "chnou", "chneya", "kifech", "kifach", "3lech", "3lech",
    "9adech", "9addech", "wa9tech", "barsha", "barcha", "behi", "behi",
    "n7eb", "nheb", "5edma", "khidma", "flous", "3andek", "3andi",
    "3andna", "mahich", "mouch", "yezzi", "wakha"
]
_ARABIZI_DIGIT_RE = re.compile(r"\b\w*[2379]\w*\b", re.IGNORECASE)


def detect_lang(text: str) -> str:
    """Retourne 'ar', 'fr' ou 'mix'."""
    has_ar = bool(_ARABIC_RE.search(text))
    has_lat = bool(_LATIN_RE.search(text))
    if has_ar and has_lat:
        return "mix"
    if has_ar:
        return "ar"
    return "fr"


def looks_like_derja(text: str) -> bool:
    """Heuristique volontairement simple : mots-clés + arabizi."""
    low = text.lower()
    if any(m in low for m in _DERJA_MARKERS):
        return True
    # arabizi : présence de chiffres 2/3/7/9 collés à des lettres latines
    if _LATIN_RE.search(text) and _ARABIZI_DIGIT_RE.search(text):
        return True
    return False
