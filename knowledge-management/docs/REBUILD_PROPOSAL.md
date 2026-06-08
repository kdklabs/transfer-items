# Your Rebuild Roadmap — Building the KM Bot, By Hand, From Scratch

> **Who this is for:** *You*. A solo developer who knows Python basics and has done hello-world FastAPI, but who has never properly worked with async, databases, LLMs, embeddings, or vector stores. You want to type every line of code yourself and understand why each one is there.
>
> **Companion doc:** [`CURRENT_STATE.md`](CURRENT_STATE.md) — the audit of the *old* codebase. Use it as a reference for *what* the v1 bot did. We are not following its design.
>
> **Tone of this document:** A mentor sitting next to you with a coffee, not an architect handing you a spec. If anything in here feels too much or too little, push back.

---

## 0. What we're explicitly dropping for now

You said you don't want these yet — and you're right. They're distractions while you're learning the core. We'll come back to each one *after* you have a working bot you understand.

| Dropped (for now) | Why we're skipping it |
| --- | --- |
| Automated tests (pytest, etc.) | You'll test by hand — sending requests, reading responses, watching logs. We add automated tests once the code shape stabilises. |
| CI/CD pipelines | You're the only committer. Run things on your machine. CI matters when a team needs guard-rails. |
| Docker / Kubernetes / Helm | Same reason — solo + local + learning. Eventually we'll containerise; not today. |
| Deployment (Azure App Service, etc.) | You'll run on `localhost`. Deployment is its own world; we visit it later. |
| Authentication / Entra ID / JWTs | Anyone can hit your `localhost:8080`. That's fine. Auth is a Phase 99 problem. |
| License validation | Gone. We don't bring this back. |
| Multi-tenancy, rate limiting, secrets vaults | All later. |

What we **are** keeping:

- A real, working KM bot that ingests documents, embeds them, and answers questions via RAG.
- A clean folder layout that *will* scale when you add the dropped stuff later.
- Habits (config separated from code, layers separated from each other, types on everything) that make the project feel professional without the ceremony.

---

## 1. The big picture, in plain English

You're building a service that does this:

1. **Ingests documents.** You point it at a folder full of PDFs, Word docs, markdown files, audio, whatever. It reads each file, breaks it into chunks of text, and saves those chunks in a database that's good at "find me the chunk that's most similar to this question."
2. **Answers questions.** Someone POSTs a question. Your service finds the most relevant chunks from step 1, hands those chunks plus the question to an LLM (a language model — initially Azure OpenAI's GPT, later optionally a local model running on your machine), and returns the LLM's answer plus the source chunks it used.
3. **Remembers.** Useful answers get cached so the next person who asks something similar gets a fast response without paying for another LLM call.

That whole pattern — *retrieve relevant context, augment the prompt, generate an answer* — is called **RAG**: Retrieval-Augmented Generation. It's the entire reason this project exists.

Everything else in the codebase exists to support those three jobs.

---

## 2. The mental model: how a request flows

Imagine someone sends a question to your bot. Here's the journey it takes:

```
HTTP request lands
       │
       ▼
┌────────────────────────────────────────┐
│ FastAPI route handler                  │  ← thin, no logic; just maps HTTP to a function call
│   (e.g. POST /chat/ask)                │
└──────────────┬─────────────────────────┘
               │ calls
               ▼
┌────────────────────────────────────────┐
│ Use case / service function            │  ← the actual workflow: retrieve, prompt, answer
│   (e.g. answer_user_question())        │
└──────────────┬─────────────────────────┘
               │ calls
       ┌───────┼───────┬─────────────────┐
       ▼       ▼       ▼                 ▼
   ┌──────┐ ┌──────┐ ┌──────────┐ ┌──────────────┐
   │Vector│ │ DB   │ │   LLM    │ │  Embedding   │
   │store │ │      │ │ provider │ │   model      │
   │(Qdrant)│ │(Postgres)│ │(Azure)│ │(sentence-trf)│
   └──────┘ └──────┘ └──────────┘ └──────────────┘
```

The big idea: **the route is dumb, the use case has the workflow, the use case talks to lower-level pieces (storage, LLM, embeddings) through small helper modules**.

Why this matters:
- When you eventually want to swap Azure OpenAI for a local model, you change *one file* (the LLM helper), and the use case doesn't notice.
- When you want to test the workflow without actually calling the LLM, you swap in a fake LLM helper. (We're skipping tests for now, but this layout makes them painless later.)
- When the workflow gets complicated, the complexity stays in one place — the use case — instead of being smeared across route handlers.

You don't need to memorise design-pattern names. This is just **"keep each kind of code in its own file."**

---

## 3. The folder layout — where everything lives

Don't be intimidated by this. **You don't create all these folders on day one.** You create the first folder in Phase 1, the second in Phase 2, and so on. By Phase 10 the structure has grown into this shape organically. I'm showing you the destination so you know we're heading somewhere coherent.

```
km-bot/
├── pyproject.toml                ← project metadata + dependencies
├── .env                          ← your secrets (NEVER commit this)
├── .env.example                  ← template, safe to commit
├── .gitignore
├── README.md                     ← your own notes; grow as you go
├── docs/                         ← this file lives here, plus future notes
│   └── REBUILD_PROPOSAL.md
└── src/
    └── km_bot/
        ├── __init__.py
        ├── main.py               ← the entry point — your app starts here
        ├── config.py             ← reads .env into a typed Settings object
        ├── logging_setup.py      ← one place to configure logging
        │
        ├── api/                  ← HTTP routes (the "Presentation" layer)
        │   ├── __init__.py
        │   ├── chat.py           ← /chat/ask endpoint
        │   ├── knowledge.py      ← /knowledge/ingest endpoint
        │   └── schemas.py        ← Pydantic request/response models
        │
        ├── services/             ← the workflows (the "Application" layer)
        │   ├── __init__.py
        │   ├── answer_question.py
        │   ├── ingest_document.py
        │   └── cache.py
        │
        ├── llm/                  ← anything related to calling an LLM
        │   ├── __init__.py
        │   ├── azure_openai.py
        │   └── ollama.py         ← added in Phase 16
        │
        ├── embeddings/           ← turning text into vectors
        │   ├── __init__.py
        │   └── local.py
        │
        ├── vector_store/         ← Qdrant glue
        │   ├── __init__.py
        │   └── qdrant.py
        │
        ├── database/             ← Postgres glue
        │   ├── __init__.py
        │   ├── models.py         ← SQLAlchemy table definitions
        │   ├── session.py        ← how we connect to the DB
        │   └── repositories.py   ← functions that read/write rows
        │
        └── parsers/              ← turn files into text chunks
            ├── __init__.py
            ├── base.py           ← shared chunk shape + helpers
            ├── markdown.py
            ├── pdf.py
            ├── docx.py
            ├── pptx.py
            └── media.py
```

### What goes in each folder — in one sentence

- **`api/`** — code that only knows about HTTP. A handler reads a request, calls a service, returns a response. Nothing else.
- **`services/`** — the actual workflows. "To answer a question, first do A, then B, then C." Talks to `llm/`, `embeddings/`, `vector_store/`, `database/` — never directly to HTTP or files.
- **`llm/`** — every line of code that talks to an LLM lives here. The rest of your app calls `llm.complete(prompt)` and doesn't care whether that's Azure or local.
- **`embeddings/`** — turns strings into lists of floats. One job.
- **`vector_store/`** — Qdrant code. Add a chunk, search for similar chunks, delete a chunk. That's it.
- **`database/`** — Postgres code. Table definitions plus the functions that read/write them.
- **`parsers/`** — given a file path, produce a stream of `Chunk` objects. One parser per file type.
- **`config.py`** — reads environment variables into a typed object so nothing else in the code uses `os.getenv` directly.

The discipline you're going to practise: **a file in `api/` never imports from `vector_store/` or `llm/` directly.** It calls a function in `services/`, and *that* function pulls in the lower-level bits. This is what people mean when they say "layered" or "clean" architecture. You don't need the jargon to do it.

---

## 4. Where your application starts

When you run `python -m km_bot.main` (or `uvicorn km_bot.main:app`), here's what happens:

1. **`src/km_bot/main.py`** is imported.
2. It loads your `.env` file (via `config.py`) into a `Settings` object.
3. It sets up logging (via `logging_setup.py`).
4. It creates the FastAPI `app` instance.
5. It registers your route modules (`from km_bot.api import chat, knowledge`) onto the app.
6. It optionally runs a "lifespan" hook that opens connections to Postgres and Qdrant at startup and closes them at shutdown.
7. Uvicorn starts listening on a port (8000 by default).

So `main.py` is small — maybe 30 lines. It's a wiring file. **All the interesting code lives in the layers below it.**

In Phase 1 your `main.py` will only do steps 4 and 7. You'll grow it phase by phase.

---

## 5. A few concepts you'll meet — a mini glossary

You don't need to master these before you start. Skim them; you'll absorb them as you build.

- **Async / `async def` / `await`** — Python's way of letting one process do many slow things (network calls, DB queries) at once without spawning threads. FastAPI is async-first. You'll learn it in Phase 3, the first time you make a network call.
- **Pydantic model** — a Python class with typed fields that validates data automatically. FastAPI uses it for request/response bodies and config.
- **Endpoint / route / handler** — three words for the same thing: a Python function that's wired to a URL path + HTTP method.
- **Dependency injection** — fancy phrase for "instead of a function creating its own helpers, you hand them to it." Makes things easier to swap and test. FastAPI has a `Depends()` helper for this.
- **Embedding** — a list of (usually 384 or 768 or 1536) floating-point numbers that represents the *meaning* of a piece of text. Texts with similar meaning have similar embeddings.
- **Vector store / vector database** — a database optimised for "find the N items whose embeddings are closest to this one." Qdrant is one. There are others.
- **Hybrid search** — combining classical keyword search (BM25 / sparse vectors) with vector search (dense vectors) to get the best of both. We'll use it.
- **RAG (Retrieval-Augmented Generation)** — the pattern: retrieve relevant chunks → put them in the prompt → ask the LLM to answer using only those chunks.
- **Chunking** — splitting a document into pieces small enough to embed and fit into an LLM's context window.
- **Migration** — a Python script that changes your DB schema (creates a table, adds a column). Tools like Alembic generate these for you.
- **ORM** — Object-Relational Mapper. Lets you talk to a SQL database using Python classes instead of raw SQL strings. SQLAlchemy is the dominant one in Python.

---

## 6. The phases — your learning ladder

Each phase is a self-contained step. The pattern for every phase:

> **What you'll learn** → **What to build** → **How to know it works** → **What to read or watch**

Take as long as you need. Some phases are an afternoon, some are a week. **Don't move on until the current phase works on your machine and you can explain it out loud to a rubber duck.**

### Phase 1 — A FastAPI skeleton that says hello

**What you'll learn:** Project scaffolding with `uv`, the bare minimum FastAPI app, running it with Uvicorn.

**What to build:**
- Install Python 3.12.
- Install `uv` (the modern, fast replacement for pip/poetry: `pip install uv` or via the installer).
- `uv init km-bot` to create a project.
- Add FastAPI and Uvicorn: `uv add fastapi uvicorn[standard]`.
- Create `src/km_bot/main.py` with one route: `GET /healthz` returning `{"status": "ok"}`.
- Run it: `uv run uvicorn km_bot.main:app --reload`.
- Visit `http://localhost:8000/healthz` in your browser.

**How to know it works:** The browser shows `{"status":"ok"}`. The auto-generated docs at `/docs` show your endpoint.

**Read:** [FastAPI's "First Steps" tutorial](https://fastapi.tiangolo.com/tutorial/first-steps/), the `uv` quickstart.

**After this phase you'll know:** how a FastAPI app is structured, how `uvicorn --reload` works, what those auto-generated `/docs` are (Swagger UI; free with FastAPI).

---

### Phase 2 — Typed request and response with Pydantic

**What you'll learn:** Why we use Pydantic models for inputs and outputs instead of raw `dict`s. The shape of a Pydantic v2 model.

**What to build:**
- Create `src/km_bot/api/schemas.py`.
- Define `class AskRequest(BaseModel): question: str` and `class AskResponse(BaseModel): answer: str`.
- Create `src/km_bot/api/chat.py` with `POST /chat/ask` that takes an `AskRequest` and returns an `AskResponse` echoing the question back (`answer=f"You asked: {request.question}"`).
- Register the chat router in `main.py`.

**How to know it works:** Use the auto-generated `/docs` page to send a POST. You get back `{"answer": "You asked: ..."}`. If you send invalid JSON, you get a nice 422 error automatically.

**Read:** [FastAPI's Body — Pydantic Models](https://fastapi.tiangolo.com/tutorial/body/) tutorial.

**After this phase you'll know:** the request/response contract is *the* boundary of your API; Pydantic enforces it for free.

---

### Phase 3 — Async, for real, by calling Azure OpenAI

**What you'll learn:** `async def`, `await`, why FastAPI loves them, how to make an HTTP call to an external service.

**What to build:**
- Get an Azure OpenAI resource (or use your existing one). Note your endpoint, API key, deployment name, and API version.
- Add the OpenAI SDK: `uv add openai`.
- Create `src/km_bot/llm/azure_openai.py` with an async function `async def complete(prompt: str) -> str:` that calls Azure OpenAI's chat completion and returns the assistant's text.
- Modify `POST /chat/ask` to actually call `complete(request.question)` and return the result.
- Hardcode your Azure key/endpoint for now — we'll fix this in Phase 5.

**How to know it works:** You POST `{"question": "What is the capital of France?"}`. You get back `{"answer": "Paris."}` (or similar). You've just made a chatbot.

**Read:** [Real Python's async/await primer](https://realpython.com/async-io-python/), [Azure OpenAI Python SDK docs](https://learn.microsoft.com/en-us/azure/ai-services/openai/quickstart).

**After this phase you'll know:** async functions return immediately and yield while waiting; FastAPI runs many of them at once; this is why we use `async def` for any I/O.

**Deep-dive moment:** Run two requests in parallel using a browser tab and `curl`. Notice that while one is waiting for Azure, the other can be served. *That* is what async bought you.

---

### Phase 4 — Refactor: separate the workflow from the route

**What you'll learn:** Why route handlers should be thin. Your first "service" function.

**What to build:**
- Create `src/km_bot/services/answer_question.py` with `async def answer_question(question: str) -> str:` that calls `llm.azure_openai.complete()`.
- Change `chat.py`'s handler to just call `answer_question(request.question)` and wrap the result in `AskResponse`.

**Why bother (deep-dive):** Right now this looks like a useless extra step — and it is, for one function. But in Phase 12 your `answer_question` will: look up cache → embed → search Qdrant → call LLM → store cache → update history. Five steps. If those five steps live in `chat.py`, you've recreated the v1 mess: a 364-line route handler. By extracting *now*, you've made room for *later*.

**After this phase you'll know:** the route layer is for HTTP plumbing; the services layer is where the workflow lives.

---

### Phase 5 — Configuration via Pydantic Settings

**What you'll learn:** Reading environment variables in a typed, validated way. `.env` files. Why hardcoded secrets are bad.

**What to build:**
- Add: `uv add pydantic-settings python-dotenv`.
- Create `src/km_bot/config.py` with a `class Settings(BaseSettings)` exposing `azure_openai_endpoint`, `azure_openai_api_key`, `azure_openai_deployment`, `azure_openai_api_version`. Tell it to read from `.env`.
- Create a `.env` file with real values. Create `.env.example` with placeholders. Add `.env` to `.gitignore`.
- Inject `Settings` into `azure_openai.py` instead of hardcoding values.

**How to know it works:** Run again, get the same chatbot result. Now delete one env var and watch the app refuse to start with a clear error. That's the validation working.

**Read:** [Pydantic Settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

**After this phase you'll know:** every secret comes from `.env`; the code itself contains no secrets and no `os.getenv()` calls outside `config.py`.

---

### Phase 6 — Logging you can actually read

**What you'll learn:** Why `print()` is not enough. What "structured logging" means. Correlation IDs.

**What to build:**
- Add: `uv add structlog`.
- Create `src/km_bot/logging_setup.py` that configures structlog to emit JSON to stdout in production and pretty colors in dev.
- Replace any `print()` statements you've sprinkled with `logger.info("answering question", question=q)`.
- Add a FastAPI middleware that generates a UUID per request and attaches it to every log line for that request.

**Deep-dive moment:** Why JSON logs? Because when you later ship this to a real environment, log aggregators (Loki, Splunk, CloudWatch) parse JSON automatically — you can search `level=ERROR AND endpoint=/chat/ask`. With plain-text logs you'd be grepping forever.

**After this phase you'll know:** logs are data, not prose; structlog gives you key-value pairs for free.

---

### Phase 7 — Your first database: PostgreSQL with async SQLAlchemy

**What you'll learn:** Installing Postgres locally, async DB drivers, SQLAlchemy 2.x with `async`, Alembic migrations.

**What to build:**
- Install PostgreSQL locally (Windows installer or use Docker if you're OK with Docker — but to honour "no Docker yet," install Postgres directly).
- Add: `uv add sqlalchemy[asyncio] asyncpg alembic`.
- Create `src/km_bot/database/session.py` with an async engine + session factory.
- Create `src/km_bot/database/models.py` with **one** SQLAlchemy model: `CachedAnswer (id, question, answer, created_at)`.
- Run `alembic init`, configure it to use your `Settings.database_url`, generate your first migration, apply it.
- Use FastAPI's lifespan hook to open the connection pool at startup and close it at shutdown.

**Deep-dive moment:** Why async? Because if your DB query takes 200ms, your whole server doesn't freeze. While the DB is thinking, FastAPI serves other requests. `asyncpg` is the Postgres driver that supports this.

**Read:** [SQLAlchemy's async ORM tutorial](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html), [Alembic quickstart](https://alembic.sqlalchemy.org/en/latest/tutorial.html).

**After this phase you'll know:** how to talk to a real database, how migrations work (no more hand-editing tables), how connection pools live for the lifetime of the app.

---

### Phase 8 — Cache answers in Postgres

**What you'll learn:** Writing your first repository function. The save/load round trip.

**What to build:**
- Add `src/km_bot/database/repositories.py` with `async def save_cached_answer(...)` and `async def find_cached_answer_by_question(question)` (exact-string match for now — semantic match comes in Phase 10).
- In `services/answer_question.py`: before calling the LLM, check the cache; after, save to cache.

**How to know it works:** Ask the same question twice; the second time the response is much faster, and the log says "cache hit".

**After this phase you'll know:** the *shape* of every storage interaction — a small function in `repositories.py` that the service calls. You'll never write raw SQL in a route handler. Ever.

---

### Phase 9 — Embeddings: turning text into numbers

**What you'll learn:** What an embedding *is*. Why "similarity in meaning" becomes "distance between vectors."

**What to build:**
- Add: `uv add sentence-transformers`.
- Create `src/km_bot/embeddings/local.py` with `def embed(text: str) -> list[float]:` using `sentence-transformers/all-MiniLM-L6-v2`.
- Write a one-off script (in `scripts/`) that embeds three sentences and prints the cosine similarity between them. Verify "the cat sat on the mat" is more similar to "a cat is on a rug" than to "interest rates rose 2%".

**Deep-dive moment:** Each embedding is 384 floats. That's the model's compressed sense of "what does this text mean?" Two texts with similar embeddings mean similar things — even with totally different words. This is the magic that makes RAG work.

**Read:** [Sentence Transformers quickstart](https://www.sbert.net/docs/quickstart.html).

**After this phase you'll know:** embedding is just a function: text in, vector out.

---

### Phase 10 — Qdrant: your vector database

**What you'll learn:** Installing and running Qdrant locally, creating a collection, upserting points, searching.

**What to build:**
- Install Qdrant locally (download the binary from their releases, run it on `localhost:6333`).
- Add: `uv add qdrant-client`.
- Create `src/km_bot/vector_store/qdrant.py` with helpers: `ensure_collection()`, `upsert(id, vector, payload)`, `search(query_vector, top_k) -> list[Match]`.
- Write a script: embed 3 sentences (from Phase 9), upsert them as points with `id=1,2,3` and `payload={"text": ...}`, then search with a 4th sentence and print which one comes back.

**Deep-dive moment:** Qdrant is just a fast nearest-neighbour search engine for vectors. Give it a query vector, it gives you the IDs of the most similar stored vectors. That's the whole thing.

**Read:** [Qdrant Python quickstart](https://qdrant.tech/documentation/quick-start/).

**After this phase you'll know:** how to store and retrieve vectors. The bones of RAG are now in place.

---

### Phase 11 — Your first document parser (markdown)

**What you'll learn:** Reading a file, splitting it into chunks, attaching metadata (filename, section).

**What to build:**
- Add: `uv add markdown-it-py langchain-text-splitters` (we use `RecursiveCharacterTextSplitter` from `langchain-text-splitters`, but only that — no full LangChain).
- Define a `Chunk` dataclass (or Pydantic model) in `parsers/base.py`: `text`, `source_file`, `section`, `chunk_index`.
- Create `parsers/markdown.py` with `def parse(path: Path) -> Iterable[Chunk]`. Read the file, split on `#` headers, then recursively split each section into ~1000-char chunks with ~200-char overlap.
- Write a script that parses one markdown file and prints all chunks.

**Deep-dive moment:** Chunk size is a tuning knob. Too small and the LLM lacks context. Too big and embeddings become muddy. ~1000 chars is a fine starting point.

---

### Phase 12 — Real RAG: connect everything

**What you'll learn:** The full RAG flow. How retrieval, prompting, and generation compose.

**What to build:**
- Create `services/ingest_document.py`: for a given file path, dispatch to the right parser (just markdown for now), embed each chunk, upsert into Qdrant with payload `{"text": ..., "source_file": ..., "section": ...}`.
- Create a `POST /knowledge/ingest` endpoint that takes a folder path and runs `ingest_document` for every `.md` file.
- Update `services/answer_question.py` to: embed the question → search Qdrant for top-5 chunks → build a prompt like `"Use the following context to answer. Context: {chunks}. Question: {question}. Answer:"` → call the LLM → return both the answer and the source chunks.
- Update `AskResponse` schema to include `sources: list[Source]`.

**How to know it works:** Ingest a folder of markdown notes. Ask a question whose answer is *only* in one of those notes. Verify (a) the answer is correct and (b) the source list points to the right file.

**Deep-dive moment:** This is RAG. Everything you've built so far has been preparing for this. Re-read your code top to bottom and notice how each layer plays its part.

**After this phase you'll know:** you've built a working RAG bot from scratch. The hard part is done. Everything after is filling in capabilities.

---

### Phase 13 — More parsers: PDF, DOCX, PPTX

**What you'll learn:** Each file format has its own quirks. A `parsers/` factory dispatches by extension.

**What to build:**
- Add: `uv add pypdf python-docx python-pptx`.
- Implement `parsers/pdf.py`, `parsers/docx.py`, `parsers/pptx.py`. Each yields `Chunk`s with `page_no` or `slide_no` in the metadata.
- In `services/ingest_document.py`, swap the hardcoded "markdown only" with a dispatch dict: `{".md": markdown.parse, ".pdf": pdf.parse, ...}`.

**After this phase you'll know:** when you want to add a new file type, you add one file and one dict entry. Nothing else changes. That's the payoff of keeping parsers in their own folder.

---

### Phase 14 — Semantic cache: smarter answer reuse

**What you'll learn:** Cache hits don't have to be exact-string matches. "What's the capital of France?" and "France's capital?" should both hit the same cache.

**What to build:**
- Add a new Qdrant collection `cached_questions`.
- When you successfully answer a question, embed the question and upsert it into `cached_questions` with payload `{"answer_id": <postgres_id>}`.
- Before calling the LLM, search `cached_questions` for top-1 with similarity > 0.95. If found, fetch the answer from Postgres by `answer_id`.

**Deep-dive moment:** You've now got two Qdrant collections doing two different jobs: document chunks for retrieval, question vectors for caching. Same primitive (vector search), different purpose. Notice how cheap it was to add — your `vector_store/` helpers didn't need to change.

---

### Phase 15 — Conversation history & question rewriting

**What you'll learn:** Why follow-up questions ("which language can be used with it?") need rewriting to be searchable.

**What to build:**
- Add a `conversations` and `messages` table in Postgres.
- After each successful answer, append the user message and assistant message to the current conversation.
- Before retrieval, if there's history, ask the LLM to rewrite the question into a standalone version using the last 3 turns.
- Use the rewritten version for retrieval, but log both.

**Deep-dive moment:** This is the first place a single user interaction triggers *two* LLM calls (rewrite + answer). Notice you didn't need to restructure anything — you added a step inside `answer_question.py`.

---

### Phase 16 — A second LLM provider: Ollama (local)

**What you'll learn:** *This* is the moment "keep LLM code in its own folder" pays off. You add a new provider without touching any other layer.

**What to build:**
- Install Ollama locally. Pull a small model (`ollama pull phi3` or `llama3.2`).
- Create `src/km_bot/llm/ollama.py` with the same shape as `azure_openai.py`: `async def complete(prompt: str) -> str`.
- Add `LLM_PROVIDER` to `Settings` (`"azure"` or `"ollama"`).
- In `main.py` (or a tiny `llm/__init__.py`), pick the right module based on the setting and expose it as a single `complete` function.

**Deep-dive moment:** This is **dependency inversion** — the fancy SOLID phrase. Your `services/answer_question.py` doesn't know which provider it's calling. It just calls `llm.complete()`. Tomorrow you can add a third provider; nothing else changes. You did this without ever drawing a UML diagram.

---

### Phase 17 — Hybrid search (dense + sparse)

**What you'll learn:** Pure vector search misses things keyword search catches (proper nouns, version numbers). Combining them is best practice.

**What to build:**
- Add `uv add fastembed` to get the sparse model `prithivida/Splade_PP_en_v1`.
- Extend `vector_store/qdrant.py` to upsert *both* dense and sparse vectors per chunk and to search hybrid (Qdrant's `query_points` API supports this natively now).

**Deep-dive moment:** Try a question with a version number, e.g. *"What changed in v2.3.0?"* — sparse-aware hybrid search will rank exact-match chunks higher than pure dense search would.

---

### Phase 18 — Audio and video (Whisper)

**What you'll learn:** Long-form transcription and chunking by time, not characters.

**What to build:**
- Add: `uv add faster-whisper`.
- Create `parsers/media.py` that transcribes audio/video and yields chunks with `start_time` and `end_time` in metadata.
- Dispatch `.mp3`, `.mp4`, etc. to it in `ingest_document.py`.

---

### Phase 19 — Error handling, problem responses, and `/healthz`

**What you'll learn:** Failures should be structured. A `503 Service Unavailable` with `{"detail": "Qdrant unreachable"}` is much better than a stack trace.

**What to build:**
- Add a global FastAPI `exception_handler` that maps your own exceptions (`LLMError`, `RetrievalError`, etc.) to JSON error responses with appropriate status codes.
- Add a `/healthz` endpoint that returns `200` if Postgres and Qdrant both respond to a ping; `503` otherwise.

---

### Phase 20 — You're done. Catch your breath.

You have a real, complete, working RAG service. Built by hand. Every line owned.

Walk yourself through the code. Open every file. Explain (out loud, to the rubber duck) what it does and why it's in that folder. If you can do that, you own this project.

---

## 7. The parking lot — things to pick up later

When you've shipped v2 and the urge for completeness returns, the next things to learn (roughly in order of usefulness) are:

1. **Automated tests** — pytest, fixtures, mocking the LLM. By now your shape is stable; tests will pay off.
2. **Authentication** — at first something simple like an API key in a header; later Entra ID / JWT.
3. **Docker** — wrap your app in a single image; learn `docker-compose` for spinning up Postgres + Qdrant + app together.
4. **CI/CD** — GitHub Actions to lint and run tests on every push.
5. **Deployment** — once Docker works locally, push the image to a registry and run it on a real server.
6. **Observability beyond logs** — OpenTelemetry traces, Prometheus metrics, Grafana dashboards.
7. **Hardening** — rate limiting, input size limits, secrets in a vault, proper CORS.

Each of those is its own learning project. None of them are needed for the bot itself to work.

---

## 8. How to use this document day-to-day

- **Don't read this whole thing twice.** Read it once now. Then jump to the phase you're working on. Refer back to §2-§4 whenever you forget the shape of the project.
- **One phase at a time.** Don't try to be clever and skip ahead.
- **When you finish a phase, commit.** A clean commit per phase gives you a beautiful history and a free undo button.
- **When stuck, ask.** Either of me or of Google. Stuck means more than 30 minutes — before that, struggle is the learning.
- **Update this document.** If a phase took longer than expected, note it. If you found a better library, note it. This is *your* roadmap; let it grow with you.

---

You own this project. Go build it.
