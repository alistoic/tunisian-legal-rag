import re
from scripts.scrape_jurisite import (ROOT, Tree, clean_heading, clean_page_text,
                                     parse_menu_entries)

PAGE_URL = "https://www.jurisitetunisie.com/tunisie/codes/ct/menu-221.html"
BASE_DIR = "https://www.jurisitetunisie.com/tunisie/codes/ct/"

# Extrait réel de la page de menu du Code du travail (balises <b> mal fermées incluses)
MENU_HTML = """
<html><body>
<a href="/forum/index.html">Les forums</a>
<td height="1%" valign="top" class="windowbg">
 <!-- #BeginEditable "texte" -->
<a href="Ct1000.htm"><img src="images/walclaspage.gif" border="0">&nbsp;Loi de Promulgation</a> <br>
<b><a href="menu.html"><img src="images/walclasopen.gif" border="0">&nbsp;<b>Sommaire</b></a> <br>
<ul>
<a href="Ct1005.htm"><img src="images/walclaspage.gif" border="0">&nbsp;Dispositions générales</a> <br>
<b><a href="menu-2.html"><img src="images/walclasopen.gif" border="0">&nbsp;<b>LIVRE Premier FORMATION DES RAPPORTS DE TRAVAIL (6 à 52)</b></a> <br>
<ul>
<b><a href="menu-22.html"><img src="images/walclasopen.gif" border="0">&nbsp;<b>TITRE Premier LE CONTRAT DE TRAVAIL (6 à 27)</b></a> <br>
<ul>
<a href="Ct1010.htm"><img src="images/walclaspage.gif" border="0">&nbsp;Chapitre Premier : FORMATION DU CONTRAT (6 à 9)</a> <br>
<a href="Ct1015.htm"><img src="images/walclaspage.gif" border="0">&nbsp;Chapitre II : LES OBLIGATIONS DU SALARIÉ ( 10 à 13)</a> <br>
<a href="Ct1020.htm"><img src="images/walclaspage.gif" border="0">&nbsp;Chapitre III : FIN DU CONTRAT DE TRAVAIL (14 à 27)</a> <br>
</ul>
<a href="Ct1025.htm"><img src="images/walclaspage.gif" border="0">&nbsp;TITRE II : SOUS-ENTREPRISE DE MAIN-D'OEUVRE ( 28 à 30)</a> <br>
<b><a href="menu-223.html"><img src="images/walclasclose.gif" border="0">&nbsp;<b>TITRE III : LES CONVENTIONS COLLECTIVES  ( 31 à 52)</b></a> <br>
</b></b></ul><b><b>
<b><a href="menu-23.html"><img src="images/walclasclose.gif" border="0">&nbsp;<b>LIVRE II : L'EXÉCUTION DU TRAVAIL ( 53 à 156)</b></a> <br>
<a href="Ct1145.htm"><img src="images/walclaspage.gif" border="0">&nbsp;LIVRE III : REPRÉSENTATION DU PERSONNEL DANS LES ENTREPRISES  (157 à 169) </a> <br>
<a href="Ct1150.htm"><img src="images/walclaspage.gif" border="0">&nbsp;LIVRE IV : L'INSPECTION DU TRAVAIL  (170 à 182) </a> <br>
<b><a href="menu-26.html"><img src="images/walclasclose.gif" border="0">&nbsp;<b>LIVRE V : LES CONFLITS INDIVIDUELS DU TRAVAIL (183 à 232)</b></a> <br>
<a href="Ct1190.htm"><img src="images/walclaspage.gif" border="0">&nbsp;LIVRE VI : DES PÉNALITÉS  (233 à 241) </a> <br>
<b><a href="menu-28.html"><img src="images/walclasclose.gif" border="0">&nbsp;<b>LIVRE VII : DISPOSITIONS SPÉCIALES (242 à 446)</b></a> <br>
</b></b></b></b></b></b></ul><b><b>
<a href="Ct2000.htm"><img src="images/walclaspage.gif" border="0">&nbsp;Table Chronologique</a> <br>
<b><a href="menu-4.html"><img src="images/walclasclose.gif" border="0">&nbsp;<b>Convention collective Cadre</b></a> <br>

   <!-- #EndEditable --></b></b></b></b></td>
</body></html>
"""


def _tree() -> Tree:
    t = Tree()
    t.merge(parse_menu_entries(MENU_HTML, PAGE_URL, BASE_DIR))
    return t


def test_links_outside_menu_region_are_ignored():
    urls = list(_tree().nodes)
    assert not any("forum" in u for u in urls)


def test_reading_order_of_pages_and_headings():
    items = [(k, clean_heading(lbl)) for k, _, lbl in _tree().iter_items()]
    assert [lbl for k, lbl in items if k == "page"] == [
        "Dispositions générales",
        "Chapitre Premier : FORMATION DU CONTRAT",
        "Chapitre II : LES OBLIGATIONS DU SALARIÉ",
        "Chapitre III : FIN DU CONTRAT DE TRAVAIL",
        "TITRE II : SOUS-ENTREPRISE DE MAIN-D'OEUVRE",
        "LIVRE III : REPRÉSENTATION DU PERSONNEL DANS LES ENTREPRISES",
        "LIVRE IV : L'INSPECTION DU TRAVAIL",
        "LIVRE VI : DES PÉNALITÉS",
    ]
    headings = [lbl for k, lbl in items if k == "heading"]
    assert headings[0] == "LIVRE Premier FORMATION DES RAPPORTS DE TRAVAIL"
    assert headings[1] == "TITRE Premier LE CONTRAT DE TRAVAIL"


def test_promulgation_chronologie_and_cadre_are_skipped():
    labels = " | ".join(lbl for _, _, lbl in _tree().iter_items())
    assert "Promulgation" not in labels
    assert "Chronologique" not in labels
    assert "Convention collective Cadre" not in labels


def test_chapters_hang_under_their_titre():
    t = _tree()
    titre1 = next(u for u, (lbl, _) in t.nodes.items() if lbl.startswith("TITRE Premier"))
    assert [t.nodes[u][0][:10] for u in t.children[titre1]] == [
        "Chapitre P", "Chapitre I", "Chapitre I"]


def test_collapsed_branches_are_the_ones_to_open_next():
    t = _tree()
    collapsed = {u.rsplit("/", 1)[-1] for u in t.collapsed_menus({PAGE_URL})}
    assert collapsed == {"menu-223.html", "menu-23.html", "menu-26.html", "menu-28.html"}


def test_clean_heading_removes_article_range():
    assert clean_heading("LIVRE II : L'EXÉCUTION DU TRAVAIL ( 53 à 156)") == \
        "LIVRE II : L'EXÉCUTION DU TRAVAIL"


def test_clean_page_text_drops_site_noise():
    raw = "Article 6 — Texte.\nCopyright Jurisite Tunisie 2001-2026\nSommaire\n\n\n\nArticle 7 — Suite."
    out = clean_page_text(raw)
    assert "Copyright" not in out and "Sommaire" not in out
    assert "Article 6" in out and "Article 7" in out


# --------------------------------------------------------------------------- #
# Structuration des articles
# --------------------------------------------------------------------------- #
from pathlib import Path

import pytest

from scripts.scrape_jurisite import (_decode, _latest_law, extract_content,
                                     structure_articles)

FIXTURE = Path(__file__).parent / "fixtures" / "ct1010.html"


def test_decode_keeps_utf8_accents_when_one_stray_cp1252_byte_is_present():
    raw = "Établissements — présent".encode("utf-8") + b" Jurisite\xa9 2001"
    assert _decode(raw) == "Établissements — présent Jurisite© 2001"


def test_latest_law_picks_most_recent_by_date_not_by_position():
    notes = ["Article ajouté par Loi n° 2025-9 du 21 mai 2025, art. 1",
             "Article ajouté par Loi n° 96-62 du 15 Juillet 1996, art. 1"]
    assert _latest_law(notes) == "Loi n° 2025-9 du 21 mai 2025"
    assert _latest_law([]) is None


def test_structure_header_variants_and_markers():
    text = "\n".join([
        "Article. 1 :", "Premier texte.",
        "Article. 5", "bis :", "@@NOTE@@ Article ajouté par Loi n° 93-66 du 5 Juillet 1993", "Texte 5 bis.",
        "Article 6-2", "@@NOTE@@ Article ajouté par Loi n° 96-62 du 15 Juillet 1996", ":", "Texte 6-2.",
        "Article.", "9", "(Abrogé)", ":", "@@DEL@@",
        "Chapitre II : LES OBLIGATIONS DU SALARIÉ ( 10 à 13)",
        "Article. 10 :", "Texte 10.",
    ])
    report = {}
    out = structure_articles(text, report)
    assert report["kept"] == ["1", "5 bis", "6-2", "10"]
    assert report["dropped"] == ["9"]
    for header in ("Article 1 — Premier texte.", "Article 5 bis — Texte 5 bis.",
                   "Article 6-2 — Texte 6-2.", "Article 10 — Texte 10."):
        assert header in out
    assert "[Version issue de la Loi n° 93-66 du 5 Juillet 1993]" in out
    assert "\n\nChapitre II : LES OBLIGATIONS DU SALARIÉ\n\n" in out   # plage (10 à 13) retirée
    assert "@@" not in out


def test_paragraph_added_later_does_not_erase_original_paragraph():
    # Article modifié paragraphe par paragraphe : le 1er alinéa est d'origine (pas de <del>),
    # le 2e a été ajouté plus tard (bulle de provenance AVANT lui).
    text = "\n".join(["Article. 20 :", "Alinéa d'origine, toujours en vigueur.",
                      "@@NOTE@@ Paragraphe ajouté par Loi n° 2025-9 du 21 mai 2025", "Alinéa ajouté en 2025."])
    out = structure_articles(text, {})
    assert "Alinéa d'origine, toujours en vigueur." in out
    assert "Alinéa ajouté en 2025." in out


def test_article_whose_whole_body_was_deleted_is_dropped():
    report = {}
    out = structure_articles("Article. 30 :\n@@DEL@@\nArticle. 31 :\nTexte 31.", report)
    assert report["dropped"] == ["30"] and report["kept"] == ["31"]
    assert "Article 30" not in out


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture absente")
def test_real_page_ct1010_keeps_only_current_versions():
    pytest.importorskip("bs4")
    pytest.importorskip("lxml")
    report = {}
    out = extract_content(_decode(FIXTURE.read_bytes()), report)

    assert report["kept"] == ["6", "6-2", "6-3", "6-4", "7", "8"]
    assert report["dropped"] == ["9"]
    assert report["multi"] == ["6", "6-2", "6-3", "6-4"]

    assert "travailleur ou salarié" in out and "Le louage de services" not in out
    assert "réputé conclu pour une durée indéterminée" in out and "peut comporter une limitation" not in out
    assert "durée maximale de six mois" in out and "sont soumis en ce qui concerne" not in out
    assert "Il est interdit la conclusion" in out and "peut être conclu dans les cas suivants" not in out
    assert "Le travailleur, qui a dû quitter" in out          # entité &#251; + accents intacts
    assert "réembauchage" not in out                           # article 9 abrogé
    assert "Copyright" not in out and "Les forums" not in out  # pied de page ignoré
    assert "@@" not in out and "[↹]" not in out and "[⥅]" not in out and "Ã" not in out


# --------------------------------------------------------------------------- #
# Pages uniques, ordre par numéro d'article, doublons, titres (bug du crawl complet)
# --------------------------------------------------------------------------- #
from scripts.scrape_jurisite import (article_sort_key, assemble_pages, compress_ranges,
                                     extract_page, missing_numbers)


def test_a_page_listed_under_two_parents_is_yielded_once():
    t = Tree()
    t.merge([(1, BASE_DIR + "menu-2.html", "LIVRE II", "menu"),
             (2, BASE_DIR + "Ct1085.htm", "Chapitre A", "page")])
    t.merge([(1, BASE_DIR + "menu-3.html", "LIVRE III", "menu"),
             (2, BASE_DIR + "Ct1085.htm", "Chapitre A", "page")])
    assert [u for k, u, _ in t.iter_items() if k == "page"] == [BASE_DIR + "Ct1085.htm"]
    assert t.page_urls() == [BASE_DIR + "Ct1085.htm"]


def test_discovery_lists_every_menu_and_page_once_and_skips_non_code_entries():
    t = _tree()
    menus = {u.rsplit("/", 1)[-1] for u in t.menu_urls()}
    pages = [u.rsplit("/", 1)[-1] for u in t.page_urls()]
    assert menus == {"menu-2.html", "menu-22.html", "menu-223.html",
                     "menu-23.html", "menu-26.html", "menu-28.html"}   # ni Sommaire ni Convention cadre
    assert pages == ["Ct1005.htm", "Ct1010.htm", "Ct1015.htm", "Ct1020.htm",
                     "Ct1025.htm", "Ct1145.htm", "Ct1150.htm", "Ct1190.htm"]  # ni Promulgation ni Chronologie


def test_article_sort_key_follows_legal_order():
    nums = ["10", "6-2", "6", "5 bis", "5", "94-2", "94", "234 bis", "234"]
    assert sorted(nums, key=article_sort_key) == [
        "5", "5 bis", "6", "6-2", "10", "94", "94-2", "234", "234 bis"]


def _page(name, headings, text):
    return {"url": BASE_DIR + name, "headings": headings, "text": text}


def test_assemble_orders_by_article_dedupes_and_emits_headings_only_on_change():
    livre, titre = "LIVRE Premier : X", "TITRE Premier : Y"
    pages = [
        _page("Ct1015.htm", [livre, titre, "Chapitre II : B"], "Article 10 — a\n\nArticle 11 — b"),
        _page("Ct1010.htm", [livre, titre, "Chapitre Premier : A"],
              "Article 6 — c\n\nArticle 6-2 — d\n\nArticle 10 — dup"),
        _page("Ct1005.htm", [], "Article 1 — e\n\nArticle 5 bis — f"),
        _page("CtVide.htm", [], "aucun article ici"),
    ]
    report = {}
    out = assemble_pages(pages, report)
    assert out == [
        "Article 1 — e", "Article 5 bis — f",
        livre, titre, "Chapitre Premier : A",
        "Article 6 — c", "Article 6-2 — d", "Article 10 — dup",
        "Chapitre II : B",                      # LIVRE et TITRE identiques : non répétés
        "Article 11 — b",
    ]
    assert report["duplicates"] == ["10"]       # le 2e "Article 10" est ignoré
    assert report["empty_pages"] == ["CtVide.htm"]
    assert report["no_headings"] == ["Ct1005.htm"]
    assert report["written"] == ["1", "5 bis", "6", "6-2", "10", "11"]


def test_same_page_content_twice_never_produces_duplicate_articles():
    # Reproduit le crash "DuplicateIDError" : une page récupérée 3 fois
    page = _page("Ct1010.htm", ["Chapitre Premier : A"], "Article 73 — texte\n\nArticle 74 — suite")
    out = assemble_pages([page, dict(page), dict(page)], {})
    assert [b for b in out if b.startswith("Article")] == ["Article 73 — texte", "Article 74 — suite"]


def test_missing_numbers_and_ranges():
    report = {"kept": ["1", "2", "5 bis", "7"], "dropped": ["9"]}
    gaps = missing_numbers(report)
    assert gaps == [3, 4, 6, 8]
    assert compress_ranges(gaps) == "3-4, 6, 8"
    assert compress_ranges([]) == "-"


@pytest.mark.skipif(not FIXTURE.exists(), reason="fixture absente")
def test_extract_page_returns_the_headings_declared_by_the_page():
    pytest.importorskip("bs4")
    pytest.importorskip("lxml")
    headings, text = extract_page(_decode(FIXTURE.read_bytes()), {})
    assert headings == ["LIVRE Premier : FORMATION DES RAPPORTS DE TRAVAIL",
                        "TITRE Premier : LE CONTRAT DE TRAVAIL",
                        "Chapitre Premier : FORMATION DU CONTRAT"]
    assert text.startswith("Article 6 — Le contrat de travail est une convention")


# --------------------------------------------------------------------------- #
# Réseau instable, cache, en-têtes en ligne, diagnostics
# --------------------------------------------------------------------------- #
import scripts.scrape_jurisite as sj


class _Resp:
    def __init__(self, content=b"<html>ok</html>"):
        self.content = content

    def raise_for_status(self):
        pass


class _Session:
    def __init__(self, fail_times=0):
        self.calls, self.fail_times = 0, fail_times

    def get(self, url, timeout=20):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("Remote end closed connection without response")
        return _Resp("Établissement".encode("utf-8"))


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(sj.time, "sleep", lambda *_: None)


def test_get_html_retries_after_transient_failure(monkeypatch, no_sleep):
    monkeypatch.setattr(sj, "_CACHE_DIR", None)
    session = _Session(fail_times=2)
    assert sj._get_html(session, "https://x.test/Ct1105.htm", 0) == "Établissement"
    assert session.calls == 3


def test_get_html_gives_up_after_three_failures(monkeypatch, no_sleep):
    monkeypatch.setattr(sj, "_CACHE_DIR", None)
    session = _Session(fail_times=99)
    with pytest.raises(ConnectionError):
        sj._get_html(session, "https://x.test/Ct1105.htm", 0)
    assert session.calls == 3


def test_get_html_uses_disk_cache_and_refresh_bypasses_it(monkeypatch, no_sleep, tmp_path):
    monkeypatch.setattr(sj, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(sj, "_REFRESH", False)
    session = _Session()
    url = "https://www.jurisitetunisie.com/tunisie/codes/ct/Ct1005.htm"
    assert sj._get_html(session, url, 0) == "Établissement"
    assert sj._get_html(session, url, 0) == "Établissement"
    assert session.calls == 1                      # 2e lecture : depuis le cache
    monkeypatch.setattr(sj, "_REFRESH", True)
    sj._get_html(session, url, 0)
    assert session.calls == 2


def test_inline_header_with_text_on_same_line_is_recognised():
    report = {}
    out = structure_articles("Article. 96 :\nTexte 96.\nArticle. 97 : Texte 97 sur la même ligne.\n"
                             "Article. 97\nbis :\nTexte 97 bis.", report)
    assert report["kept"] == ["96", "97", "97 bis"]
    assert "Article 97 — Texte 97 sur la même ligne." in out
    assert "Article. 97 :" not in out              # plus fusionné dans l'article 96


def test_unrecognised_header_like_line_is_reported_as_suspect():
    report = {}
    structure_articles("Article. 96 :\nTexte 96.\nArticle 98.- Texte avec un format inattendu.", report)
    assert report["suspects"] == ["96: Article 98.- Texte avec un format inattendu."]


def test_duplicate_with_different_text_is_flagged_as_conflict():
    pages = [_page("Ct1.htm", [], "Article 5 — version A"),
             _page("Ct2.htm", [], "Article 5 — version A\n\nArticle 6 — x"),
             _page("Ct3.htm", [], "Article 5 — version B\n\nArticle 7 — y")]
    report = {}
    out = assemble_pages(pages, report)
    assert report["duplicates"] == ["5", "5"]
    assert report["conflicts"] == ["5"]            # seule la copie "B" diffère de la première
    assert "Article 5 — version A" in out and "Article 5 — version B" not in out


# --------------------------------------------------------------------------- #
# En-têtes réels trouvés dans le crawl complet (articles 97, 155, 335)
# --------------------------------------------------------------------------- #
from scripts.scrape_jurisite import clean_page_text


def test_header_with_nouveau_on_the_same_line():
    report = {}
    out = structure_articles("Article. 96 :\nTexte 96.\nArticle. 97 (nouveau):\nTexte 97.\n"
                             "Article. 98 (nouveau) :\nTexte 98.", report)
    assert report["kept"] == ["96", "97", "98"]
    assert "Article 97 — Texte 97." in out and "Article 98 — Texte 98." in out
    assert "(nouveau)" not in out and report["suspects"] == []


def test_header_with_nouveau_and_text_on_the_same_line():
    out = structure_articles("Article. 335 (nouveau) : Texte du 335.", {})
    assert out == "Article 335 — Texte du 335."


def test_inline_abroge_flag_in_header_drops_the_article():
    report = {}
    structure_articles("Article. 50 (Abrogé) :\n@@DEL@@\nArticle. 51 :\nTexte 51.", report)
    assert report["dropped"] == ["50"] and report["kept"] == ["51"]


def test_broken_ins_tag_text_is_removed_from_the_header():
    assert clean_page_text('Article. 155 ins class="a19960062" :') == "Article. 155 :"
    report = {}
    out = structure_articles(
        clean_page_text('Article. 154-5 :\nTexte 154-5.\nArticle. 155 ins class="a19960062" :\nTexte 155.'),
        report)
    assert report["kept"] == ["154-5", "155"]
    assert "Article 155 — Texte 155." in out and "class=" not in out


def test_broken_del_tag_left_in_text_is_sent_to_manual_review():
    report = {}
    structure_articles('Article. 60 :\nTexte avec del class="a19960062" resté dedans.', report)
    assert report["review"] == ["60"]


def test_unrecognised_header_at_start_of_page_is_reported_too():
    report = {}
    structure_articles("Article 335.- Texte avec un format inattendu.\nsuite", report)
    assert report["suspects"] == ["(début de page): Article 335.- Texte avec un format inattendu."]


def test_duplicate_details_name_the_pages_and_show_where_texts_differ():
    pages = [_page("Ct1085.htm", [], "Article 30 — Le salarié peut partir en congé."),
             _page("Ct1090.htm", [], "Article 30 — Le salarié doit partir en congé.\n\nArticle 31 — x")]
    report = {}
    assemble_pages(pages, report)
    assert report["duplicate_details"] == ["30: Ct1085.htm (gardé) / Ct1090.htm"]
    detail = report["conflict_details"][0]
    assert "Article 30 : Ct1085.htm (gardé) / Ct1090.htm" in detail
    assert "peut partir" in detail and "doit partir" in detail


# --------------------------------------------------------------------------- #
# Bug des "articles fantômes" : un renvoi hyperlié pris pour un en-tête d'article
# --------------------------------------------------------------------------- #
def _cell(body: str) -> str:
    return f'<html><body><table><tr><td class="windowbg">{body}</td></tr></table></body></html>'


def test_cross_reference_link_does_not_create_a_phantom_article():
    pytest.importorskip("bs4")
    pytest.importorskip("lxml")
    html = _cell(
        '<a name="21"></a>Article. 21 :<br>'
        "<blockquote>Les dispositions de l'<a href=\"Ct1010.htm\">article 8</a> du présent code "
        "doivent être observées.<br>Le réembauchage est prioritaire.</blockquote>"
        '<a name="22"></a>Article. 22 :<br><blockquote>Texte 22.</blockquote>')
    report = {}
    out = extract_content(html, report)
    assert report["kept"] == ["21", "22"]                      # pas d'"Article 8" fantôme
    assert "Les dispositions de l'article 8 du présent code doivent être observées." in out
    assert "Le réembauchage est prioritaire." in out            # la fin de l'article 21 n'est plus perdue
    assert "Article 8 —" not in out


def test_flow_text_breaks_only_on_br_and_blocks_not_on_inline_tags():
    pytest.importorskip("bs4")
    from bs4 import BeautifulSoup
    soup = BeautifulSoup("<div>à l'<a href='x'>article 153</a> du <b>Code</b> pénal<br>ligne 2"
                         "<!-- commentaire --><blockquote>bloc</blockquote></div>", "lxml")
    lines = [l.strip() for l in sj._flow_text(soup.div).split("\n") if l.strip()]
    assert lines == ["à l'article 153 du Code pénal", "ligne 2", "bloc"]


def test_lowercase_article_line_is_a_reference_never_a_header():
    report = {}
    out = structure_articles("Article. 5 :\nTexte.\narticle 6\nsuite du texte.", report)
    assert report["kept"] == ["5"]
    assert not re.search(r"(?im)^article\s*6", out)             # jamais en début de ligne


def test_body_line_starting_with_article_is_attached_to_previous_line():
    report = {}
    out = structure_articles("Article. 5 :\nPremier alinéa.\nArticle 12 du présent code s'applique.", report)
    assert report["kept"] == ["5"]
    assert "Premier alinéa. Article 12 du présent code s'applique." in out
    assert report["suspects"] == ["5: Article 12 du présent code s'applique."]


def test_nouveau_with_colon_on_its_own_line_is_dropped():
    report = {}
    out = structure_articles("Article. 6-3 :\n@@NOTE@@ Article ajouté par Loi n° 96-62 du 15 Juillet 1996\n"
                             "(nouveau):\nTexte 6-3.", report)
    assert report["kept"] == ["6-3"] and "(nouveau)" not in out


def test_clean_page_text_collapses_double_spaces():
    assert clean_page_text("médecine  du   travail ,  à l'inspection") == "médecine du travail , à l'inspection"


# --------------------------------------------------------------------------- #
# Article 117 : bulle de provenance écrite en <span> (et non <div>)
# --------------------------------------------------------------------------- #
def test_span_tooltip_after_header_does_not_hide_the_article():
    pytest.importorskip("bs4")
    pytest.importorskip("lxml")
    html = _cell(
        '<a name="116"></a>Article. 116 :<br><blockquote>Texte 116.</blockquote>'
        '<a name="117"></a>Article. 117 <ins class="a19960062">(nouveau)</ins> '
        '<span class="tooltip">Note4<span class="tooltiptext">Modifié par l\'article premier de la loi '
        'n° 96-62 du 15/07/96</span></span>:<br>'
        '<blockquote>Texte 117 <span class="tooltip">Note<span class="tooltiptext">En vigueur</span></span>.'
        '</blockquote>'
        '<a name="118"></a>Article. 118 :<br><blockquote>Texte 118.</blockquote>')
    report = {}
    out = extract_content(html, report)
    assert report["kept"] == ["116", "117", "118"]
    assert report["suspects"] == []
    assert "Article 117 — Texte 117." in out            # la ponctuation orpheline est rattachée
    assert "Note4" not in out and "NoteEn" not in out and "tooltip" not in out
    assert "Article 116 — Texte 116." in out and "Article 118 — Texte 118." in out


# --------------------------------------------------------------------------- #
# Article 117 réel : notes de bas de page = <sup>NoteN</sup> + <span style="visibility:hidden">
# --------------------------------------------------------------------------- #
ART_117_HTML = _cell('''
<br><img src="/expandcollapse/menu_14.png" width="18" height="16" hspace="5" alt="Code du travail - Tunisie"><a name="116"></a>Article.&nbsp;116&nbsp;:
<blockquote>Texte 116.</blockquote>
<br><img src="/expandcollapse/menu_14.png" width="18" height="16" hspace="5" alt="Code du travail - Tunisie"><a
name="117"></a>Article.&nbsp;117&nbsp;<ins class="a19960062">(nouveau)</ins>
  <sup><font color="#0000FF"><a href="javascript:;" onMouseOver="MM_showHideLayers('footnoteNote4','','show')"
onMouseOut="MM_showHideLayers('footnoteNote4','','hide')">Note4</a></font></sup>  <span id="footnoteNote4"
style="position:absolute; width:350px; z-index:1; visibility:hidden; background-color:#CCFFFF;
layer-background-color:#CCFFFF;"><font size="-1"><font size="-1">Modifié  par l'article premier de la loi n° 96-62 du
15/07/96</font></font></span>:
  <sup><font color="#0000FF"><a href="javascript:;" onMouseOver="MM_showHideLayers('92covid-19','','show')"
onMouseOut="MM_showHideLayers('92covid-19','','hide')">Note</a></font></sup><span id="92covid-19"
style="position:absolute; width:350px; z-index:1; visibility:hidden; background-color:#CCFFFF;
layer-background-color:#CCFFFF;"><font size="-1">En vertu des dispositions du décret-loi n°2020-2 du 14 avril 2020,
"Est suspendue l’application des dispositions du premier alinéa de l’article 117 du Code du travail".</font></span>
<blockquote>
  <del class="a19960062_a00000000">
          La période des congés est fixée par la conventioncollective de travail. ANCIEN TEXTE 117.<ins class="a19960062">
          <div class="tooltip">[↹]<span class="tooltiptext">Contenu supprimé en vue de son remplacement par Loi n° 96-62 du 15 Juillet 1996, art. 1</span></div></ins>
  </del>
  <ins class="a19960062">
          <div class="tooltip">[↹]<span class="tooltiptext">Nouveau contenu inséré après suppression du contenu auquel il se substitue,  par Loi n° 96-62 du 15 Juillet 1996, art. 1</span></div>
          Le congé annuel est octroyé au cours de la période du 1er juin au 31 octobre de chaque année.<div class="tooltip">[S]<span
class="tooltiptext">En vertu des dispositions du décret-loi n°2020-2 du 14 avril 2020, "Est suspendue l’application des dispositions du premier alinéa de l’article 117 du Code du travail".</span></div><br>
          L'employeur fixe l'ordre des départs en congé.
  </ins>
</blockquote>
<br><img src="/expandcollapse/menu_14.png" width="18" height="16" hspace="5" alt="Code du travail - Tunisie"><a
name="118"></a>Article.&nbsp;118&nbsp;:
<blockquote>Texte 118.</blockquote>''')


def test_real_article_117_with_hidden_footnote_spans():
    pytest.importorskip("bs4")
    pytest.importorskip("lxml")
    report = {}
    out = extract_content(ART_117_HTML, report)
    assert report["kept"] == ["116", "117", "118"] and report["suspects"] == []
    assert "Article 117 — Le congé annuel est octroyé au cours de la période du 1er juin au 31 octobre" in out
    assert "L'employeur fixe l'ordre des départs en congé." in out
    assert "ANCIEN TEXTE" not in out                                   # texte remplacé (<del>)
    for leftover in ("Note4", "NoteEn", "Est suspendue", "Modifié", "visibility", "[S]"):
        assert leftover not in out                                      # notes cachées retirées du texte
    # la version vient de la loi de 1996, PAS du décret-loi de 2020 (simple suspension)
    assert "[Version issue de la Loi n° 96-62 du 15 Juillet 1996]" in out
    assert "2020" not in out
    assert report["multi"] == ["117"]


def test_version_line_ignores_non_amendment_notes():
    out = structure_articles(
        "Article. 5 :\n@@NOTE@@ Article ajouté par Loi n° 96-62 du 15 Juillet 1996\n"
        "@@NOTE@@ En vertu des dispositions du décret-loi n°2020-2 du 14 avril 2020, suspension.\nTexte.", {})
    assert out.endswith("[Version issue de la Loi n° 96-62 du 15 Juillet 1996]")


def test_latest_law_understands_numeric_dates():
    assert _latest_law(["Modifié  par l'article premier de la loi n° 96-62 du 15/07/96"]) == \
        "loi n° 96-62 du 15/07/96"
    mixed = ["Article ajouté par Loi n° 93-66 du 5 Juillet 1993",
             "Modifié par la loi n° 2007-20 du 30/04/07"]
    assert _latest_law(mixed) == "loi n° 2007-20 du 30/04/07"          # 2007 > 1993


def test_note_text_wrapped_over_several_lines_stays_on_one_line():
    pytest.importorskip("bs4")
    pytest.importorskip("lxml")
    html = _cell('Article. 7 :<br><blockquote>Texte 7.<span style="visibility:hidden">Modifié par\n la loi\n n° 96-62</span>'
                 '</blockquote>Article. 8 :<br><blockquote>Texte 8.</blockquote>')
    report = {}
    out = extract_content(html, report)
    assert report["kept"] == ["7", "8"]
    assert "Modifié" not in out and "n° 96-62" not in out