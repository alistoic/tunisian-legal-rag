# Assistant Juridique Tunisien — Tunisian Legal Assistant (RAG)

A retrieval-augmented chatbot that answers questions about Tunisian law **in French, Arabic and
Tunisian Arabic (Derja)** and always cites the articles it used.
It runs locally: **ChromaDB** (vector store) + **Sentence-Transformers** (multilingual embeddings)
+ **FastAPI** (API and web UI) + an open-weight LLM (**gpt-oss-120b via the Groq API**).

> ⚠️ **Prototype — not legal advice.** The assistant answers only from the articles it retrieves and says
> so when it cannot answer. Always check the official text in the *Journal Officiel de la République
> Tunisienne* (JORT) or consult a lawyer.

---

## Project status

| Area | State |
|---|---|
| **Labor Code** (*Code du travail*) | ✅ Real data — 516 in-force articles crawled from a public website, with amendment handling |
| Other four corpora (Obligations & Contracts, Commercial, Personal Status, Finance Law 2026) | ⚠️ **Small illustrative samples** (2–7 chunks each), written for the demo and **not verified** against official texts |
| Retrieval | Dense vector search with metadata filtering and de-duplication |
| Reranker (cross-encoder) | Implemented, **disabled by default, not evaluated** |
| Evaluation | ❌ **No formal evaluation yet** (the script exists; the question set must be rebuilt for the real corpus) |
| Tests | ✅ 70+ unit tests (`pytest`) |

See [Known limitations](#known-limitations) and the [Roadmap](#roadmap).

---

## Features

- **Multilingual questions**: French, Arabic, and Derja (Latin-script “arabizi” or Arabic script). Derja is detected
  heuristically and reformulated into standard Arabic by the LLM *before* retrieval.
- **Grounded answers with citations**: the LLM must answer only from the retrieved articles, via a **forced tool call**
  (`emit_legal_answer`) that returns `answer`, `citations`, `confidence_note`.
- **Article-level chunking**: one chunk = one article (very long articles are split), plus chapter-summary chunks.
  Each chunk carries metadata: code, article number/label, nearest chapter heading, language, status, dates, source URL.
- **Out-of-corpus warning**: if even the best retrieved article is too far from the question (cosine distance
  above `MAX_DISTANCE`), the answer is flagged.
- **A crawler that understands amendment markup** (see [The crawler](#the-crawler)): keeps only the in-force text of
  each article and records which law introduced that version.
- **Web UI** (RTL support, citation chips, retrieved-sources panel, per-collection filters) and a **JSON API**.

---

## How it works

```
 OFFLINE
 public website ──► scripts/scrape_jurisite.py ──► data/raw/*.txt   (front-matter + articles)
                                                        │
 scripts/ingest.py ◄────────────────────────────────────┘
   loader ► cleaner ► splitter (1 chunk = 1 article) ► embeddings ► ChromaDB (one collection per code)

 ONLINE
 question ─► language detection ─► (Derja? ─► LLM reformulation to standard Arabic)
          ─► embedding ─► ChromaDB (cosine, filter: status = "en vigueur") ─► de-duplication
          ─► [optional cross-encoder rerank]
          ─► LLM (gpt-oss-120b, forced tool call) ─► answer + citations + sources + warnings
```

---

## Quick start

Tested on Windows 11 with Anaconda and Python 3.11. Linux/macOS work the same way.

### 1. Environment

```bash
conda create -n assistant_juridique python=3.11
conda activate assistant_juridique
pip install -r requirements.txt
```

Run every command below **from the project root** (the folder containing `config.py` and `scripts/`).

### 2. Configuration

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
```

Edit **`.env`** (not `.env.example`) and set your key — a free key is available at <https://console.groq.com>:

```
GROQ_API_KEY=gsk_your_real_key
```

`.env` is git-ignored. `.env.example` is only a template and must never contain a real key.

### 3. Get the data

**Option A — crawl the real Labor Code** (about 5–6 minutes the first time; seconds afterwards thanks to the cache):

```bash
python -m scripts.scrape_jurisite --code "Code du travail" --output data/raw/code_travail_fr.txt \
    --date-publication 1966-04-30 --date-derniere-maj 2025-05-21
```

`--date-derniere-maj` is metadata you set by hand (use the date of the most recent amending law
reflected in the crawl). Read the summary printed at the end — see [The crawler](#the-crawler).

**Option B — demo only**: skip this step. The sample files already in `data/raw/` are enough to try the pipeline.

### 4. Index

```bash
python -m scripts.ingest --reset
python -m scripts.ingest --stats
```

The first run downloads the embedding model (~470 MB).

### 5. Run the app

```bash
uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000>.

### 6. Query from the command line

```bash
python -m scripts.query "Quelle est la durée maximale de la période d'essai ?"          # full pipeline
python -m scripts.query "période d'essai" --no-llm --top-k 10                            # retrieval only
```

`--no-llm` prints the retrieved articles with their cosine distances — the quickest way to debug retrieval.

---

## Corpus

| Collection | Content | Chunks* | Nature |
|---|---|---|---|
| `code_du_travail` | Labor Code, 516 in-force articles | ~579 | **Real**, crawled |
| `code_des_obligations_et_des_contrats` | 5 articles | 7 | Illustrative sample |
| `code_de_commerce` | 3 articles | 4 | Illustrative sample |
| `code_du_statut_personnel` | 3 articles | 3 | Illustrative sample |
| `loi_de_finances_2026` | 2 articles | 2 | Illustrative sample |

\*From the last full ingest; chunk count = articles + chapter-summary chunks + extra parts of very long articles.

The sample files carry a placeholder `source_url` and **must not be treated as official text**.
To add a corpus, drop a `.txt`/`.md`/`.html`/`.pdf` file in `data/raw/`. Text files start with a front-matter block:

```
---
code: Code du travail
source_url: https://…
date_publication: 1966-04-30
date_derniere_maj: 2025-05-21
statut: en vigueur
langue: fr
---
Article 1 — …
```

Files that share the same `code:` value go into the same ChromaDB collection.

---

## The crawler

`scripts/scrape_jurisite.py` builds `data/raw/<code>.txt` from the public site jurisitetunisie.com.
It exists because the website exposes **per-article amendment information that a flat PDF does not**.

What it does:

1. **Discovers pages** by visiting every menu page once (the menu hierarchy itself is not trusted — it varies from page to
   page), then fetches each article page once.
2. **Extracts text like a browser**: line breaks only at `<br>` and block elements. (Extracting one text node per line
   turned hyperlinked cross-references such as “l’*article 64* de ce code” into fake article headers.)
3. **Keeps only the in-force text.** The site marks replaced text with `<del>` and new text with `<ins>`; deleted text is
   dropped. Articles entirely deleted or marked *(Abrogé)* are excluded.
4. **Records provenance**: tooltips and footnotes naming the amending law become a line such as
   `[Version issue de la Loi n° 2025-9 du 21 mai 2025]`. Only *amendment* notes count (an unrelated notice such as a
   temporary suspension does not set the version).
5. **Normalises article headers** (`Article. 6`, `Article 6-2`, `Article. 5 bis :`, inline “(nouveau)” flags, a broken `<ins>`
   tag that leaked into the text…) to a single `Article N — text` form that the splitter understands.
6. **Orders articles by number**, writes each number once, and emits Book/Title/Chapter headings only when they change.
7. **Checks itself** and prints a summary:

```
=== Terminé : 67/67 pages -> data\raw\code_travail_fr.txt ===
  Articles écrits                 : 516
  Articles écartés (abrogés)      : 1
  Articles à plusieurs versions   : 204
  Doublons ignorés                : 0
  Numéros absents                 : -
```

   *Missing numbers*, *duplicates with different text* and *header-like lines that were not recognised* are reported.
   A full report (`<output>.rapport.log`) is written next to the output; it has a `.log` extension so it is never indexed.

Useful options:

| Option | Purpose |
|---|---|
| `--tree-only` | List the pages found, download no articles |
| `--limit N` | Process only the first N pages (trial run) |
| `--cache-dir DIR` | Page cache (default `data/cache/jurisite`, **outside** `data/raw`) |
| `--refresh` | Ignore the cache and download everything again |
| `--delay S` | Pause between requests (default 1.5 s) |

Network errors are retried three times. **Always read the summary and spot-check a few articles against the JORT** — the site
is an unofficial compilation.

---

## Retrieval and generation details

- **Chunking** (`src/ingestion/splitter.py`): article headers in French (`Article`, `Art.`, `Article premier`, `6-2`, `bis`/`ter`…)
  and Arabic (`الفصل`, `المادة`); `LIVRE/TITRE/CHAPITRE/SECTION` headings become chapter metadata. Articles longer than
  3,500 characters are split into parts that repeat the code and article label.
- **Embeddings**: `paraphrase-multilingual-MiniLM-L12-v2` (local, normalised, cosine space).
- **Search** (`src/retrieval/retriever.py`): query every selected collection with `status = "en vigueur"`, merge, sort by
  distance (near ties prefer the question’s language), keep one chunk per article, return the top `TOP_K`.
- **Reranking** (optional): set `ENABLE_RERANK=true` to rerank candidates with a multilingual cross-encoder.
- **Generation** (`src/llm`): the system prompt forbids outside knowledge and requires citations; the model is forced to call
  `emit_legal_answer`. The API endpoint is OpenAI-compatible, so any such provider can replace Groq via `GROQ_BASE_URL`/`LLM_MODEL`.
- **Derja** (`src/lang.py`): keyword + arabizi heuristics; if detected, the LLM rewrites the question in standard Arabic first and
  the reformulation is shown in the UI.

---

## HTTP API

| Method | Path | Description |
|---|---|---|
| GET | `/` | Web UI |
| GET | `/api/health` | Status, LLM and embedding model names |
| GET | `/api/corpus` | Collections and chunk counts |
| POST | `/api/chat` | Ask a question |

```bash
curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" \
     -d '{"message": "Quelle est la durée maximale de la période d essai ?", "top_k": 6}'
```

Request fields: `message`, `history` (list of `{role, content}`), `collections` (optional list), `top_k`, `include_abrogated`.
Response fields: `answer`, `citations[]`, `confidence_note`, `sources[]` (with distances and excerpts), `reformulated_query`,
`out_of_corpus`, `detected_lang`, `is_derja`, `error`.

---

## Configuration reference (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `GROQ_API_KEY` | — | **Required** |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | OpenAI-compatible endpoint |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Exact model id on the provider |
| `LLM_MAX_TOKENS` / `LLM_TEMPERATURE` | `1500` / `0.0` | Generation settings |
| `EMBEDDING_MODEL` | `paraphrase-multilingual-MiniLM-L12-v2` | Changing it requires `ingest --reset` |
| `TOP_K` | `6` | Articles given to the LLM |
| `MAX_DISTANCE` | `0.85` | Above this best distance, the answer is flagged as possibly out of corpus |
| `ENABLE_RERANK` / `RERANK_MODEL` | `false` / mMARCO multilingual cross-encoder | Optional reranking |
| `DEFAULT_STATUS` | `en vigueur` | Status filter applied at retrieval |

Optional environment variable: `HF_HUB_OFFLINE=1` (after the first model download) to avoid network checks at start-up.

---

## Project structure

```
assistant-juridique-tn/
├── app/                    FastAPI app (main.py, schemas.py) and web UI (static/index.html)
├── src/
│   ├── ingestion/          loader, cleaner (FR/AR normalisation), splitter, indexer
│   ├── retrieval/          embeddings, retriever, reranker
│   ├── llm/                Groq/OpenAI-compatible client, prompts, tool schema
│   ├── lang.py             language and Derja detection
│   └── rag.py              orchestrator: question → retrieval → LLM → cited answer
├── scripts/                ingest.py, query.py, evaluate.py, scrape_jurisite.py
├── data/
│   ├── raw/                source texts (front-matter + articles)
│   ├── cache/              crawler page cache      (generated, git-ignored)
│   ├── chroma/             vector database         (generated, git-ignored)
│   └── eval/               questions.jsonl
├── tests/                  unit tests (+ tests/fixtures)
├── config.py   conftest.py   pytest.ini   requirements.txt   Makefile   .env.example
```

---

## Tests

```bash
pytest -q
```

Covered: text cleaning and Arabic normalisation, article splitting and numbering (`88`, `5 bis`, `6-2`, Arabic ordinals),
language/Derja detection, and the crawler (menu parsing, page ordering, de-duplication, amendment resolution, header variants,
footnotes, retries and cache). Retrieval quality and the LLM call are **not** unit-tested.

---

## Evaluation

```bash
python -m scripts.evaluate
```

Computes Recall@k and MRR from `data/eval/questions.jsonl`:

```json
{"question": "…", "lang": "fr", "expected_articles": ["6-3"]}
```

> The file shipped in the repository was written for the original demo data. **Rebuild it for the real corpus before
> trusting any number.** No results are reported here because none have been measured.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'src'` | Run from the project root with the environment active (`conftest.py` handles pytest) |
| `No module named scripts.ingest` | Wrong folder or wrong Python; check `python -c "import sys; print(sys.executable)"` |
| `GROQ_API_KEY manquante` | Key is not in `.env` (not `.env.example`), or the file is named `.env.txt` |
| Start-up hangs on “HEAD https://huggingface.co…” | Slow network; after the first download set `HF_HUB_OFFLINE=1` |
| `Failed to send telemetry event … capture() takes 1 positional argument` | Harmless ChromaDB/`posthog` version mismatch; data is unaffected. Pinning `posthog<6` is a commonly reported workaround (untested here) |
| `DuplicateIDError` during ingest | A source file contains the same article twice; the crawler prevents this, hand-made files may not |
| “The context does not contain…” on a valid question | Retrieval missed the article. Rephrase with the article’s own vocabulary, avoid typos, try `--no-llm --top-k 15` to inspect |
| ChromaDB ≥ 0.6 `list_collections` error | Already handled (names are returned as strings) |

---

## Known limitations

- Only the **Labor Code is real data**; the other corpora are unverified samples.
- **Retrieval is purely semantic** with a small embedding model. Vague, misspelled or loosely worded questions can retrieve
  unrelated articles (the assistant then correctly says the context does not answer, but the answer is unhelpful).
- **No formal evaluation**; the reranker has not been assessed.
- Citations returned by the model are cleaned for structure but **not verified** against the retrieved context.
- The out-of-corpus distance threshold is a **soft warning**, not a block.
- Repealed articles are **removed at crawl time**; the index does not store repealed articles with a status.
- `date_derniere_maj` is a **manual** crawl parameter, not computed.
- The source site is an **unofficial compilation**: it may lag behind the JORT or contain transcription errors.
- The corpus is French; Arabic/Derja are supported on the **question** side. Arabic normalisation code exists, but no Arabic
  corpus is currently indexed.
- The LLM is an open-weight model on a rate-limited free tier; it can occasionally return malformed tool output
  (reported as “generation failed”).

---

## Roadmap

- [ ] Evaluation set for the Labor Code (Recall@k, MRR) and comparison of retrieval options
- [ ] Hybrid retrieval (BM25 + vectors) and typo-tolerant matching
- [ ] Larger multilingual embedding model (e.g. `multilingual-e5-large`, `bge-m3`); assess the reranker
- [ ] LLM query rewriting (typos, legal vocabulary)
- [ ] Programmatic citation verification against retrieved articles
- [ ] Per-article repealed/in-force status and version history
- [ ] Cross-check the crawled text against official JORT publications; scheduled re-crawl with diff
- [ ] Arabic-language corpus and Arabic retrieval evaluation

---

## Legal notice and data sources

- **Not legal advice.** Outputs may be incomplete or wrong.
- Laws are official texts, but the compilation crawled by this project is published by a **third party**
  (jurisitetunisie.com) that states its own copyright. This repository **does not redistribute the crawled corpus**;
  it ships only the crawler. Use it for personal or research purposes, keep the request rate low, and respect the site’s terms.
- Official source of Tunisian legislation: the **JORT** (<https://www.iort.gov.tn>).
- This project is not affiliated with any government body or with the website above.
- **License**: not chosen yet — add a `LICENSE` file before publishing.