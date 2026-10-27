"""Prompts système et gabarits."""
from __future__ import annotations

from typing import Sequence

SYSTEM_PROMPT = """Tu es un assistant juridique tunisien. Tu réponds \
EXCLUSIVEMENT à partir du CONTEXTE fourni, extrait d'un corpus de textes de loi \
tunisiens indexés dans une base vectorielle.

RÈGLES ABSOLUES
1. N'utilise jamais de connaissances juridiques externes au contexte. Si le \
contexte ne permet pas de répondre, dis-le explicitement.
2. Cite systématiquement le code et le numéro d'article pour chaque affirmation \
juridique, en reprenant exactement les références présentes dans le contexte.
3. Si des articles du contexte semblent se contredire, signale-le et privilégie \
la version dont la date de dernière mise à jour est la plus récente.
4. Précise toujours la date de la version citée quand elle est disponible dans \
les métadonnées, et recommande une vérification au JORT pour toute décision \
importante.
5. Réponds dans la langue de la question (arabe si la question est en arabe, \
français si elle est en français). Si la question est en dialecte tunisien \
(Derja), réponds dans un registre simple, en arabe standard ou en français.
6. Tu n'es pas un avocat : ne présente jamais ta réponse comme un conseil \
juridique définitif.
7. Ne recopie pas de longs passages : reformule et cite.

FORMAT DE SORTIE
Tu dois répondre en appelant l'outil `emit_legal_answer`, avec :
- `answer` : la réponse rédigée.
- `citations` : liste d'objets {source, article, url, date}, une entrée par \
référence citée. Tableau vide si aucune citation ne s'applique.
- `confidence_note` : une phrase courte indiquant la limite de la réponse \
(ex. « Corpus de démonstration, non exhaustif »).
"""

DERJA_REFORMULATION_PROMPT = """La question de l'utilisateur ci-dessous est \
écrite en dialecte tunisien (Derja) ou en arabizi. Reformule-la en une question \
juridique claire, en arabe standard moderne (fusha). Si la question est en \
arabizi, transcris-la d'abord. Ne réponds PAS à la question : donne uniquement \
la reformulation, sur une seule ligne, sans préambule ni guillemets.

Question : {question}
"""

# Schéma de l'outil forcé pour la sortie structurée
ANSWER_TOOL = {
    "name": "emit_legal_answer",
    "description": "Émet la réponse juridique structurée avec ses citations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "La réponse rédigée dans la langue de la question.",
            },
            "citations": {
                "type": "array",
                "description": "Références juridiques citées.",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string",
                                   "description": "Nom du code ou de la loi."},
                        "article": {"type": "string",
                                    "description": "Numéro / libellé d'article."},
                        "url": {"type": "string",
                                "description": "Lien vers la source (JORT), si connu."},
                        "date": {"type": "string",
                                 "description": "Date de la version citée."},
                    },
                    "required": ["source", "article"],
                },
            },
            "confidence_note": {
                "type": "string",
                "description": "Note courte sur les limites de la réponse.",
            },
        },
        "required": ["answer", "citations", "confidence_note"],
    },
}


def build_context_block(articles: Sequence) -> str:
    """Construit le bloc CONTEXTE injecté dans le message utilisateur."""
    if not articles:
        return "(contexte vide — aucun article pertinent trouvé)"

    blocks: list[str] = []
    for i, art in enumerate(articles, start=1):
        meta = art.metadata
        header = (
            f"--- SOURCE {i} ---\n"
            f"Code : {meta.get('code', '?')}\n"
            f"Article : {meta.get('article_label') or meta.get('article_num', '?')}\n"
            f"Statut : {meta.get('statut', '?')}\n"
            f"Dernière mise à jour : {meta.get('date_derniere_maj') or 'inconnue'}\n"
            f"URL source : {meta.get('source_url') or 'non fournie'}\n"
            f"Type : {meta.get('type', 'article')}\n"
        )
        blocks.append(f"{header}\n{art.text}")
    return "\n\n".join(blocks)
