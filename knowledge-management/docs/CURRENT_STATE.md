# Current State — `qea-tech-coe-km-bot-azure-openai-backend`

> **Audit date:** 2026-05-19
> **Scope:** Full backend codebase as it stands on `main` after commit `00513a9` (License-generator-integration merge).
> **Posture:** Factual inventory only. No recommendations — those live in [`REBUILD_PROPOSAL.md`](REBUILD_PROPOSAL.md).

---

## 1. Executive Summary

This repository is a **Knowledge Management (KM) bot backend** — a FastAPI service that answers natural-language questions about an internal corpus of documents (PDF, Word, PowerPoint, Markdown, audio, video) using a Retrieval-Augmented Generation (RAG) pipeline.

| Property | Value |
| --- | --- |
| Author of record | GitHub user `848566` (`pyproject.toml:5`) |
| Last meaningful commit | `893271e` — *Final Changes for IP ready* |
| Project status | Dormant — no work in ~2 years |
| Primary language | Python (`^3.10`) |
| Web framework | FastAPI `0.111.1` on Uvicorn `0.30.5` |
| LLM (cloud) | Azure OpenAI — deployment `gpt35exploration` (GPT-3.5-Turbo) |
| LLM (local) | Microsoft Phi-3-mini Q4 GGUF via `llama-cpp-python` |
| Vector store | Qdrant (embedded, file-based) — hybrid dense + sparse |
| Metadata store | MongoDB (async via Motor) |
| Access control | Custom Fernet-encrypted license key bound to MAC address and validity window |
| Test automation | None — `test/` contains manual scripts only |
| CI/CD | None |
| Container / deploy | None — bare `uvicorn.run` |

### Architecture at a glance

```
                    ┌───────────────────────────────┐
   HTTP client ───► │  FastAPI app (src/main.py)    │
                    │  ┌────────┬────────┬────────┐ │
                    │  │ /chat  │/database│/cached-│ │
                    │  │        │         │question│ │
                    │  └────────┴────────┴────────┘ │
                    └──────────┬────────────────────┘
                               │ License gate (per route)
                               ▼
                    ┌───────────────────────────────┐
                    │ LLMChains (orchestrator)      │
                    │ — 364-line method             │
                    └──┬──────────┬────────┬────────┘
                       │          │        │
                       ▼          ▼        ▼
              ┌────────────┐  ┌────────┐  ┌────────────┐
              │ Qdrant     │  │ Mongo  │  │ Azure      │
              │ (embedded) │  │ (Motor)│  │ OpenAI /   │
              │ hybrid     │  │ cached │  │ Phi-3      │
              │ search     │  │ Q&A    │  │            │
              └─────┬──────┘  └────────┘  └────────────┘
                    │
                    ▼
       ┌────────────────────────────┐
       │ Parsers (PDF/DOCX/PPTX/MD/ │
       │   media → chunks)          │
       └────────────────────────────┘
```

---

## 2. Repository Layout

```
qea-tech-coe-km-bot-azure-openai-backend/
├── .gitignore                            # 179 lines; notably also ignores poetry.lock and pyproject.toml
├── README.md                             # 34 lines, install steps only
├── pyproject.toml                        # Poetry manifest
├── poetry.lock                           # 512 KB
├── requirements.txt                      # one line: poetry==1.7.1
├── sample_config_env/
│   ├── sample.env                        # 19 env-var template
│   └── sample_config.json                # 108-line runtime config template
├── src/
│   ├── CONSTANTS.py                      # collection names, file-type map, Fernet key + separator
│   ├── main.py                           # FastAPI bootstrap
│   ├── database_layer/
│   │   ├── mongo_data_interface/
│   │   │   └── MongoClient.py            # Motor async client
│   │   └── vector_data_interface/
│   │       ├── QdrantClient.py           # Qdrant client (~632 lines)
│   │       ├── CustomQdrantClient.py
│   │       └── QdrantFastEmbed.py        # Hybrid search support
│   ├── db_service_layer/
│   │   ├── MongoDbServices.py            # Cached Q&A service
│   │   └── VectorDbServices.py           # Ingestion + retrieval service
│   ├── llm_clients/
│   │   ├── AzureOpenAi.py                # All LangChain chains for GPT-3.5
│   │   └── MicrosoftPhi.py               # Local Phi-3 wrapper
│   ├── llm_service_layer/
│   │   └── llm_chains.py                 # 364-line orchestrator
│   ├── routes/
│   │   ├── ChatInterface.py              # /chat
│   │   ├── DataHandling.py               # /database
│   │   └── CachedQuestion.py             # /cached-question
│   ├── parsers/
│   │   ├── BaseParser.py
│   │   ├── WordParser.py                 # PDF + DOC/DOCX, uses LiLT layout model
│   │   ├── MarkdownParser.py
│   │   ├── PPTParser.py
│   │   ├── ParseTable.py
│   │   ├── word_parser/
│   │   │   ├── VisionDocumentParser.py   # ~627 lines, layout-aware PDF
│   │   │   └── WordDocumentTableParser.py
│   │   └── media_parsers/
│   │       ├── MediaTranscribe.py        # Whisper small.en, 60-sec chunks
│   │       └── VideoTextExtraction.py    # Frame-level OCR
│   ├── pydantic_models/view_models/
│   │   ├── ChatData.py                   # Request/response schemas
│   │   └── LikeDislike.py                # Feedback schemas
│   ├── utilities/
│   │   ├── AppLogger.py                  # Loguru global logger
│   │   ├── StartupUtilities.py           # Singleton DI container
│   │   ├── DocumentChunker.py            # RecursiveCharacterTextSplitter 6000/500
│   │   ├── WordParserUtilities.py        # Doc format conversion (Windows COM)
│   │   ├── DButils.py                    # Filesystem helpers
│   │   ├── PromptLogger.py               # Per-chain Excel prompt log
│   │   └── utils.py                      # UUIDs, MAC address, regex helpers
│   ├── github_automation/
│   │   └── GithubAutomater.py            # GitPython-based clone/pull
│   └── license_checker/
│       └── validate_license.py           # Fernet license decoder + checks
└── test/
    ├── __init__.py
    ├── TestDocumentParsing.py            # 31 lines — manual usage script
    ├── TestFiles.py                      # 448 lines — manual utility class
    └── TestQuestions.py                  # 60 lines — manual HTTP smoke
```

The repo has **no `docker/`, no `deploy/`, no `.github/`, no `Makefile`, no infra code, and no ADRs**.

---

## 3. Runtime & Dependencies

### 3.1 Runtime

| Property | Value | Source |
| --- | --- | --- |
| Python | `^3.10` | [pyproject.toml:9](../pyproject.toml#L9) |
| Package manager | Poetry `1.7.1` (frozen) | [requirements.txt](../requirements.txt) |
| ASGI server | Uvicorn `0.30.5` | [pyproject.toml:14](../pyproject.toml#L14) |
| Web framework | FastAPI `0.111.1` | [pyproject.toml:15](../pyproject.toml#L15) |

### 3.2 Direct dependencies

| Package | Pinned version | Role |
| --- | --- | --- |
| `fastapi` | `0.111.1` | REST framework |
| `uvicorn` | `0.30.5` | ASGI server |
| `langchain` | `>=0.2.12,<0.3.0` | LLM orchestration |
| `langchain-openai` | `0.1.20` | Azure OpenAI integration |
| `langchain-community` | `0.2.11` | Community integrations |
| `openai` | `1.34.0` | OpenAI SDK |
| `python-dotenv` | `1.0.1` | `.env` loader |
| `pyyaml` | `6.0.1` | YAML parsing |
| `Jinja2` | `3.1.4` | Templating |
| `python-multipart` | `0.0.9` | Multipart form |
| `aiohttp` | `3.10.1` | Async HTTP |
| `motor` | `3.5.1` | Async MongoDB |
| `pymongo` | `4.8.0` | Mongo driver (used by Motor) |
| `qdrant-client` | `1.9.1` | Vector DB client |
| `fastembed` | `0.2.7` (Python 3.10 only) | Sparse embeddings |
| `sentence-transformers` | `3.0.1` | Dense embeddings |
| `unstructured` | `0.11.8` | Generic doc parsing |
| `pypdf` | `4.3.1` | PDF text extraction |
| `PyPDF2` | `3.0.1` | Alternate PDF lib (overlap) |
| `pdfminer-six` | `20231228` | PDF text extraction |
| `pdfplumber` | `0.11.2` | PDF tables |
| `python-docx` | `1.1.2` | DOCX parsing |
| `python-pptx` | `0.6.23` | PPTX parsing |
| `pandas` | `2.2.2` | Tabular data, Excel logs |
| `openpyxl` | `3.1.5` | Excel write |
| `opencv-python` | `4.10.0.84` | Video frame processing |
| `scikit-image` | `0.23.2` | Image processing |
| `torch` | `2.3.1` | Required by transformers / LiLT |
| `llama-cpp-python` | `0.2.83` | Local Phi-3 inference |
| `openai-whisper` | from `git@HEAD` (unpinned) | Audio/video transcription |
| `markdown` | `3.6` | Markdown utilities |
| `datasets` | `2.18.0` | HuggingFace datasets |
| `GitPython` | `3.1.43` | Git automation |
| `getmac` | `0.9.5` | MAC address retrieval (license) |
| `loguru` | `0.7.2` | Logging |
| `sentencepiece` | `0.2.0` | Phi-3 tokenizer |
| `comtypes` | `1.4.6` | Windows COM (DOC→DOCX conversion) |

Transitive (used in code, not listed directly): `transformers` (for LiLT), `cryptography` (Fernet via `cryptography.fernet.Fernet`).

### 3.3 Notable pinning behavior

- `fastembed` is conditionally installed **only for Python 3.10** ([pyproject.toml:36-38](../pyproject.toml#L36-L38)). Hybrid search depends on it.
- `openai-whisper` is sourced from `git@HEAD` with no commit SHA — non-reproducible build.
- `pypdf` (4.3.1) **and** `PyPDF2` (3.0.1) coexist; same-purpose libraries.
- `requirements.txt` is one line: `poetry==1.7.1` — used only to bootstrap Poetry itself.
- `.gitignore` lines 163-164 ignore `pyproject.toml` and `poetry.lock` themselves — unusual, but they are committed regardless.

---

## 4. Application Entry & Bootstrap

[`src/main.py`](../src/main.py) — 51 lines.

```python
# src/main.py:25-29
@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_utilities.db_setup()
    yield
```

- `load_dotenv()` is called at module import ([main.py:22](../src/main.py#L22)).
- App constructed at [main.py:32](../src/main.py#L32).
- Three routers attached at [main.py:34-36](../src/main.py#L34-L36):
  - `DBRouter` → `/database`
  - `ChatApiRouter` → `/chat`
  - `CachedQuestionRouter` → `/cached-question`
- CORS configured at [main.py:37-43](../src/main.py#L37-L43):
  ```python
  allow_origins=["http://localhost:3000", "*"],
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
  ```
  *(Per CORS spec, wildcard origins with credentials are invalid. The browser will refuse the response. Documented as Finding 6.1.)*
- Runs on `0.0.0.0:8080` with `reload=False`, `access_log=True` ([main.py:46](../src/main.py#L46)).
- Trailing comments at [main.py:49-51](../src/main.py#L49-L51) read:
  ```
  # 1. Liscen corruption
  # 2. Date Expiry
  # Mac maddress mismatch
  ```

### Startup container

[`src/utilities/StartupUtilities.py`](../src/utilities/StartupUtilities.py) implements a **thread-safe singleton** (`StartUp`) that, on first construction, builds and caches:

1. Vector DB client (Qdrant, hybrid mode if configured)
2. MongoDB client (Motor)
3. Word/PPT/Media parsers (loading LiLT and Whisper models synchronously at startup)
4. LLM client — Azure OpenAI **or** Phi-3 based on `os.getenv('llm_model')`

Routes receive these via `Depends(startup_utilities.get_…)` accessors. **No abstraction**: routes depend on concrete classes (`VectorDb`, `MongoAppDbService`, `LLMChains`).

---

## 5. API Surface — Every Endpoint

### 5.1 `/chat` — Chat Operations (`routes/ChatInterface.py`)

| Method | Path | Handler | Input | Output | What it does |
| --- | --- | --- | --- | --- | --- |
| `POST` | `/chat/getqueryresponse` | `chat_with_bot` | `UserQuestion { question: str }` | `JSONResponse` | Validates license, branches on `os.getenv('llm_model')` (`gpt3` → online Azure flow, `phi3` → local Phi-3 flow), returns answer + sources. |

Source: [ChatInterface.py:24-46](../src/routes/ChatInterface.py#L24-L46).

### 5.2 `/database` — Data Handling (`routes/DataHandling.py`)

| Method | Path | Handler | Input | Output | What it does |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/database/add-file-from-source-db` | `create_db` | — | `JSONResponse` | Full rebuild: clears all collections, walks every local folder + GitHub wiki configured in `data_sources`, parses, chunks, embeds, upserts. |
| `GET` | `/database/update-github-wiki-file-db` | `update_db` | — | `JSONResponse` | Incremental update: `git pull` each wiki, diff changed files, re-embed only those. |
| `POST` | `/database/get_all_db_content` | `fetch_db_content` | `DBFetch { results_returned: int }` | `JSONResponse` | Fetch up to N documents. |
| `POST` | `/database/fetch_data_by_filename` | `fetch_data_by_filename` | `FileFetch { file_name: str, results_returned: int }` | `JSONResponse` | Filter by filename. |
| `GET` | `/database/get_all_conversation_data` | `fetch_conversation_content` | — | `JSONResponse` | All conversation summaries (keyed by user IP). |
| `POST` | `/database/delete_conversation_data_by_ip` | `delete_conversation_content` | `DeleteChat { user_ip: str }` | `JSONResponse` | Drop one user's history. |
| `GET` | `/database/delete_all_conversation_data` | `delete_all_conversation_content` | `DeleteChat` | `JSONResponse` | Drop all history. Mixed semantics: `GET` with a body. |

Source: [DataHandling.py](../src/routes/DataHandling.py).

### 5.3 `/cached-question` — Cached Q&A (`routes/CachedQuestion.py`)

| Method | Path | Handler | Input | Output | What it does |
| --- | --- | --- | --- | --- | --- |
| `GET` | `/cached-question/get_all_cached_question` | `fetch_cached_question` | — | `JSONResponse` | List every cached Q&A. |
| `GET` | `/cached-question/delete_all_cached_question` | `delete_all_cache_questions` | — | `JSONResponse` | Wipe vector cache + Mongo cache. |
| `POST` | `/cached-question/delete_single_cached_question` | `delete_cache_questions` | `DeleteCacheQuestion { question_id: str }` | `JSONResponse` | Delete one cached entry from both stores. |

Source: [CachedQuestion.py](../src/routes/CachedQuestion.py).

**License gating:** Every handler calls `validate_license(os.getenv("km_bot_license_key"))` inline and returns HTTP 403 with `{ "message": <reason> }` if invalid. No middleware abstraction.

---

## 6. Domain Flows

### 6.1 Chat — `POST /chat/getqueryresponse`

1. **Pull request** — `user_query.question` extracted ([ChatInterface.py:32](../src/routes/ChatInterface.py#L32)).
2. **License check** — `validate_license(os.getenv("km_bot_license_key"))` ([ChatInterface.py:33](../src/routes/ChatInterface.py#L33)). On failure, return HTTP 403.
3. **Branch on `llm_model`** env var ([ChatInterface.py:39, 44](../src/routes/ChatInterface.py#L39)):
   - `gpt3` → `LLMChains.question_answer_with_online_llms(...)` — the 364-line orchestrator in [llm_chains.py:66](../src/llm_service_layer/llm_chains.py#L66).
   - `phi3` → `LLMChains.question_answer_with_phi(...)` ([llm_chains.py:24](../src/llm_service_layer/llm_chains.py#L24)).
4. **Online flow inside `question_answer_with_online_llms`** ([llm_chains.py:66-end](../src/llm_service_layer/llm_chains.py#L66)):
   1. Look up similar cached questions in Qdrant (`cached_question_answer`, threshold ~0.99).
   2. If cache hit, run `check_cache_answer_is_right_or_not` chain to confirm relevance; if confirmed, return cached answer + sources.
   3. On cache miss / rejected cache:
      a. Fetch last 3 conversation turns for this `user_host_ip` from `user_conversation_summary`.
      b. Run `custom_llm_release_chain` to extract any version mentioned in the question.
      c. Run `question_rewrite_chain` to disambiguate follow-ups using history.
      d. Run hybrid semantic search against `documents_data` (threshold 0.8, tolerance 0.3, top-5), optionally filtered by detected version.
      e. Concatenate retrieved chunks into a context block; truncate if over `max_total_tokens` (8000).
      f. Run `question_answer_custom_chain` to generate the point-wise answer.
      g. Run `check_bot_answer_the_question_or_not` chain to decide whether to cache.
      h. If cache-worthy, persist `{question, answer, sources}` to Mongo (`cached_question_answer`) and embed the question into Qdrant `cached_question_answer`.
      i. Run `user_bot_conversation_summary` chain and upsert the rolling summary for this IP.
   4. Return `QuestionAnswer { user_query, bot_answer: List[BotAnswer], summary_sources: List[BotSource], other_sources: Optional }`.
5. **Phi-3 flow** ([llm_chains.py:24-64](../src/llm_service_layer/llm_chains.py#L24-L64)) is much simpler — retrieval → single prompt → return. No caching path, no history.

### 6.2 Full ingestion — `GET /database/add-file-from-source-db`

1. License check.
2. Clear all three Qdrant collections + Mongo cache collection.
3. For each `local_folder` in `data_sources`: recursively walk; for each file call `VectorDb.add_data_to_vectordb`.
4. For each `github_wiki`: `Github.clone_repository` or `pull_repository`; walk; ingest.
5. Inside `add_data_to_vectordb` ([VectorDbServices.py:29-98](../src/db_service_layer/VectorDbServices.py#L29-L98)):
   - Look up file extension in `CONSTANTS.file_extension_map`.
   - Route to the matching parser (markdown / document / presentation / video / audio).
   - Parser returns segment dicts with `segment_id`, `segment_content`, `segment_metadata`.
   - Hand chunks to `QdrantDbClient.add_to_vector_db(collection='documents_data', ...)`.

### 6.3 Incremental update — `GET /database/update-github-wiki-file-db`

1. License check.
2. For each GitHub source: `Github.pull_repository()` returns the list of files whose hash changed between pre-pull and post-pull HEAD.
3. For each changed file: delete its existing chunks (filter by `file_path`), re-parse, re-embed, re-upsert.

### 6.4 Cached question CRUD — `/cached-question/*`

Direct passthrough to `MongoAppDbService` + `VectorDb` deletions, paired so the two stores stay consistent. No transactionality across the two stores; partial-failure window is not handled.

---

## 7. RAG & LLM Layer

### 7.1 Chunking

- `RecursiveCharacterTextSplitter`, `chunk_size=6000`, `chunk_overlap=500` ([DocumentChunker.py:6-15](../src/utilities/DocumentChunker.py)).
- Chunks are large because the goal is to preserve full sections of long-form docs.

### 7.2 Embeddings

| Type | Model | Dim | Notes |
| --- | --- | --- | --- |
| Dense | `sentence-transformers/all-MiniLM-L6-v2` | 384 | Loaded locally |
| Sparse | `prithvida/Splade_PP_en_v1` | n/a | Loaded via FastEmbed; enabled by `hybrid_search: true` in `sample_config.json:14` |
| Similarity | cosine | — | `sample_config.json:10` |

Models live under `{km_azure_home}/Model/` and `local_downloaded_model_only: true` blocks fetching new model weights.

### 7.3 Qdrant collections

| Collection (`CONSTANTS.py:2-4`) | Purpose | Key payload fields |
| --- | --- | --- |
| `documents_data` | Source document chunks | `file_name`, `file_path`, `release_version`, `release_file`, `original_document` / `document`, plus parser-specific fields (`Header 1`, `page_no`, `segment_type`, `start_time`, etc.) |
| `user_conversation_summary` | Per-user (IP) conversation rolling summary | `user_ip`, `conversation_history` (semicolon-joined recent turns), `history_update` timestamp |
| `cached_question_answer` | Vector index of previously answered questions | `question_app_db_id` (FK to Mongo `_id`) |

### 7.4 LangChain chains in `AzureOpenAi.py`

All chains live in [`src/llm_clients/AzureOpenAi.py`](../src/llm_clients/AzureOpenAi.py) and use `AzureChatOpenAI` from `langchain-openai`.

| Chain | Lines | Purpose |
| --- | --- | --- |
| `question_answer_custom_chain` | 25-97 | Primary answer generation. Reduces context when over `max_total_tokens=8000`. |
| `user_bot_conversation_summary` | 99-134 | Progressively summarizes chat history. |
| `custom_llm_release_chain` | 136-180 | Extracts software version from question. Returns `[bool, version]`. |
| `question_rewrite_chain` | 182-238 | Rewrites follow-ups using history. |
| `check_question_related_to_allowed_topics` | 240-257 | Topic gate (disabled by default — empty allowed list). |
| `check_bot_answer_the_question_or_not` | 259-304 | Quality gate to decide cacheability. |
| `check_cache_answer_is_right_or_not` | 306-334 | Confirms a cache hit applies to the new wording. |

Azure model config ([sample_config.json:40-47](../sample_config_env/sample_config.json#L40-L47)):
```json
{
  "deployment_name": "gpt35exploration",
  "model_name": "gpt-35-turbo",
  "temperature": 0.4,
  "token_length_factor": 4.5,
  "max_total_tokens": 8000
}
```

### 7.5 Phi-3 (local) path

- File: [`src/llm_clients/MicrosoftPhi.py`](../src/llm_clients/MicrosoftPhi.py).
- Weights: `{km_azure_home}/Model/llamamodel/Phi-3-mini-4k-instruct-q4.gguf`.
- Loaded synchronously at startup via `Llama(model_path=..., n_ctx=4096, n_threads=8)`.
- Inference uses a single prompt template `"<|user|>\n{prompt}<|end|>\n<|assistant|>"` with `stop=["<|end|>"]`, `max_tokens=2000`, `temperature=0.4`, `echo=False`.
- Phi-3 path does not exercise the full chain set — no cache verification, no question rewriting, no conversation summary writeback.

---

## 8. Persistence Layer

### 8.1 Qdrant (embedded)

- Single `QdrantClient` instance with the local path from `qdrant_db.db_path` (config).
- Embedded mode — no network port — packaged with the app.
- Operations live in [`src/database_layer/vector_data_interface/QdrantClient.py`](../src/database_layer/vector_data_interface/QdrantClient.py) (~632 lines). One class handles collection bootstrap, dense indexing, sparse indexing, hybrid search, fetch-by-id, filter-by-payload, deletion, and reformatting search results.

### 8.2 MongoDB (Motor)

- URI constructed inline at [MongoClient.py:18](../src/database_layer/mongo_data_interface/MongoClient.py#L18):
  ```python
  uri = f"mongodb://{db_username}:{db_password}@{db_host}:{db_port}/{db_name}"
  ```
  Credentials are interpolated directly into the URI string — they flow into Motor's internal state, error messages, and any logging of the client object.
- Single MongoDB collection in use: **`cached_question_answer`**, with shape:
  ```jsonc
  {
    "_id": ObjectId,
    "question_vector_db_id": "<uuid>",      // FK into Qdrant cached_question_answer
    "user_ip":  "<client ip>",
    "question": "<text>",
    "answer":   "<text>",
    "summary_sources": [ { /* BotSource */ } ],
    "show_sources": true
  }
  ```
- Operations: `add_single_document_to_db`, `query_document_by_id`, `get_all_collection_document`, `update_one_document`, `delete_document`, `delete_all_document` — each wrapped in a generic `try/except Exception`.

---

## 9. Document Parsing Pipeline

### 9.1 File-type map

`CONSTANTS.file_extension_map` ([CONSTANTS.py:5-21](../src/CONSTANTS.py#L5-L21)) covers `pdf`, `doc`/`docx`, `ppt`/`pptx`, `md`, video (`mp4`, `ogv`, `webm`, `avi`, `mov`) and audio (`ogg`, `mp3`, `wav`, `m4a`).

### 9.2 Per-format details

**Markdown** — [`parsers/MarkdownParser.py`](../src/parsers/MarkdownParser.py):
- Detects HTML-embedded markdown vs pure markdown; uses BeautifulSoup to flatten HTML.
- Splits by Level-1 headers (`#`).
- Calls `release_file_pattern_check(filename)` for `vX.Y.Z` / `release-X.Y` filename detection — emits `release_version` and `release_file` payload fields.
- Chunks via the shared 6000/500 splitter.

**Word / PDF** — [`parsers/WordParser.py`](../src/parsers/WordParser.py) plus `parsers/word_parser/`:
- Loads transformer tokenizer + model `pierreguillou/lilt-xlm-roberta-base-finetuned-with-DocLayNet-base-at-linelevel-ml384` at parser init (synchronous, ~600 MB).
- Two strategies:
  - **Heading-based** — when the document has detectable headings, uses `WordDocumentTableParser.process_document()`.
  - **Vision-based** — when no headings, uses `VisionDocumentParser` (627 lines) with LiLT for layout-aware extraction.
- PDFs go through `VisionDocumentParser.pdf_processor()` and combine into a single dataframe of segments.

**PowerPoint** — [`parsers/PPTParser.py`](../src/parsers/PPTParser.py):
- One segment per slide, includes slide tables (via `ParseTable.parse_table`) and speaker notes.

**Audio / Video** — [`parsers/media_parsers/MediaTranscribe.py`](../src/parsers/media_parsers/MediaTranscribe.py):
- Whisper `small.en` loaded at startup; cache at `{km_azure_home}/Model/whisper/`.
- Transcribes; chunks into 60-second windows.
- For video, also runs [`VideoTextExtraction`](../src/parsers/media_parsers/VideoTextExtraction.py) for frame OCR (`displayed_text` metadata).

### 9.3 Output normalization

All parsers ultimately yield segments shaped as:
```python
{ "segment_id": "<uuid>",
  "segment_content": "<text>",
  "segment_metadata": { "file_path": ..., "file_name": ..., "segment_type": ..., "segment_number": ..., ... } }
```
…which `VectorDb.add_data_to_vectordb` then flattens into Qdrant's `documents` / `document_ids` / `document_metadata` shape.

---

## 10. Auth, Licensing & Secrets

### 10.1 License model

- **Algorithm:** Fernet symmetric encryption (`cryptography.fernet`).
- **Payload:** `<mac>SPELL<start_date>SPELL<end_date>SPELL<username>` where `SPELL = "separator_string"` ([validate_license.py:23-28](../src/license_checker/validate_license.py)).
- **Validation steps** ([validate_license.py:38-82](../src/license_checker/validate_license.py#L38-L82)):
  1. Fernet decrypt; on failure → "License is corrupted."
  2. Split on `SPELL` into four fields.
  3. Compare decrypted MAC to `get_current_mac_address()`.
  4. Check current date is within `[start_date, end_date]`.
  5. Return `(bool, message)`.

### 10.2 Hardcoded cryptographic material

[`src/CONSTANTS.py:22-23`](../src/CONSTANTS.py#L22-L23):
```python
KEY   = "yGvG97s3OFaqpGNlQEpShsRriEIAeh6a8Q5jYEMk6Iw="   # Fernet key
SPELL = "separator_string"                                # field delimiter
```
**This is the master secret of the license system, checked into git history.** Anyone with read access to the repo can:
- Decrypt any issued license.
- Forge new licenses for any MAC address and date window.

### 10.3 API authentication

- **None beyond the license.** No bearer tokens, no API keys, no signed requests, no mTLS, no IP allowlist, no per-user identity, no roles, no scopes.
- The license key is supplied to the process as an environment variable (`km_bot_license_key`), not as a request header — so every caller able to reach the network port has the same authority.

### 10.4 Secrets in `.env`

[`sample_config_env/sample.env`](../sample_config_env/sample.env) declares 15 environment variables; the operational secrets are:
- `AZURE_OPENAI_API_KEY`
- `kmbot_db_username`, `kmbot_db_password`
- `user_name`, `user_token` (GitHub PAT)
- `km_bot_license_key`

The `.env` is loaded by `python-dotenv` at process start. There is no integration with Key Vault, Vault, AWS Secrets Manager, or Kubernetes Secrets.

### 10.5 GitHub token embedded in URL

[`GithubAutomater.py:19`](../src/github_automation/GithubAutomater.py#L19) builds the clone URL as:
```python
self.repository_url = f"https://{self.github_username}:{self.github_user_token}@github.com/.../{self.repo_name}.git"
```
The token becomes part of git's stored remote URL on disk and may surface in error messages.

---

## 11. Observability

- **Logging library:** Loguru `0.7.2` ([`src/utilities/AppLogger.py`](../src/utilities/AppLogger.py), 106 lines). Single global instance (`global_logger`).
- **Sinks:** colored console (TRACE) plus file at `{km_azure_home}/Logs/kmbot.log.out`, rotated at 100 KB.
- **Format:** plain text — `{time} - Logger Module : {name} - Level : {level} - Module : {module} - Function : {function} - Line Number : {line} - MSG : {message}`. Not structured / not JSON.
- **Correlation IDs:** none. **Trace IDs:** none. **Request IDs:** none.
- **Metrics:** none. No Prometheus, no StatsD, no Application Insights, no OpenTelemetry.
- **Health probes:** no `/healthz`, no `/livez`, no `/readyz` endpoints.
- **LLM telemetry:** [`PromptLogger`](../src/utilities/PromptLogger.py) writes each chain invocation (prompt + response) into a per-chain Excel file under `{km_azure_home}/LLM Logs/`. Used for offline review, not aggregation.

---

## 12. Testing

The `test/` directory looks like a test suite but isn't.

| File | Lines | What it actually is |
| --- | --- | --- |
| `test/__init__.py` | 0 | Package marker. |
| `test/TestDocumentParsing.py` | 31 | A class with one method `parse_doc()`. Usage code at the bottom is commented out. No assertions. |
| `test/TestFiles.py` | 448 | A large `VectorDb`-style class for manually exercising file ingestion + retrieval. Uses `print()` for output. No assertions. |
| `test/TestQuestions.py` | 60 | A loop that posts hardcoded questions to a running server and writes the responses to a file. No assertions. |

There is **no `pytest` runner, no fixtures, no mocks, no coverage tool, no CI integration**. Coverage is effectively zero by any automated measure.

---

## 13. Deployment & CI/CD

- **No Dockerfile.**
- **No `docker-compose.yml`.**
- **No `helm/`, no Kubernetes manifests.**
- **No `.github/workflows/`, no `azure-pipelines.yml`, no `Jenkinsfile`.**
- **No deployment scripts (`.sh`, `.ps1`).**
- **No health endpoints.**
- **No graceful-shutdown logic** beyond Uvicorn's default.

Production starts with `python -m src.main` (or equivalent), which lands on [main.py:46](../src/main.py#L46):
```python
uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False, access_log=True)
```

The deployment target is not specified anywhere in-repo. Based on the project name ("azure-openai") it was almost certainly intended for Azure (App Service or VM), but the artifacts to deploy it are absent.

---

## 14. Configuration Surface

### 14.1 Environment variables

| Var | Required? | Purpose |
| --- | --- | --- |
| `km_azure_home` | Yes | Base directory containing `Config/`, `Model/`, `Logs/`. |
| `km_bot_license_key` | Yes | Fernet-encrypted license. |
| `user_name` | Yes (if GitHub sources used) | GitHub username. |
| `user_token` | Yes (if GitHub sources used) | GitHub PAT. |
| `llm_model` | Yes | `"gpt3"` or `"phi3"`. |
| `OPENAI_API_TYPE` | Yes (gpt3) | Always `azure`. |
| `OPENAI_API_VERSION` | Yes (gpt3) | e.g. `2024-02-15-preview`. |
| `AZURE_OPENAI_ENDPOINT` | Yes (gpt3) | Azure resource endpoint URL. |
| `AZURE_OPENAI_API_KEY` | Yes (gpt3) | Azure OpenAI key. |
| `app_db_type` | Yes | `"mongo_db"`. |
| `kmbot_db_username` | Yes | Mongo user. |
| `kmbot_db_password` | Yes | Mongo password. |
| `kmbot_db_host` | Yes | Mongo host. |
| `kmbot_db_port` | Yes | Mongo port. |
| `kmbot_db_name` | Yes | Mongo database name. |

There is **no validation** that required vars are set. Missing variables surface as runtime `KeyError` or `None` further down the call graph.

### 14.2 `sample_config.json` (108 lines)

Sections:
- `databases` — selectors (`qdrant_db`, `mongo_db`).
- `qdrant_db` — `db_path`, `embedding_model`, `similarity_metrics`, `dense_model`, `sparse_model`, `hybrid_search`, `local_downloaded_model_only`.
- `semantic_search.question_answers` — `threshold: 0.8`, `tolerance: 0.3`, `no_of_results: 5`.
- `llm_config.phi_3` — `n_ctx: 4096`, `n_threads: 8`, `max_tokens: 2000`, `temperature: 0.4`, `echo: false`.
- `llm_config.gpt_3` — `deployment_name`, `model_name`, `temperature: 0.4`, `token_length_factor: 4.5`, `max_total_tokens: 8000`.
- `allowed_topics` — `[]` (off).
- `data_sources` — list of local folders or GitHub wikis to ingest.
- `llm_prompt_logger` — chain → Excel filename map.
- `logger` — colored output, file path, rotation 100 KB.

---

## 15. Recent History (last 8 commits)

| SHA | Subject |
| --- | --- |
| `00513a9` | Merge PR #18 — license-generator-integration |
| `893271e` | Final Changes for IP ready |
| `41516e3` | Merge PR #17 — license-generator-integration |
| `3329006` | Poetry version fixes |
| `fc5247e` | Phi3 config changes |
| `04219ec` | Testing completed |
| `7fd7f2b` | License validation check added |
| `4ebc2ef` | License generator zip added |

No activity since IP-ready signoff.

---

## 16. Findings Catalogue

> Severity legend: **C** = Critical (data/security/legal risk), **H** = High (will fail in prod), **M** = Medium (quality/operability), **L** = Low (cosmetic).

### Security

| # | Sev | Finding | Citation |
| --- | --- | --- | --- |
| S1 | **C** | Fernet license-system master key hardcoded in source — anyone with repo read can forge licenses. | [CONSTANTS.py:22](../src/CONSTANTS.py#L22) |
| S2 | **C** | No API authentication. License key is a process-wide env var; every reachable caller has full authority. | [ChatInterface.py:33](../src/routes/ChatInterface.py#L33) and all routes |
| S3 | **H** | CORS configured with `allow_origins=["http://localhost:3000", "*"]` together with `allow_credentials=True` — invalid CORS combination, browsers will refuse. | [main.py:37-43](../src/main.py#L37-L43) |
| S4 | **H** | MongoDB credentials interpolated into the URI string; flow into client state, exceptions, and any logging of the client. | [MongoClient.py:18](../src/database_layer/mongo_data_interface/MongoClient.py#L18) |
| S5 | **H** | GitHub PAT embedded in clone URL; persists in git remote on disk. | [GithubAutomater.py:19](../src/github_automation/GithubAutomater.py#L19) |
| S6 | **M** | No rate limiting, no body-size limits, no input validation on `user_query.question`. | [ChatInterface.py:32](../src/routes/ChatInterface.py#L32) |
| S7 | **M** | `openai-whisper` pinned to `git@HEAD` — non-reproducible, supply-chain risk. | [pyproject.toml:48](../pyproject.toml#L48) |
| S8 | **M** | No HTTPS / TLS termination configured at the app layer. | [main.py:46](../src/main.py#L46) |
| S9 | **M** | License key transmitted as plain env var (not header); no rotation mechanism. | [ChatInterface.py:33](../src/routes/ChatInterface.py#L33) |

### Reliability & error handling

| # | Sev | Finding | Citation |
| --- | --- | --- | --- |
| R1 | **H** | Bare `except Exception` everywhere — 68 try blocks across the codebase, almost none distinguish failure modes. | [MongoClient.py:24-65](../src/database_layer/mongo_data_interface/MongoClient.py), [QdrantClient.py:84-92, 114-115](../src/database_layer/vector_data_interface/QdrantClient.py) and many others |
| R2 | **H** | Several "errors" are swallowed: caught, logged, and the function returns `None` — callers must defensively check. | [QdrantClient.py:84-86](../src/database_layer/vector_data_interface/QdrantClient.py) |
| R3 | **H** | No FastAPI `exception_handler` registered; responses on failure are inconsistent. | [main.py](../src/main.py) (absence) |
| R4 | **M** | Cross-store consistency between Qdrant and Mongo is not transactional; partial failures can desynchronize the cache. | [CachedQuestion.py](../src/routes/CachedQuestion.py) |
| R5 | **M** | Required env vars are not validated at startup; failures surface deep in call graph. | [StartupUtilities.py](../src/utilities/StartupUtilities.py) |

### Code quality

| # | Sev | Finding | Citation |
| --- | --- | --- | --- |
| Q1 | **H** | `LLMChains.question_answer_with_online_llms` is ~364 lines and mixes cache lookup, history, rewriting, retrieval, generation, caching, summary writeback — SRP violation. | [llm_chains.py:66+](../src/llm_service_layer/llm_chains.py#L66) |
| Q2 | **M** | `QdrantClient.py` and `VisionDocumentParser.py` exceed 600 lines — god-class smell. | [QdrantClient.py](../src/database_layer/vector_data_interface/QdrantClient.py), [VisionDocumentParser.py](../src/parsers/word_parser/VisionDocumentParser.py) |
| Q3 | **M** | Of ~201 function defs, only ~15 carry return-type annotations. mypy would refuse most of the codebase. | repo-wide |
| Q4 | **M** | No linter or formatter configured (no `ruff`, `black`, `isort`, `mypy` config in `pyproject.toml`). | [pyproject.toml](../pyproject.toml) |
| Q5 | **M** | Two PDF libraries pinned (`pypdf` + `PyPDF2`); doc parsers also pull `pdfminer-six` and `pdfplumber` — redundant. | [pyproject.toml:26,31-33](../pyproject.toml) |
| Q6 | **M** | Routes depend on concrete classes (`VectorDb`, `MongoAppDbService`, `LLMChains`) via a singleton — DIP violation, untestable without infra. | [ChatInterface.py:25-29](../src/routes/ChatInterface.py#L25-L29) |
| Q7 | **L** | Magic strings/numbers: `<break>` delimiter, hardcoded "last 3 turns", `token_length_factor: 4.5`. | [llm_chains.py](../src/llm_service_layer/llm_chains.py), [sample_config.json:45](../sample_config_env/sample_config.json#L45) |
| Q8 | **L** | Inconsistent naming (`user_host_ip` vs `user_ip`, `result_Type` vs `result_type`, `file_name` vs `fileName`). | repo-wide |
| Q9 | **L** | Commented-out code blocks left in source (e.g., `TestDocumentParsing.py:29-31`, `TestFiles.py:106-135`). | as cited |
| Q10 | **L** | Typos in code comments (`Liscen`, `maddress`). | [main.py:49-51](../src/main.py#L49-L51) |

### Testing

| # | Sev | Finding | Citation |
| --- | --- | --- | --- |
| T1 | **C** | Zero automated tests. The `test/` directory contains manual scripts only. | [test/](../test) |
| T2 | **H** | No CI / no enforcement gate on lint, type, or test. | repo-wide |

### Observability & operability

| # | Sev | Finding | Citation |
| --- | --- | --- | --- |
| O1 | **H** | No `/healthz`, `/readyz`, or `/livez` endpoint — no way for an orchestrator to know if the app is live. | [main.py](../src/main.py) (absence) |
| O2 | **H** | No structured logs; logs are free-form text. | [AppLogger.py](../src/utilities/AppLogger.py) |
| O3 | **H** | No metrics emission, no distributed tracing. | repo-wide |
| O4 | **M** | LLM telemetry written to per-chain Excel files — not aggregatable, not queryable, grows unbounded on disk. | [PromptLogger.py](../src/utilities/PromptLogger.py) |

### Performance

| # | Sev | Finding | Citation |
| --- | --- | --- | --- |
| P1 | **H** | Whisper and LiLT models loaded synchronously at startup; if model download fails or paths are wrong, the entire app fails to start. | [StartupUtilities.py](../src/utilities/StartupUtilities.py), [WordParser.py:25-26](../src/parsers/WordParser.py) |
| P2 | **M** | Large-string accumulation by `+=` inside loops in `llm_chains.py:220-228` — quadratic-ish concatenation for big contexts. | [llm_chains.py:220-228](../src/llm_service_layer/llm_chains.py) |
| P3 | **M** | No connection pooling configuration for Mongo or Qdrant. | as cited |
| P4 | **M** | Single-process Uvicorn run (`uvicorn.run`), no Gunicorn workers. | [main.py:46](../src/main.py#L46) |

### Deployment

| # | Sev | Finding | Citation |
| --- | --- | --- | --- |
| D1 | **C** | No deployment artifacts at all (Docker, Helm, CI, scripts). | repo-wide |
| D2 | **H** | Qdrant is embedded — single-host only, no horizontal scaling, no operational tooling. | [QdrantClient.py](../src/database_layer/vector_data_interface/QdrantClient.py) |

### Documentation

| # | Sev | Finding | Citation |
| --- | --- | --- | --- |
| W1 | **M** | README is install-only (~34 lines); no architecture, deployment, configuration, or operations docs. | [README.md](../README.md) |
| W2 | **L** | Endpoint handlers carry no docstrings; OpenAPI summaries are minimal. | [ChatInterface.py:24](../src/routes/ChatInterface.py#L24) and others |

---

End of audit.
