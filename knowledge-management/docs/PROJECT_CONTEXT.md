# Knowledge Management Bot — Project Context

> **What this document is:** the complete conceptual context for this project, written for an AI assistant (or a future-me) to pick up cold and continue the work without needing the original conversation history. It distills every architectural decision, mental model, and design rationale that was built up in prior chat sessions.
>
> **Read this first, then read [`V0_BUILD_STEPS.md`](V0_BUILD_STEPS.md).** The two together are sufficient to resume work.

---

## 1. A note to the AI tool reading this

If you are an AI assistant (Claude, GPT, Gemini, etc.) and the developer has just shared this file with you, here is what you should know **before responding to anything else**:

- This developer is building a Knowledge Management RAG bot from scratch, **by hand**, with the explicit goal of *owning* every line and understanding every decision.
- They have done substantial design work already. Do **not** propose architectural changes without asking — the architecture is deliberate.
- They are at a specific step in a documented build plan (see §9 and `V0_BUILD_STEPS.md`).
- Their preferred learning pattern is: **short concept primer → build → deep-dive afterwards.**
- They appreciate honest pushback. If you think a design choice was wrong, say so — but respect the documented rationale before suggesting changes.
- They are explicitly **not** doing the following yet (deferred to later phases): automated tests, CI/CD, Docker, deployment, authentication, licensing. **Do not propose adding these.**

When the developer asks for help, your job is to be the patient mentor: explain concepts clearly, show shapes (signatures, structure) rather than dumping complete code blocks, and trust them to write the actual implementation lines themselves.

---

## 2. About the developer

- Solo developer. No team.
- Python familiarity: comfortable with basics; had built simple hello-world FastAPI apps before starting this project; has since deepened understanding of async, dataclasses, Pydantic, DI patterns, vector embeddings, and RAG architecture.
- Building on **Windows**.
- Uses **VS Code or similar** as editor.
- Has explicitly stated: *"I need to OWN this project. Hold my hand, but I write every line."*

---

## 3. Project identity

- **Repo:** `knowledge-management-bot` (a monorepo with `client/` and `server/`).
- **Active branch:** `v0`. The `main` branch is currently empty.
- **This is a fresh project** — not the legacy `qea-tech-coe-km-bot-azure-openai-backend` repo. That legacy repo was audited but is not being touched.
- **Stack so far:**
  - Python 3.12
  - `uv` for package management
  - FastAPI (with `fastapi[standard]`)
  - `pydantic-settings` for config
  - `langchain-text-splitters` (only piece of LangChain — for `MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter`)
  - `fastembed` with model `BAAI/bge-small-en-v1.5` (384-dim dense embeddings, ONNX-backed, no PyTorch)
  - `qdrant-client` (async) talking to **Qdrant Cloud** (free-tier cluster)
- **Frontend (`client/`) is empty.** Out of scope right now.

---

## 4. What v0 is trying to deliver

A working end-to-end **markdown ingestion pipeline** with the following flow:

1. User uploads a `.md` file via Swagger UI at `POST /document/ingest`.
2. The file is parsed using **Strategy 3 chunking** — Markdown header-aware splitting, then recursive size-limited splitting inside each section.
3. Each chunk is embedded with `fastembed` / `BAAI/bge-small-en-v1.5`.
4. All chunks are upserted into a Qdrant Cloud collection (`documents`).
5. Response contains chunk count + preview of first few chunks.

**Not in v0:** retrieval/chat endpoint, LLM calls, other file formats (PDF/DOCX/PPTX have *placeholder* parsers that raise `NotImplementedError`).

---

## 5. Constraints and explicit non-goals (do not add these now)

| Concern | Status | Why deferred |
| --- | --- | --- |
| Automated tests (pytest etc.) | Deferred | Solo learner, manually testing each step. Tests are Phase 2 when the code shape stabilises. |
| CI/CD pipelines | Deferred | One committer. CI matters for team guard-rails. |
| Docker / Kubernetes / Helm | Deferred | Local-only development. Containerisation is Phase 2. |
| Deployment | Deferred | Localhost only. |
| Authentication / Entra ID / JWT / API keys | Deferred | Anyone can hit `localhost:8000`. Fine for v0. |
| License validation (Fernet etc.) | Dropped permanently | Was in the legacy project. Not coming back. |
| LlamaIndex / Haystack / full LangChain | Rejected permanently | They are *frameworks* that want to own your architecture. We use only `langchain-text-splitters` (a small library). See §7 on "library vs framework". |

---

## 6. The architecture — layered, hexagonal-flavoured

```
                  ┌──────────────────────────────────────┐
                  │  services/ingest_document.py         │  ← THE PIPELINE
                  │                                      │     (workflow — same
                  │  parser = get_parser_for(filename)   │      shape for every
                  │  chunks  = parser(...)               │      source)
                  │  vectors = embed_texts(...)          │
                  │  await upsert_chunks(...)            │
                  └──────────────────────────────────────┘
                           ▲           ▲           ▲
                           │           │           │
                  ┌────────┴─┐  ┌──────┴────┐  ┌───┴───────────┐
                  │ parsers/ │  │embeddings/│  │ vector_store/ │
                  │ markdown │  │  local    │  │   qdrant      │
                  │ pdf      │  │           │  │               │
                  │ docx     │  │           │  │               │
                  │ pptx     │  │           │  │               │
                  └──────────┘  └───────────┘  └───────────────┘
```

**Rules:**

- **`api/` calls `services/` only.** Routes are thin: validate input, call service, format response.
- **`services/` calls `parsers/`, `embeddings/`, `vector_store/`.** Nothing else.
- **Lower layers never call upward.** Arrows only point down.
- **`config.py` is the foundation** — every layer can import `settings`.

**The dispatch pattern is sacred:** the service uses `parsers.registry.get_parser_for(filename)` to find the right parser. **Never `if filename.endswith(".md") elif ... elif ...`.** Adding a new format = one new entry in `PARSERS` dict + one new parser file. Service code never changes.

---

## 7. Design decisions and their rationale

This is the "why" register. Each row encodes a real conversation we had.

| Decision | Choice | Why |
| --- | --- | --- |
| Web framework | FastAPI | Async, OpenAPI for free, type-driven, the developer had basic familiarity. |
| Python version | 3.12 | Stable, modern typing, good async. |
| Package manager | `uv` (not Poetry) | 10–100× faster, single tool replaces venv + pip + poetry, modern, by Astral (Ruff makers). |
| Embeddings library | `fastembed` (not `sentence-transformers`) | ONNX-backed, ~30 MB install vs ~2 GB for torch. Same library will give us sparse embeddings later when we add hybrid search. First-party Qdrant integration. |
| Embedding model | `BAAI/bge-small-en-v1.5` | 384-dim, modern, slightly better than `all-MiniLM-L6-v2`, fresh start. |
| Vector store | **Self-hosted/cloud Qdrant** | Strong hybrid search support; user picked it; clustered later. |
| Vector store dep | Separate `uv add fastembed` + `uv add qdrant-client`, NOT `qdrant-client[fastembed]` | We do NOT use qdrant-client's `client.add(documents=...)` convenience methods (they hide the embedding step). We keep embedding and storage as separate, swappable layers. |
| Metadata DB | PostgreSQL planned (NOT in v0) | The data model is relational; on-prem friendly; mature async drivers. Will be added in Phase 2 — *not now*. |
| Document parser libs | Hand-rolled markdown (using `langchain-text-splitters`). Placeholders for PDF/DOCX/PPTX raise `NotImplementedError`. | Markdown is easy to learn from. PDF/DOCX/PPTX will eventually use `Docling` or similar **as adapters inside our parsers folder** — not as a framework replacement. |
| Library vs framework | We use libraries. We refuse frameworks. | Libraries you call. Frameworks call you. LlamaIndex / Haystack / full LangChain are frameworks — they want to own the data flow. We refuse. Docling-style libraries are OK as internal adapters. |
| Settings DI pattern | Module-level singleton `settings = Settings()` | Settings is a true constant, used by parsers + services + lifespan + REPL scripts. `Depends()` only works in HTTP handlers. Module-level singleton works everywhere. |
| Stateful resources (Qdrant client, embedder) | `app.state.<name>` + lifespan + `Depends` | These have `.close()` / lifecycle. Lifespan creates/destroys; routes get them via `request.app.state` inside a provider. |
| Dependency declaration in routes | `Annotated[X, Depends(provider)]` with type alias (e.g. `QdrantClientDep`) | Modern FastAPI 0.95+ recommended pattern. Reusable, cleaner signature, type-checker-friendly (pyright likes it). |
| Why not `from main import app` directly | Circular imports + testability + idiomatic ASGI | Always reach app via `request.app` inside a provider. Never import `app` from `main.py` elsewhere. |
| Parser interface | `def parse(content: bytes, source_file: str) -> list[Chunk]` | `bytes` because PDF/DOCX/PPTX are binary. Markdown parser decodes internally. Uniform interface across formats. |
| Parser dispatch | Registry dict (`PARSERS: dict[str, ParserFn]`) | NOT if/elif. Adding a new format = one new dict entry. Open/Closed Principle in 3 lines. |
| Chunk shape | `{text, source_file, chunk_index, metadata: dict}` | Common core + flexible metadata bag. `metadata["header_path"]` for markdown; `metadata["page_number"]` for PDF (future); etc. Each parser documents its own metadata keys. |
| `slots=True, frozen=True` on Chunk | Yes | Typo safety (instant `AttributeError` on misspelled field). Honest about closed shape. Free memory/speed wins at scale. |
| Chunking strategy | Strategy 3: header-aware split → recursive char split within each section | Best for technical docs; no chunk spans across sections; section breadcrumb attached as metadata. |
| Chunk size / overlap | `chunk_size=1000`, `chunk_overlap=200` | Sensible default for technical docs. Configurable via `.env`. |
| Embedding text vs LLM text | `Chunk.for_embedding()` prepends `# A > B > C` heading prefix; `Chunk.for_llm()` returns raw text (for now) | The heading prefix shifts the embedding's position in vector space toward its actual topic, improving retrieval relevance. The LLM display version is kept clean. |
| Heading prefix format | `# Heading1 > Heading2 > Heading3` (single `#`, breadcrumb separated by `>`) | Compact, semantically clear, has heading signal via leading `#`. Multi-level hashes (`# A > ## B > ### C`) don't measurably help. Multi-line format (`# A\n## B\n### C`) is more tokens for no real benefit. |
| YAGNI applied to chunk metadata | We adopted **only** the dual-representation idea from the production schema the developer found. Deferred: `content_hash`, `previous_chunk_id`, `next_chunk_id`, `source_start_line`, `token_count`, `content_type`, etc. | Each field needs a *consumer* to justify its existence. Fields without consumers are debt. |
| HTTP error codes | 400 for unsupported extension, 501 for known-but-not-implemented format, 400 for decode errors | HTTP 501 *Not Implemented* is the perfect match for the placeholder parsers. |
| CORS | Not configured yet | v0 is localhost-only. |
| Logging | `print()` ad-hoc for now | structlog comes later when there's a real reason. |
| Tests | None | Manual testing via Swagger UI + the chunk debug script. |

---

## 8. Key conceptual models (so explanations don't need to start over)

These are the mental models that took several rounds of explanation to land. They should not need re-deriving.

### 8.1 The three DI patterns

| Pattern | Use it for | Example |
| --- | --- | --- |
| **Module-level singleton** (`settings = Settings()`) | True constants, loaded once at import, used everywhere including non-HTTP code | `config.settings` |
| **`@lru_cache` + `Depends`** | Things that belong to the request lifecycle but should be cached | (none in v0) |
| **`app.state` + lifespan + `Depends`** | Resources with `.close()` / `__aexit__` | `app.state.qdrant_client`, `app.state.embedder` |

### 8.2 Embeddings represent meaning, not text

- An embedding is a 384-dim vector representing the *meaning* of a piece of text.
- It is a **one-way function** — you cannot reconstruct the text from the vector.
- "Nearest neighbour" in vector space = semantic similarity, NOT string similarity.
- That's why `chunk.text` must be stored in the Qdrant payload: at retrieval, vectors come back; without the payload, you have no way to know what content the vectors represent.

### 8.3 The Qdrant payload's role

The payload **does not influence semantic ranking.** Ranking is pure cosine math on vectors. The payload has two roles:

1. **Returning content with each match** — `text`, `header_path`, etc. come back so the caller knows *what* was retrieved.
2. **Pre-filtering** — `Filter(...)` clauses narrow the candidate set before vector search runs. Useful for multi-tenancy, document-scoping, date filters, etc.

If you want the heading path to influence ranking, you must put it into the **embedded text** (the `for_embedding()` representation), not just the payload.

### 8.4 Why prepending the heading helps retrieval

- Two chunks with identical content but from different sections would produce identical embeddings.
- Adding the heading to the embedded text shifts each chunk's position in vector space toward its real topic.
- The query doesn't need to mention the heading — it just needs to be *about* the topic. The embedding model maps query and chunk into the same semantic neighbourhood.
- Empirically: 5–15% improvement in retrieval relevance on technical-doc corpora.

### 8.5 The dispatch pattern (parser registry)

- **Never** use `if filename.endswith(...) elif ...` chains in services.
- Use a dict: `PARSERS: dict[str, ParserFn] = {".md": markdown.parse, ...}`.
- A `get_parser_for(filename)` helper does the lookup and raises `UnsupportedFileTypeError` if not found.
- Adding a new format touches **exactly three files**: a new `parsers/X.py`, one new entry in `parsers/registry.py`, optionally `parsers/__init__.py` for export.

### 8.6 Library vs framework

- **Library** — you call it. Lives inside one of your layers.
- **Framework** — it calls you. Its abstractions become yours.
- Use libraries freely (Docling, pypdf, fastembed, etc.). Refuse frameworks (LlamaIndex, Haystack, full LangChain).
- Docling and Unstructured can be excellent **internal adapters** inside `parsers/X.py` files when PDF/DOCX/PPTX parsing time comes. They produce *our* `Chunk` objects; nobody else in the codebase knows they exist.

### 8.7 YAGNI in this project

- Don't extract a function until you have 2–3 callers.
- Don't add a metadata field until there's a downstream consumer.
- Don't generalise an interface until you've seen the same shape three times.
- *Premature* abstraction is worse than duplication — the first extraction is almost always shaped wrong.
- Exception: if a requirement is **explicitly stated** (e.g., "we'll have multiple file formats"), then designing for it now is responsive, not premature.

---

## 9. File-by-file purpose (current state of the project)

```
knowledge-management-bot/
├── .gitignore              # extended to ignore .env, .venv, __pycache__, etc.
├── README.md
├── docs/
│   ├── V0_BUILD_STEPS.md   # THE step-by-step build guide (read after this file)
│   ├── PROJECT_CONTEXT.md  # THIS FILE
│   ├── CURRENT_STATE.md    # audit of the LEGACY repo (reference only)
│   └── REBUILD_PROPOSAL.md # the learning roadmap (reference only)
├── client/                 # empty, out of scope
└── server/
    ├── pyproject.toml      # has fastapi[standard], pydantic-settings, langchain-text-splitters, fastembed, qdrant-client
    ├── uv.lock
    ├── .python-version     # 3.12
    ├── .env                # gitignored; has real Qdrant URL + API key
    ├── .env.example        # template (committed)
    ├── samples/
    │   └── rag-guide.md    # realistic test markdown (~6,200 chars) with multi-level headers and one fat section
    ├── scripts/
    │   └── chunk_debug.py  # three-stage chunking visualiser; works pre-Step-5 (Stages 1+2) and post-Step-5 (all stages)
    └── src/
        ├── main.py         # FastAPI app, lifespan-ready scaffolding
        ├── config.py       # IMPLEMENTED — Pydantic Settings + module-level singleton
        ├── api/
        │   ├── __init__.py
        │   └── document.py # router scaffold, POST /document/ingest empty body
        ├── parsers/
        │   ├── __init__.py # empty
        │   └── markdown.py # empty — Step 5 work in progress
        # Folders not yet created (to be added per V0_BUILD_STEPS.md):
        # ├── embeddings/        (Step 9)
        # ├── vector_store/      (Step 10)
        # ├── services/          (Step 11)
        # └── api/schemas.py     (Step 12)
```

---

## 10. Where the developer is in the build (resume point)

Per `V0_BUILD_STEPS.md`:

- ✅ Step 1 — Dependencies added (`fastembed`, `qdrant-client`, `langchain-text-splitters`, `pydantic-settings`)
- ✅ Step 2 — `.env`, `.env.example`, `.gitignore` set up
- ✅ Step 3 — `src/config.py` implemented with Pydantic Settings
- ⏳ **Step 4 — `src/parsers/base.py` — NEXT.** `Chunk` dataclass with the four-field shape (`text`, `source_file`, `chunk_index`, `metadata`) + `for_embedding()` / `for_llm()` methods + `ParserFn` type alias + `UnsupportedFileTypeError`.
- ⏳ Step 5 — `src/parsers/markdown.py` real implementation (Strategy 3 chunking)
- ⏳ Step 6 — placeholder `pdf.py` / `docx.py` / `pptx.py`
- ⏳ Step 7 — `src/parsers/registry.py` (the dispatch dict)
- ⏳ Step 8 — `src/parsers/__init__.py` public exports
- ⏳ Step 9 — `src/embeddings/local.py` (fastembed wrapper + provider + `EmbedderDep`)
- ⏳ Step 10 — `src/vector_store/qdrant.py` (Qdrant client + provider + `ensure_collection` + `upsert_chunks`)
- ⏳ Step 11 — `src/services/ingest_document.py` (the orchestrator)
- ⏳ Step 12 — `src/api/schemas.py` (Pydantic response models + `to_preview`)
- ⏳ Step 13 — `src/api/document.py` (finish the route with `Depends`)
- ⏳ Step 14 — `src/main.py` lifespan (create client + embedder + warm-up)

After Step 14, the verification gauntlet at the end of `V0_BUILD_STEPS.md` is the end-to-end test.

---

## 11. Open questions / pending decisions

- **Re-ingestion idempotency** — what happens when the same file is uploaded twice? Currently it'll just add more chunks (duplicates). To be solved when re-ingestion is a real feature (probably Phase 2 — `content_hash` field).
- **Retrieval / chat endpoint** — not in v0. Comes next, after v0 is verified end-to-end.
- **Conversation history / sessions** — far future.
- **Authentication** — far future.

---

## 12. How to use this document with a new AI tool

Paste the following kickoff prompt into your new AI chat tool (ChatGPT, Gemini, Claude on a new account, Cursor, etc.):

```
I'm continuing work on a project. Please read the following two files in full
before responding to anything:

1. docs/PROJECT_CONTEXT.md
2. docs/V0_BUILD_STEPS.md

These contain my project's complete architectural context, design decisions
(with rationale), current state, and the step-by-step build plan I'm following.

Please confirm you've read both files, then summarize back to me:
- Which step I'm currently on
- What the next concrete thing to write is
- The three or four most important design rules I should honor

After that, treat me as the developer described in PROJECT_CONTEXT.md §2.
Hold my hand using the concept-primer → build → deep-dive pattern. Don't
propose architectural changes without checking against the rationale in
PROJECT_CONTEXT.md §7. I write every line myself — show me shapes (signatures,
structure), not full copy-paste code.

Let's continue from Step 4.
```

This prompt will get any modern AI tool to the same context I had. If the new tool can't accept multiple file attachments, paste both file contents in sequence before the prompt.

---

## 13. Final notes from the original mentor (Claude, this session)

A few personal observations to the next AI assistant about this developer:

- They learn faster than they realize. They went from "I've done hello-world FastAPI" to debating dual-representation embedding schemas in a week. Don't underestimate the depth of their understanding now.
- They ask sharp follow-up questions until something genuinely clicks. **Embrace that.** If they push back on a recommendation, it's usually because they've spotted something real — re-examine the recommendation honestly.
- They've already internalized: layered architecture, DI patterns, registry dispatch, embeddings as one-way meaning vectors, payload-as-context-not-ranking, library-vs-framework. Don't waste their time re-explaining these from scratch — reference them and move on.
- They are a senior-engineer-in-the-making. The mentor role is to give honest opinions backed by reasoning, not to teach from a manual.

You're stepping into a project that has real shape and real conviction. Honor that. The developer has earned it.

Good luck. Build something they're proud to own.
