"""Crawler de jurisitetunisie.com : reconstruit l'arborescence d'un code
(Livre > Titre > Chapitre) à partir de ses pages de menu, récupère les pages
d'articles dans l'ordre de lecture, nettoie le bruit du site et écrit un .txt
avec front-matter, prêt pour data/raw/.

Exemple : Code de Commerce
--------------------------
1. Aperçu de l'arborescence, sans télécharger les articles :

     python -m scripts.scrape_jurisite --tree-only

2. Essai sur quelques pages :

     python -m scripts.scrape_jurisite --limit 5 --refresh

3. Passage complet :

     python -m scripts.scrape_jurisite --refresh --date-publication 1959-12-15 --date-derniere-maj 2018-01-01

4. Ingestion :

     python -m scripts.ingest --reset
"""
from __future__ import annotations

import argparse
import codecs
import html as htmllib
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

log = logging.getLogger(__name__)

ROOT = "__root__"

# Code de Commerce — table des matières (Livre I à V + loi de promulgation)
DEFAULT_START_URL = "https://www.jurisitetunisie.com/tunisie/codes/cc/menu.html"

# --------------------------------------------------------------------------- #
# Analyse du menu
# --------------------------------------------------------------------------- #
_TOKEN_RE = re.compile(
    r"(?P<ul><ul\b[^>]*>)"
    r"|(?P<endul></ul\s*>)"
    r"|<a\s[^>]*?href\s*=\s*[\"'](?P<href>[^\"']+)[\"'][^>]*>(?P<inner>.*?)</a\s*>",
    re.I | re.S,
)
_EDITABLE_RE = re.compile(
    r"<!--\s*#BeginEditable\s+\"texte\"\s*-->(.*?)<!--\s*#EndEditable\s*-->",
    re.I | re.S,
)
_MENU_FILE_RE = re.compile(r"^menu[^/]*\.html?$", re.I)

_SKIP_LABEL_RE = re.compile(
    r"^\s*(loi de promulgation|table chronologique|convention collective\s+cadre)",
    re.I,
)
_TRANSPARENT_RE = re.compile(r"^\s*sommaire\s*$", re.I)
_STRUCT_RE = re.compile(r"^\s*(livre|titre|chapitre|section)\b", re.I)
_RANGE_RE = re.compile(r"\s*\(\s*\d+\s*(?:à|a|-)\s*\d+\s*\)\s*$", re.I)


def _text_of(inner_html: str) -> str:
    text = re.sub(r"<[^>]+>", "", inner_html)
    text = htmllib.unescape(text).replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def clean_heading(label: str) -> str:
    """'LIVRE II : L'EXÉCUTION DU TRAVAIL ( 53 à 156)' -> sans la plage d'articles."""
    return re.sub(r"\s+", " ", _RANGE_RE.sub("", label)).strip()


def parse_menu_entries(page_html: str, page_url: str, base_dir: str
                       ) -> list[tuple[int, str, str, str]]:
    """Retourne [(profondeur, url, libellé, 'menu'|'page')] dans l'ordre du document."""
    m = _EDITABLE_RE.search(page_html)
    region = m.group(1) if m else page_html

    entries: list[tuple[int, str, str, str]] = []
    depth = 0
    for tok in _TOKEN_RE.finditer(region):
        if tok.group("ul"):
            depth += 1
        elif tok.group("endul"):
            depth = max(0, depth - 1)
        else:
            href = tok.group("href").strip()
            if href.lower().startswith(("#", "mailto:", "javascript:")):
                continue
            url = urljoin(page_url, href).split("#")[0]
            if not url.startswith(base_dir):
                continue
            label = _text_of(tok.group("inner"))
            if not label:
                continue
            filename = url.rsplit("/", 1)[-1]
            kind = "menu" if _MENU_FILE_RE.match(filename) else "page"
            entries.append((depth, url, label, kind))
    return entries


class Tree:
    """Arborescence fusionnée à partir de plusieurs pages de menu."""

    def __init__(self) -> None:
        self.nodes: dict[str, tuple[str, str]] = {}
        self.children: dict[str, list[str]] = {}

    def merge(self, entries: list[tuple[int, str, str, str]]) -> None:
        stack: list[tuple[int, str]] = []
        for depth, url, label, kind in entries:
            while stack and stack[-1][0] >= depth:
                stack.pop()
            parent = stack[-1][1] if stack else ROOT
            self.nodes.setdefault(url, (label, kind))
            siblings = self.children.setdefault(parent, [])
            if url not in siblings:
                siblings.append(url)
            stack.append((depth, url))

    def menu_urls(self) -> list[str]:
        return [u for u, (label, kind) in self.nodes.items()
                if kind == "menu" and not _SKIP_LABEL_RE.match(label)
                and not _TRANSPARENT_RE.match(label)]

    def page_urls(self) -> list[str]:
        return [u for u, (label, kind) in self.nodes.items()
                if kind == "page" and not _SKIP_LABEL_RE.match(label)]

    def iter_items(self, node: str = ROOT, _seen: set[str] | None = None):
        seen = set() if _seen is None else _seen
        for url in self.children.get(node, []):
            if url in seen:
                continue
            seen.add(url)
            label, kind = self.nodes[url]
            if _SKIP_LABEL_RE.match(label):
                continue
            if _TRANSPARENT_RE.match(label):
                yield from self.iter_items(url, seen)
            elif kind == "menu":
                yield ("heading", url, label)
                yield from self.iter_items(url, seen)
            else:
                yield ("page", url, label)


# --------------------------------------------------------------------------- #
# Récupération et nettoyage des pages
# --------------------------------------------------------------------------- #
_NOISE_PATTERNS = [
    re.compile(r"copyright\s+jurisite\s+tunisie", re.I),
    re.compile(r"iddn", re.I),
    re.compile(r"all rights protected", re.I),
    re.compile(r"actio personalis", re.I),
    re.compile(r"une action li[ée]e [àa] la personne meurt avec elle", re.I),
    re.compile(r"optimis[ée]\s+par\s+google", re.I),
    re.compile(r"codes et lois en texte int[ée]gral", re.I),
    re.compile(r"^\s*(les forums|index et taux|partages de successions)\s*$", re.I),
    re.compile(r"^\s*(sommaire|loi de promulgation|table chronologique)\s*$", re.I),
    re.compile(r"^\s*(pr[ée]c[ée]dent|suivant|retour|haut de page|imprimer)\s*$", re.I),
    re.compile(r"^\s*/\s*$"),
]

_BROKEN_INS_RE = re.compile(r'\bins\s+class="[^"]*"\s*')


def clean_page_text(raw_text: str) -> str:
    lines = []
    for line in raw_text.split("\n"):
        stripped = re.sub(r"[ \t]{2,}", " ", _BROKEN_INS_RE.sub("", line.replace("\xa0", " "))).strip()
        if not stripped:
            lines.append("")
        elif not any(p.search(stripped) for p in _NOISE_PATTERNS):
            lines.append(stripped)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return text.strip()


def _cp1252_fallback(exc: UnicodeError):
    if isinstance(exc, UnicodeDecodeError):
        return exc.object[exc.start:exc.end].decode("cp1252", errors="replace"), exc.end
    raise exc


codecs.register_error("cp1252_fallback", _cp1252_fallback)


def _decode(content: bytes) -> str:
    return content.decode("utf-8", errors="cp1252_fallback")


_CACHE_DIR: Path | None = None
_REFRESH = False


def _cache_path(url: str) -> Path:
    return _CACHE_DIR / re.sub(r"[^\w.\-]+", "_", url.split("//", 1)[-1])


def _get_html(session, url: str, delay: float) -> str:
    path = _cache_path(url) if _CACHE_DIR else None
    if path is not None and path.exists() and not _REFRESH:
        return _decode(path.read_bytes())

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            log.info("GET %s", url)
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            log.warning("Tentative %d/3 échouée pour %s : %s", attempt, url, exc)
            time.sleep(2 * attempt)
    else:
        raise last_exc  # type: ignore[misc]

    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
    time.sleep(delay)
    return _decode(resp.content)


# --------------------------------------------------------------------------- #
# Structuration des articles
# --------------------------------------------------------------------------- #
_ART_NUM = r"\d+(?:-\d+)?"
_SUFFIX = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies)"
_HDR_FLAGS = r"(?P<flags>(?:\s*\((?:nouveau|abrog[ée]e?)\))*)"

# En-tête SEUL sur sa ligne : "Article 408.", "Article 408", "Article 408. -", "Article 408 :".
# On tolère des points/espaces parasites en tête (le site en met parfois un).
_HDR_RE = re.compile(
    rf"^[.\s]*(?-i:Article|ARTICLE)\.?\s*(?P<num>{_ART_NUM})?\s*(?P<suf>{_SUFFIX})?"
    rf"{_HDR_FLAGS}\s*\.?\s*[-:–—]?\s*$",
    re.I)

# En-tête SUIVI de texte sur la même ligne, avec séparateur "." / ":" / "-" / "–" / "—".
# C'est le cas dominant sur le site : "<b>Article 189.</b> - Font partie..."
_HDR_INLINE_RE = re.compile(
    rf"^[.\s]*(?-i:Article|ARTICLE)\.?\s*(?P<num>{_ART_NUM})\s*(?P<suf>{_SUFFIX})?"
    rf"{_HDR_FLAGS}\s*\.?\s*[-:–—]\s*(?P<rest>\S.*)$",
    re.I)

_FLAG_RE = re.compile(r"\((nouveau|abrog[ée]e?)\)", re.I)
_SUSPECT_HDR_RE = re.compile(r"^(?:Article|ARTICLE)\.?\s*\d")
_SPLIT_TRIGGER_RE = re.compile(r"^art(?:icle)?\.?\s*(?:\d|premier\b|1\s*er\b)", re.I)

_CONT_NUM_RE = re.compile(rf"^(?P<num>{_ART_NUM})\s*\.?\s*:?$")
_CONT_SUF_RE = re.compile(rf"^(?P<suf>{_SUFFIX})\s*\.?\s*:?$", re.I)
_CONT_FLAG_RE = re.compile(r"^\((?P<flag>nouveau|abrog[ée]e?)\)\s*\.?\s*:?$", re.I)

_STRAY_RE = re.compile(r"^(?::|\(nouveau\)\s*:?)$", re.I)
_MARKER_RE = re.compile(r"^\[[^\w\s\]]{1,4}\]$")
_STRUCT_HEADING_RE = re.compile(
    r"^(?:LIVRE|TITRE|CHAPITRE|SECTION|Livre|Titre|Chapitre|Section)\s+"
    r"(?:Premier|Première|premier|première|Unique|unique|[IVXLC]+|\d+)\b")

_DEL = "@@DEL@@"
_NOTE = "@@NOTE@@"

_LAW_RE = re.compile(
    r"((?:Loi|Décret(?:-loi)?|Ordonnance)\s+n[°º]?\s*[\d\-/]+\s+du\s+"
    r"(?P<d>\d{1,2})(?:er)?\s+(?P<m>[^\W\d_]+)\s+(?P<y>\d{4}))", re.I)
_LAW_NUM_RE = re.compile(
    r"((?:Loi|Décret(?:-loi)?|Ordonnance)\s+n[°º]?\s*[\d\-/]+\s+du\s+"
    r"(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{2,4}))", re.I)
_AMEND_NOTE_RE = re.compile(
    r"^(?:nouvel\s+article|nouveau\s+contenu|article|contenu|texte|paragraphe|alinéa|"
    r"modifié|ajouté|inséré|complété|rétabli|remplacé)\b", re.I)
_MONTHS = {m: i for i, m in enumerate(
    "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(), 1)}
_ODD_DOT_APOS_RE = re.compile(r"(?<=\b[sldnjmtcSLDNJMTC])·(?=[aeiouyhAEIOUYHéèêàâîôû])")

# Séparateur parasite laissé par le site devant le texte du 1er alinéa
# ("- text", ".- text", ". - text", ": text"...).
_LEADING_SEP_RE = re.compile(r"^[.\s]*[-:–—]\s*")


def _latest_law(notes: list[str]) -> str | None:
    best, best_key = None, (-1, -1, -1)
    for note in notes:
        found = [(m.group(1), (int(m.group("y")), _MONTHS.get(m.group("m").lower(), 0), int(m.group("d"))))
                 for m in _LAW_RE.finditer(note)]
        for m in _LAW_NUM_RE.finditer(note):
            year = int(m.group("y"))
            if year < 100:
                year += 1900 if year >= 50 else 2000
            found.append((m.group(1), (year, int(m.group("m")), int(m.group("d")))))
        for text, key in found:
            if key >= best_key:
                best, best_key = text, key
    return best


def _resolve_versions(body: list[str], abrogated_flag: bool) -> dict:
    kept: list[str] = []
    notes: list[str] = []
    had_deleted = False
    for line in body:
        if line == _DEL:
            had_deleted = True
        elif line.startswith(_NOTE):
            notes.append(line[len(_NOTE):].strip())
        elif _MARKER_RE.match(line) or _STRAY_RE.match(line):
            continue
        elif re.match(r"^\(abrog[ée]e?\)$", line, re.I):
            abrogated_flag = True
        elif kept and re.fullmatch(r"[.,;:)\]]+", line):
            kept[-1] += line
        else:
            kept.append(line)

    # Nettoie un éventuel séparateur "-" / "." / ":" resté collé au début du texte
    # du premier alinéa (« Article 408 » suivi de « - Indépendamment… »).
    if kept:
        stripped = _LEADING_SEP_RE.sub("", kept[0])
        if stripped:
            kept[0] = stripped
        else:
            kept.pop(0)

    return {
        "kept": kept,
        "dropped": abrogated_flag or not kept,
        "multi": had_deleted,
        "review": (abrogated_flag and bool(kept)) or any('del class="' in x for x in kept),
        "law": _latest_law([n for n in notes if _AMEND_NOTE_RE.match(n)]),
    }


def structure_articles(text: str, report: dict | None = None) -> str:
    if report is None:
        report = {}
    for key in ("kept", "dropped", "multi", "review", "suspects"):
        report.setdefault(key, [])

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    out: list[str] = []
    cur: dict | None = None

    def flush() -> None:
        nonlocal cur
        if cur is None:
            return
        num = cur["num"]
        res = _resolve_versions(cur["body"], "abrogé" in cur["flags"] or "abrogée" in cur["flags"])
        if res["dropped"] or not res["kept"]:
            report["dropped"].append(num)
        else:
            report["kept"].append(num)
            if res["multi"]:
                report["multi"].append(num)
            if res["review"]:
                report["review"].append(num)
            first, *rest = res["kept"]
            block = [f"Article {num} — {first}", *rest]
            if res["law"]:
                block.append(f"[Version issue de la {res['law']}]")
            out.append("\n".join(block))
        cur = None

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]

        # 1) En-tête sur sa propre ligne
        m = _HDR_RE.match(line)
        if m:
            num, suf, j = m.group("num"), m.group("suf"), i + 1
            flags = {f.lower() for f in _FLAG_RE.findall(m.group("flags") or "")}
            while j < n:
                nxt = lines[j]
                mn, ms, mf = _CONT_NUM_RE.match(nxt), _CONT_SUF_RE.match(nxt), _CONT_FLAG_RE.match(nxt)
                if num is None and mn:
                    num = mn.group("num")
                elif num and suf is None and ms:
                    suf = ms.group("suf")          # garde la casse d'origine
                elif mf:
                    flags.add(mf.group("flag").lower())
                elif nxt == ":":
                    pass
                else:
                    break
                j += 1
            if num:
                flush()
                cur = {"num": num + (f" {suf}" if suf else ""), "flags": flags, "body": []}
                i = j
                continue

        # 2) En-tête suivi de texte sur la même ligne (« Article 189. - Font partie… »)
        mi = _HDR_INLINE_RE.match(line)
        if mi:
            flush()
            suf = mi.group("suf")
            cur = {"num": mi.group("num") + (f" {suf}" if suf else ""),
                   "flags": {f.lower() for f in _FLAG_RE.findall(mi.group("flags") or "")},
                   "body": [mi.group("rest")]}
            i += 1
            continue

        # 3) Titre structurel (LIVRE / TITRE / CHAPITRE / SECTION)
        if _STRUCT_HEADING_RE.match(line):
            flush()
            out.append(clean_heading(line))

        # 4) Texte hors article
        elif cur is None:
            if _SUSPECT_HDR_RE.match(line):
                report["suspects"].append(f"(début de page): {line[:100]}")
            out.append(line)

        # 5) Suite du corps de l'article courant
        else:
            if _SUSPECT_HDR_RE.match(line):
                report["suspects"].append(f"{cur['num']}: {line[:100]}")
            if (_SPLIT_TRIGGER_RE.match(line) and cur["body"]
                    and not cur["body"][-1].startswith(_NOTE)):
                cur["body"][-1] += " " + line
            else:
                cur["body"].append(line)
        i += 1
    flush()
    return _ODD_DOT_APOS_RE.sub("'", "\n\n".join(out)).replace("·", " ")


def _note_node(text: str):
    from bs4 import NavigableString
    return NavigableString(f"\n{_NOTE} " + re.sub(r"\s+", " ", text).strip() + "\n")


_HIDDEN_STYLE_RE = re.compile(r"visibility\s*:\s*hidden|display\s*:\s*none", re.I)
_BLOCK_TAGS = {"p", "div", "blockquote", "li", "ul", "ol", "dl", "dt", "dd", "table", "tr",
               "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "pre", "center"}


def _flow_text(node) -> str:
    from bs4 import CData, NavigableString, Tag
    parts: list[str] = []

    def walk(el) -> None:
        for child in el.children:
            if isinstance(child, Tag):
                if child.name == "br":
                    parts.append("\n")
                elif child.name in _BLOCK_TAGS:
                    parts.append("\n")
                    walk(child)
                    parts.append("\n")
                else:
                    walk(child)
            elif type(child) in (NavigableString, CData):
                raw = str(child)
                if raw.strip().startswith((_DEL, _NOTE)):
                    parts.append("\n" + raw.strip() + "\n")
                else:
                    parts.append(re.sub(r"\s+", " ", raw))

    walk(node)
    return "".join(parts)


def _content_from_soup(soup, report: dict | None = None) -> str:
    from bs4 import NavigableString
    for tag in soup(["script", "style", "noscript", "form"]):
        tag.decompose()
    cells = soup.find_all("td", class_="windowbg")
    node = max(cells, key=lambda c: len(c.get_text(strip=True)), default=None)
    node = node or soup.body or soup

    # 1) Texte remplacé (<del>) → marqueur _DEL
    for d in node.find_all("del"):
        d.replace_with(NavigableString(f"\n{_DEL}\n"))
    # 2) Bulles de provenance (class="tooltip") → marqueur _NOTE
    for t in node.find_all(class_="tooltip"):
        span = t.find(class_="tooltiptext")
        t.replace_with(_note_node(span.get_text(" ", strip=True) if span else ""))
    # 3) Notes cachées par style (visible seulement au survol) → marqueur _NOTE
    for el in node.find_all(style=_HIDDEN_STYLE_RE):
        el.replace_with(_note_node(el.get_text(" ", strip=True)))
    # 4) Étiquettes "Note" / "Note4" des <sup> (y compris quand le <sup>
    #    est DANS le <b> de l'en-tête, comme « Article 189 Bis. <sup>Note</sup> »)
    for sup in node.find_all("sup"):
        if re.fullmatch(r"Note\s*\d*", sup.get_text(strip=True), re.I):
            sup.decompose()

    return structure_articles(clean_page_text(_flow_text(node)), report)


def extract_content(page_html: str, report: dict | None = None) -> str:
    from bs4 import BeautifulSoup
    return _content_from_soup(BeautifulSoup(page_html, "lxml"), report)


def extract_page(page_html: str, report: dict | None = None) -> tuple[list[str], str]:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_html, "lxml")
    headings: list[str] = []
    top = soup.find(id="topcontent")
    if top is not None:
        for h in top.find_all(["h1", "h2", "h3", "h4"]):
            text = clean_heading(h.get_text(" ", strip=True).replace("\xa0", " "))
            if _STRUCT_RE.match(text):
                headings.append(text)
    return headings, _content_from_soup(soup, report)


def crawl_menu(start_url: str, session, delay: float) -> Tree:
    """Découvre toutes les pages d'articles en visitant chaque page de menu une fois.

    Si l'URL de départ est `menu.html`, on amorce aussi `menu-2.html` … `menu-6.html`
    (un fichier par livre). C'est indispensable : certaines pages de sommaire
    oublient de lier tous les livres, et sans ces graines on perd des branches
    entières. Les graines 404 sont simplement journalisées et ignorées.
    """
    base_dir = start_url.rsplit("/", 1)[0] + "/"
    tree = Tree()
    fetched: set[str] = set()

    todo = [start_url]
    parent, filename = start_url.rsplit("/", 1)
    if filename.lower() == "menu.html":
        for i in range(2, 7):
            sibling = f"{parent}/menu-{i}.html"
            if sibling not in todo:
                todo.append(sibling)

    while todo:
        url = todo.pop(0)
        if url in fetched:
            continue
        fetched.add(url)
        try:
            page_html = _get_html(session, url, delay)
        except Exception as exc:  # noqa: BLE001
            log.warning("Menu inaccessible %s : %s", url, exc)
            continue
        tree.merge(parse_menu_entries(page_html, url, base_dir))
        todo.extend(u for u in tree.menu_urls() if u not in fetched and u not in todo)
    return tree


# --------------------------------------------------------------------------- #
# Assemblage : ordre des articles, doublons, titres, numéros manquants
# --------------------------------------------------------------------------- #
_SUFFIX_RANK = {w: i for i, w in enumerate(
    "bis ter quater quinquies sexies septies octies nonies decies".split(), 1)}
_BLOCK_ART_RE = re.compile(r"^Article (?P<num>\d+(?:-\d+)?(?: [A-Za-z]+)?) — ")


def article_sort_key(num: str) -> tuple[int, int, int]:
    m = re.match(r"^(\d+)(?:-(\d+))?(?:\s+([A-Za-z]+))?$", num.strip())
    if not m:
        return (10**9, 0, 0)
    return (int(m.group(1)), int(m.group(2) or 0),
            _SUFFIX_RANK.get((m.group(3) or "").lower(), 0))


def _diff_snippet(kept: str, other: str, ctx: int = 80) -> str:
    n = next((i for i, (x, y) in enumerate(zip(kept, other)) if x != y), min(len(kept), len(other)))
    lo = max(0, n - ctx)
    return (f"    gardé : …{kept[lo:n + ctx]!r}  (longueur {len(kept)})\n"
            f"    autre : …{other[lo:n + ctx]!r}  (longueur {len(other)})")


def assemble_pages(pages: list[dict], report: dict) -> list[str]:
    for key in ("duplicates", "conflicts", "empty_pages", "no_headings"):
        report.setdefault(key, [])

    usable = []
    for page in pages:
        blocks = [b for b in page["text"].split("\n\n") if b.strip()]
        nums = [m.group("num") for b in blocks if (m := _BLOCK_ART_RE.match(b))]
        name = page["url"].rsplit("/", 1)[-1]
        if not nums:
            report["empty_pages"].append(name)
            continue
        if not page["headings"]:
            report["no_headings"].append(name)
        usable.append((min(article_sort_key(n) for n in nums), page, blocks))
    usable.sort(key=lambda t: t[0])

    out: list[str] = []
    seen: set[str] = set()
    first_text: dict[str, str] = {}
    first_src: dict[str, str] = {}
    report.setdefault("duplicate_details", [])
    report.setdefault("conflict_details", [])
    prev: list[str] = []
    for _, page, blocks in usable:
        heads = page["headings"]
        i = 0
        while i < len(heads) and i < len(prev) and _norm(heads[i]) == _norm(prev[i]):
            i += 1
        out.extend(heads[i:])
        prev = heads
        for block in blocks:
            m = _BLOCK_ART_RE.match(block)
            if m:
                num = m.group("num")
                src = page["url"].rsplit("/", 1)[-1]
                if num in seen:
                    report["duplicates"].append(num)
                    report["duplicate_details"].append(f"{num}: {first_src[num]} (gardé) / {src}")
                    if _norm(block) != _norm(first_text[num]):
                        report["conflicts"].append(num)
                        report["conflict_details"].append(
                            f"Article {num} : {first_src[num]} (gardé) / {src}\n"
                            f"{_diff_snippet(first_text[num], block)}")
                    continue
                seen.add(num)
                first_text[num] = block
                first_src[num] = src
            out.append(block)
    report["written"] = sorted(seen, key=article_sort_key)
    return out


def missing_numbers(report: dict) -> list[int]:
    seen = set(report.get("kept", [])) | set(report.get("dropped", []))
    mains = {int(m.group()) for n in seen if (m := re.match(r"\d+", n))}
    if not mains:
        return []
    return [i for i in range(min(mains), max(mains) + 1) if i not in mains]


def compress_ranges(nums: list[int]) -> str:
    out: list[str] = []
    start = prev = None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(str(start) if start == prev else f"{start}-{prev}")
            start = prev = n
    if start is not None:
        out.append(str(start) if start == prev else f"{start}-{prev}")
    return ", ".join(out) or "-"


def _norm(s: str) -> str:
    return re.sub(r"\W+", " ", s.casefold()).strip()


# --------------------------------------------------------------------------- #
def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(message)s")
    p = argparse.ArgumentParser(description="Crawl d'un code juridique sur jurisitetunisie.com.")
    p.add_argument("--start-url", default=DEFAULT_START_URL,
                   help="Page de menu du code (défaut : Code de Commerce, .../cc/menu.html).")
    p.add_argument("--output", default="data/raw/code_commerce_fr.txt",
                   help="Ex : data/raw/code_commerce_fr.txt (défaut).")
    p.add_argument("--code", default="Code de Commerce",
                   help="Ex : 'Code de Commerce' (défaut).")
    p.add_argument("--source-url", default="")
    p.add_argument("--date-publication", default="")
    p.add_argument("--date-derniere-maj", default="")
    p.add_argument("--statut", default="en vigueur")
    p.add_argument("--langue", default="fr", choices=["fr", "ar", "bilingue"])
    p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--tree-only", action="store_true",
                   help="Affiche les pages détectées puis s'arrête.")
    p.add_argument("--limit", type=int, default=0,
                   help="Ne traiter que les N premières pages (essai).")
    p.add_argument("--cache-dir", default="data/cache/jurisite")
    p.add_argument("--refresh", action="store_true",
                   help="Ignore le cache et re-télécharge tout.")
    p.add_argument("--user-agent", default=(
        "Mozilla/5.0 (compatible; assistant-juridique-tn-personal-scraper/1.0; "
        "usage personnel de recherche juridique)"))
    args = p.parse_args()

    import requests
    global _CACHE_DIR, _REFRESH
    _CACHE_DIR = Path(args.cache_dir) if args.cache_dir else None
    _REFRESH = args.refresh
    session = requests.Session()
    session.headers.update({"User-Agent": args.user_agent})

    tree = crawl_menu(args.start_url, session, args.delay)
    pages = tree.page_urls()
    if not pages:
        print("Aucune page d'articles détectée. Vérifiez --start-url.")
        return

    if args.tree_only:
        for kind, url, label in tree.iter_items():
            if kind == "heading":
                print(f"\n## {clean_heading(label)}")
            else:
                print(f"   - {clean_heading(label)}   [{url.rsplit('/', 1)[-1]}]")
        print(f"\n{len(pages)} pages d'articles distinctes détectées "
              f"(la hiérarchie affichée est indicative ; l'ordre final suit les numéros d'articles).")
        return

    if args.limit:
        pages = pages[:args.limit]

    report: dict = {}
    fetched_pages: list[dict] = []
    failures: list[str] = []
    for url in pages:
        try:
            headings, text = extract_page(_get_html(session, url, args.delay), report)
        except Exception as exc:  # noqa: BLE001
            log.error("Échec %s : %s", url, exc)
            failures.append(url)
            continue
        fetched_pages.append({"url": url, "headings": headings, "text": text})

    blocks = assemble_pages(fetched_pages, report)

    front = "\n".join([
        "---",
        f"code: {args.code}",
        f"source_url: {args.source_url or args.start_url}",
        f"date_publication: {args.date_publication}",
        f"date_derniere_maj: {args.date_derniere_maj}",
        f"statut: {args.statut}",
        f"langue: {args.langue}",
        "---",
    ])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(front + "\n\n" + "\n\n".join(blocks) + "\n", encoding="utf-8")

    def uniq(key: str) -> list[str]:
        return sorted(set(report.get(key, [])), key=article_sort_key)

    gaps = [] if args.limit else missing_numbers(report)
    suspects = report.get("suspects", [])
    explained = {}
    for n in gaps:
        hit = next((x for x in suspects if re.search(rf":\s*Article\.?\s*{n}\b", x, re.I)), None)
        if hit:
            explained[n] = hit
    detail = out.with_suffix(".rapport.log")
    detail.write_text("\n".join([
        f"Pages traitées : {len(fetched_pages)}/{len(pages)}",
        f"Articles écrits ({len(report.get('written', []))}) : {', '.join(report.get('written', []))}",
        f"Articles écartés ({len(uniq('dropped'))}) : {', '.join(uniq('dropped'))}",
        f"Articles à plusieurs versions ({len(uniq('multi'))}) : {', '.join(uniq('multi'))}",
        f"A vérifier : {', '.join(uniq('review')) or '-'}",
        f"Doublons ignorés : {', '.join(report.get('duplicates', [])) or '-'}",
        f"Doublons au TEXTE DIFFERENT (à vérifier) : "
        f"{', '.join(sorted(set(report.get('conflicts', [])), key=article_sort_key)) or '-'}",
        "Détail des doublons (article: page gardée / page ignorée) :",
        *[f"    {x}" for x in report.get("duplicate_details", [])],
        "Détail des doublons au texte différent :",
        *[f"  {x}" for x in report.get("conflict_details", [])],
        f"Numéros absents probablement fusionnés dans un autre article : "
        f"{'; '.join(f'{n} -> {v}' for n, v in explained.items()) or '-'}",
        f"Lignes ressemblant à un en-tête d'article mais non reconnues ({len(suspects)}) :",
        *[f"    {x}" for x in suspects],
        f"Numéros absents : {compress_ranges(gaps)}",
        f"Pages sans article : {', '.join(report.get('empty_pages', [])) or '-'}",
        f"Pages sans titre : {', '.join(report.get('no_headings', [])) or '-'}",
        f"Échecs : {', '.join(failures) or '-'}",
    ]) + "\n", encoding="utf-8")

    print(f"\n=== Terminé : {len(fetched_pages)}/{len(pages)} pages -> {out} ===")
    print(f"  Articles écrits                 : {len(report.get('written', []))}")
    print(f"  Articles écartés (abrogés)      : {len(uniq('dropped'))}")
    print(f"  Articles à plusieurs versions   : {len(uniq('multi'))}")
    print(f"  Doublons ignorés                : {len(report.get('duplicates', []))}")
    if report.get("conflicts"):
        print(f"  DOUBLONS AU TEXTE DIFFERENT     : "
              f"{', '.join(sorted(set(report['conflicts']), key=article_sort_key))}")
    if not args.limit:
        print(f"  Numéros absents                 : {compress_ranges(gaps)}")
        for n, v in explained.items():
            print(f"    {n} -> entête non reconnu, fusionné ici : {v}")
    if report.get("review"):
        print(f"  A VÉRIFIER À LA MAIN            : {', '.join(uniq('review'))}")
    for url in failures:
        print(f"  échec : {url}")
    print(f"  Détail complet : {detail}")
    print("Relisez le fichier, puis : python -m scripts.ingest --reset")


if __name__ == "__main__":
    main()