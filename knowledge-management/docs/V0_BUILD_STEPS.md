# v0 — Build Steps: Markdown Ingestion → Qdrant Cloud

> **What this doc is:** the standing reference for building the end-to-end markdown ingestion flow on the `v0` branch. Every step is self-contained — open the doc, find your step, do it, verify, move on.
>
> **What this doc isn't:** copy-paste code. Each step shows *shape* (signatures, imports, key decisions) and explains the *why*. You write the bodies.

---

## Table of contents

- [Architecture at a glance](#architecture-at-a-glance)
- [The dispatch pattern (the most important idea)](#the-dispatch-pattern-the-most-important-idea)
- [Three DI patterns, three jobs (cheat sheet)](#three-di-patterns-three-jobs-cheat-sheet)
- [Build order — 14 steps](#build-order)
  - [Step 1 — Dependencies](#step-1--dependencies)
  - [Step 2 — `.gitignore`, `.env.example`, `.env`](#step-2--gitignore-envexample-env)
  - [Step 3 — `src/config.py`](#step-3--srcconfigpy)
  - [Step 4 — `src/parsers/base.py`](#step-4--srcparsersbasepy)
  - [Step 5 — `src/parsers/markdown.py`](#step-5--srcparsersmarkdownpy)
  - [Step 6 — placeholder parsers (`pdf.py`, `docx.py`, `pptx.py`)](#step-6--placeholder-parsers)
  - [Step 7 — `src/parsers/registry.py`](#step-7--srcparsersregistrypy)
  - [Step 8 — `src/parsers/__init__.py`](#step-8--srcparsersinitpy)
  - [Step 9 — `src/embeddings/local.py`](#step-9--srcembeddingslocalpy)
  - [Step 10 — `src/vector_store/qdrant.py`](#step-10--srcvector_storeqdrantpy)
  - [Step 11 — `src/services/ingest_document.py`](#step-11--srcservicesingest_documentpy)
  - [Step 12 — `src/api/schemas.py`](#step-12--srcapischemaspy)
  - [Step 13 — `src/api/document.py`](#step-13--srcapidocumentpy)
  - [Step 14 — `src/main.py` lifespan](#step-14--srcmainpy-lifespan)
- [Verification gauntlet](#verification-gauntlet)
- [When you add a new parser later](#when-you-add-a-new-parser-later)

---

## Architecture at a glance

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
                  │ parsers/ │  │embeddings/│  │ vector_store/ │  ← THE OPERATIONS
                  │ markdown │  │  local    │  │   qdrant      │     (mechanics —
                  │ pdf      │  │           │  │               │      each its own
                  │ docx     │  │           │  │               │      external lib)
                  │ pptx     │  │           │  │               │
                  └──────────┘  └───────────┘  └───────────────┘
```

**The rule:** arrows point down only. `api/` calls `services/`. `services/` calls `parsers/`, `embeddings/`, `vector_store/`. Nothing reaches back up. Nothing reaches sideways.

---

## The dispatch pattern (the most important idea)

When the service needs the right parser for a file, it **does not** use if/elif:

```python
# ❌ Never. Grows unboundedly. Violates Open/Closed.
if filename.endswith(".md"):    chunks = markdown.parse(...)
elif filename.endswith(".pdf"): chunks = pdf.parse(...)
elif filename.endswith(".docx"):chunks = docx.parse(...)
```

It uses a **registry** (a dispatch dict):

```python
# parsers/registry.py
PARSERS: dict[str, ParserFn] = {
    ".md":   markdown.parse,
    ".pdf":  pdf.parse,
    ".docx": docx.parse,
    ".pptx": pptx.parse,
}

def get_parser_for(filename: str) -> ParserFn:
    ext = Path(filename).suffix.lower()
    parser = PARSERS.get(ext)
    if parser is None:
        raise UnsupportedFileTypeError(ext)
    return parser
```

Service usage shrinks to two lines:

```python
parser = get_parser_for(filename)
chunks = parser(content, filename)
```

Adding a new format = **one new entry in the dict.** Service code never changes. That's Open/Closed in three lines.

---

## Three DI patterns, three jobs (cheat sheet)

| Pattern | Use it for | Example in this app |
| --- | --- | --- |
| **Module-level singleton** (`settings = Settings()`) | True constants. Loaded once at import. Used everywhere including non-HTTP code. | `config.settings` |
| **`@lru_cache` + `Depends`** | Things that belong to the request lifecycle but should be cached. | (none in v0; reserved for future per-user/per-tenant resolvers) |
| **`app.state` + lifespan + `Depends`** | Resources with `.close()` / `__aexit__`. Lifecycle managed by FastAPI. | `app.state.qdrant_client`, `app.state.embedder` |

---

## Build order

### Step 1 — Dependencies

From inside `server/`:

```
uv add pydantic-settings
uv add langchain-text-splitters
uv add fastembed
uv add qdrant-client
```

What each gives you:
- `pydantic-settings` — typed `.env` loading with validation.
- `langchain-text-splitters` — `MarkdownHeaderTextSplitter` + `RecursiveCharacterTextSplitter`. Only LangChain piece we use.
- `fastembed` — ONNX-backed embeddings. No PyTorch dependency. Same library will give us sparse embeddings later.
- `qdrant-client` — async client for Qdrant Cloud.

`fastapi[standard]` already provides Uvicorn + `python-multipart` (needed for `UploadFile`).

**Verify:**
```
uv run python -c "import fastembed, qdrant_client, langchain_text_splitters, pydantic_settings; print('ok')"
```
Must print `ok`.

---

### Step 2 — `.gitignore`, `.env.example`, `.env`

**Concept:** Secrets never live in source. `.env.example` is the shape (committed). `.env` is the contents (gitignored).

**Files:**

- **Root `.gitignore`** — append:
  ```
  .env
  .venv/
  __pycache__/
  *.pyc
  .mypy_cache/
  .pytest_cache/
  .ruff_cache/
  ```

- **`server/.env.example`** — committed template:
  ```
  QDRANT_URL=
  QDRANT_API_KEY=
  QDRANT_COLLECTION=documents
  EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
  CHUNK_SIZE=1000
  CHUNK_OVERLAP=200
  ```

- **`server/.env`** — same keys filled with real values. Never committed.

**Verify:** `git status` shows `server/.env.example` as a new file but does NOT show `server/.env`.

---

### Step 3 — `src/config.py`

**Concept:** All env vars flow through one typed object. Nothing else in the codebase touches `os.environ`. Pydantic validates at app startup — missing required vars fail loudly and immediately, not deep in a request three hours later.

**Pattern choice:** module-level singleton (`settings = Settings()`), NOT `@lru_cache + Depends`. Settings is read by parsers, services, lifespan, and REPL scripts — most of those have no `Request`. A module-level singleton is universally accessible; DI is not.

**File: `src/config.py`**

```python
# shape, not full code
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    qdrant_url: str                 # required (no default)
    qdrant_api_key: str             # required (no default)
    qdrant_collection: str = "documents"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chunk_size: int = 1000
    chunk_overlap: int = 200

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

settings = Settings()    # module-level singleton
```

**Verify** (from `server/`):
```
uv run python -c "import sys; sys.path.insert(0, 'src'); from config import settings; print(settings.qdrant_collection, settings.chunk_size)"
```
Should print `documents 1000`. If it errors with `Field required`, your `.env` is missing keys.

---

### Step 4 — `src/parsers/base.py`

**Concept:** Every parser produces the same shape (a list of `Chunk`s) regardless of file type. This uniformity is what lets embed + store be format-agnostic. `Chunk` is the common currency of the system.

But — "location within source" looks different for each format (markdown has header paths, PDF has page numbers, video has timestamps). So `Chunk` has a **common typed core** plus a **flexible `metadata` bag** for format-specific data. Each parser documents its own metadata convention.

`ParserFn` formalises the contract: any function `(bytes, str) -> list[Chunk]` is a parser. The registry will be typed against it.

**Bytes, not str?** Yes. PDF/DOCX/PPTX are binary; the route gets `bytes` from `UploadFile.read()`; the markdown parser decodes internally. Uniform interface > convenience.

**File: `src/parsers/base.py`**

```python
# shape
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(slots=True, frozen=True)
class Chunk:
    text: str                          # the content (what gets embedded)
    source_file: str                   # universal — origin filename
    chunk_index: int                   # universal — ordinal position within the file
    metadata: dict[str, Any]           # format-specific (header_path, page_number, etc.)

ParserFn = Callable[[bytes, str], list[Chunk]]

class UnsupportedFileTypeError(Exception):
    def __init__(self, extension: str):
        super().__init__(f"Unsupported file extension: {extension!r}")
        self.extension = extension
```

**Why this shape?**
- `text`, `source_file`, `chunk_index` are truly universal — every chunk needs them.
- `metadata` is a `dict[str, Any]` because "location within source" looks different per format. The dict trades type safety for honesty about format variation.
- Each parser file documents its own `metadata` keys in a docstring at the top — that's how we keep this from becoming a free-for-all.

**Per-format metadata conventions (documented per parser):**

| Format | Metadata keys |
| --- | --- |
| Markdown | `header_path: list[str]` — e.g. `["Getting Started", "Installation"]` |
| PDF (future) | `page_number: int`, optionally `section_heading: str` |
| DOCX (future) | `header_path: list[str]` (extracted from Heading 1/2/3 styles) |
| PPTX (future) | `slide_number: int`, optionally `slide_title: str` |
| Audio / Video (future) | `start_time: float`, `end_time: float` (seconds) |

**Why `frozen=True, slots=True`?**
- `frozen=True` makes Chunk immutable — prevents accidental mutation bugs.
- `slots=True` saves memory when you hold thousands of chunks.
- Both are nearly free; opt in.

---

### Step 5 — `src/parsers/markdown.py`

**Concept (Strategy 3 chunking):**
1. **Step A — header split.** `MarkdownHeaderTextSplitter` returns `Document`s carrying header metadata (`h1`, `h2`, `h3`).
2. **Step B — recursive split.** Inside each section, `RecursiveCharacterTextSplitter` enforces size limits while respecting paragraph → sentence → word boundaries.
3. **Step C — wrap.** Each resulting piece becomes a `Chunk` with the section's header path attached.

The output: chunks that (a) never span section boundaries and (b) carry their "address" in the document.

**File: `src/parsers/markdown.py`**

```python
# shape
#
# Metadata convention for this parser:
#   { "header_path": list[str] }   e.g. ["Getting Started", "Installation"]
#
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from parsers.base import Chunk
from config import settings

HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]

def parse(content: bytes, source_file: str) -> list[Chunk]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{source_file} is not valid UTF-8 markdown") from e

    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS)
    header_docs = header_splitter.split_text(text)

    recursive_splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    chunks: list[Chunk] = []
    for doc in header_docs:
        header_path = [doc.metadata[k] for k in ("h1", "h2", "h3") if k in doc.metadata]
        pieces = recursive_splitter.split_text(doc.page_content)
        for piece in pieces:
            chunks.append(Chunk(
                text=piece,
                source_file=source_file,
                chunk_index=len(chunks),
                metadata={"header_path": header_path},
            ))
    return chunks
```

**Edge cases to handle:**
- Markdown with no headers → `MarkdownHeaderTextSplitter` returns one doc with empty metadata → chunks have `header_path=[]`.
- Section shorter than `chunk_size` → recursive splitter returns one piece.
- Empty file → returns `[]`.

**Verify in REPL:**
```python
content = b"# Intro\n\nHello world.\n\n## Setup\n\nRun `uv sync`.\n"
chunks = parse(content, "test.md")
for c in chunks:
    print(c.chunk_index, c.metadata.get("header_path"), c.text[:50])
```
Expect two chunks, one with `header_path=["Intro"]` in metadata, one with `header_path=["Intro", "Setup"]`.

---

### Step 6 — placeholder parsers

**Concept:** Placeholders are *contracts*. By registering them, the dispatch is honest: "I know what a PDF is; I just haven't implemented it." Better error than "Unsupported file type" for known formats.

**Three files**, identical shape:

```python
# src/parsers/pdf.py  (and docx.py, pptx.py — same shape, different message)
from parsers.base import Chunk

def parse(content: bytes, source_file: str) -> list[Chunk]:
    raise NotImplementedError(
        f"PDF parser is not yet implemented (file: {source_file})"
    )
```

When you implement real PDF parsing later, you replace this body. Nothing else in the codebase changes.

---

### Step 7 — `src/parsers/registry.py`

**Concept:** The central map from extension → parser. The one file you edit when adding a new format.

**File: `src/parsers/registry.py`**

```python
# shape
from pathlib import Path
from parsers import markdown, pdf, docx, pptx
from parsers.base import ParserFn, UnsupportedFileTypeError

PARSERS: dict[str, ParserFn] = {
    ".md":   markdown.parse,
    ".pdf":  pdf.parse,
    ".docx": docx.parse,
    ".pptx": pptx.parse,
}

def get_parser_for(filename: str) -> ParserFn:
    ext = Path(filename).suffix.lower()
    parser = PARSERS.get(ext)
    if parser is None:
        raise UnsupportedFileTypeError(ext)
    return parser
```

**Note:** dict values are *function references*, not calls. `markdown.parse` (no parens) — that's an object you can store and call later.

**Verify in REPL:**
```python
get_parser_for("hello.md")      # returns markdown.parse
get_parser_for("hello.pdf")     # returns pdf.parse (placeholder)
get_parser_for("hello.txt")     # raises UnsupportedFileTypeError
```

---

### Step 8 — `src/parsers/__init__.py`

Expose the package's public API:

```python
# src/parsers/__init__.py
from parsers.base import Chunk, ParserFn, UnsupportedFileTypeError
from parsers.registry import get_parser_for, PARSERS

__all__ = [
    "Chunk", "ParserFn", "UnsupportedFileTypeError",
    "get_parser_for", "PARSERS",
]
```

Now everywhere else imports as `from parsers import get_parser_for, Chunk`. The internal files (`markdown.py`, `pdf.py`, …) are implementation details.

---

### Step 9 — `src/embeddings/local.py`

**Concept:** One job — turn text into 384-dim vectors. No knowledge of Qdrant, no knowledge of file formats, no knowledge of HTTP.

The embedder is heavy (loads an ONNX model into RAM). It's created in lifespan and lives on `app.state.embedder`. Routes get it via `EmbedderDep`.

**File: `src/embeddings/local.py`**

```python
# shape
from typing import Annotated
from fastapi import Depends, Request
from fastembed import TextEmbedding

def get_embedder(request: Request) -> TextEmbedding:
    return request.app.state.embedder

EmbedderDep = Annotated[TextEmbedding, Depends(get_embedder)]

def embed_texts(embedder: TextEmbedding, texts: list[str]) -> list[list[float]]:
    vectors = embedder.embed(texts)        # iterator of np.ndarray
    return [v.tolist() for v in vectors]
```

Also create empty `src/embeddings/__init__.py`.

**Verify in REPL** (slow first time — downloads ~50 MB ONNX model):
```python
from fastembed import TextEmbedding
emb = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
vecs = embed_texts(emb, ["hello", "world"])
assert len(vecs) == 2 and len(vecs[0]) == 384
```

---

### Step 10 — `src/vector_store/qdrant.py`

**Concept:** Qdrant operations module. Client lives on `app.state` (it has `.close()` — needs lifecycle management). Routes get the client via `QdrantClientDep`. Functions take the client as their first parameter.

**File: `src/vector_store/qdrant.py`**

```python
# shape
import uuid
from typing import Annotated
from fastapi import Depends, Request
from qdrant_client import AsyncQdrantClient, models

from config import settings
from parsers import Chunk

def get_qdrant_client(request: Request) -> AsyncQdrantClient:
    return request.app.state.qdrant_client

QdrantClientDep = Annotated[AsyncQdrantClient, Depends(get_qdrant_client)]

async def ensure_collection(client: AsyncQdrantClient) -> None:
    exists = await client.collection_exists(settings.qdrant_collection)
    if not exists:
        await client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=models.VectorParams(
                size=384,
                distance=models.Distance.COSINE,
            ),
        )

async def upsert_chunks(
    client: AsyncQdrantClient,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> int:
    points = [
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vec,
            payload={
                "text": chunk.text,
                "source_file": chunk.source_file,
                "chunk_index": chunk.chunk_index,
                **chunk.metadata,                  # spread format-specific keys
            },
        )
        for chunk, vec in zip(chunks, vectors)
    ]
    await client.upsert(
        collection_name=settings.qdrant_collection,
        points=points,
    )
    return len(points)
```

Also create empty `src/vector_store/__init__.py`.

**Verify in REPL:**
```python
import asyncio
from qdrant_client import AsyncQdrantClient
client = AsyncQdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
asyncio.run(ensure_collection(client))
# Check Qdrant Cloud dashboard — `documents` collection exists, 384 dim, cosine.
```

---

### Step 11 — `src/services/ingest_document.py`

**Concept:** The only place that knows the full workflow. Picks the parser via the registry, calls it, embeds, stores. No format-specific branches anywhere.

**File: `src/services/ingest_document.py`**

```python
# shape
from dataclasses import dataclass
from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient

from parsers import Chunk, get_parser_for
from embeddings.local import embed_texts
from vector_store.qdrant import upsert_chunks

@dataclass
class IngestResult:
    filename: str
    total_chunks: int
    chunks: list[Chunk]

async def ingest_document(
    filename: str,
    content: bytes,
    client: AsyncQdrantClient,
    embedder: TextEmbedding,
) -> IngestResult:
    parser = get_parser_for(filename)         # registry dispatch
    chunks = parser(content, filename)        # format-specific
    if not chunks:
        return IngestResult(filename, 0, [])
    vectors = embed_texts(embedder, [c.text for c in chunks])
    await upsert_chunks(client, chunks, vectors)
    return IngestResult(filename, len(chunks), chunks)
```

**Notice:** no `if filename.endswith(...)` anywhere. The registry handles dispatch; the service handles workflow.

Also create empty `src/services/__init__.py`.

---

### Step 12 — `src/api/schemas.py`

**Concept:** Pydantic models at the API boundary define the *contract*. They're separate from the internal `Chunk` dataclass — API can change without forcing domain change.

**File: `src/api/schemas.py`**

The `to_preview` helper produces a uniform "location" string regardless of source format — markdown gets a header breadcrumb, PDF gets a page number, video gets a timestamp. The API user sees a consistent shape; the helper handles the per-format translation.

```python
# shape
from pydantic import BaseModel
from parsers import Chunk

class ChunkPreview(BaseModel):
    chunk_index: int
    location: str                # uniform string across formats
    text_preview: str            # first ~200 chars
    char_count: int

class IngestResponse(BaseModel):
    filename: str
    total_chunks: int
    collection: str
    sample_chunks: list[ChunkPreview]

def to_preview(chunk: Chunk) -> ChunkPreview:
    meta = chunk.metadata
    if meta.get("header_path"):
        location = " > ".join(meta["header_path"])
    elif "page_number" in meta:
        location = f"Page {meta['page_number']}"
    elif "slide_number" in meta:
        location = f"Slide {meta['slide_number']}"
    elif "start_time" in meta:
        location = f"@{meta['start_time']:.1f}s"
    else:
        location = "(unknown)"
    return ChunkPreview(
        chunk_index=chunk.chunk_index,
        location=location,
        text_preview=chunk.text[:200],
        char_count=len(chunk.text),
    )
```

---

### Step 13 — `src/api/document.py`

**Concept:** The route is thin. Validate input shape, call the service, format the response. No business logic, no parser dispatch, no embedding, no Qdrant.

**File: `src/api/document.py`**

```python
# shape
from typing import Annotated
from fastapi import APIRouter, File, HTTPException, UploadFile

from config import settings
from parsers import UnsupportedFileTypeError
from embeddings.local import EmbedderDep
from vector_store.qdrant import QdrantClientDep
from services.ingest_document import ingest_document
from api.schemas import IngestResponse, to_preview

router = APIRouter(tags=["Documents"])

FileUpload = Annotated[UploadFile, File()]

@router.post("/ingest", response_model=IngestResponse)
async def ingest(
    file: FileUpload,
    client: QdrantClientDep,
    embedder: EmbedderDep,
) -> IngestResponse:
    content = await file.read()
    try:
        result = await ingest_document(file.filename, content, client, embedder)
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {e.extension}")
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return IngestResponse(
        filename=result.filename,
        total_chunks=result.total_chunks,
        collection=settings.qdrant_collection,
        sample_chunks=[to_preview(c) for c in result.chunks[:3]],
    )
```

**HTTP 501 Not Implemented** is the correct code for "we know what this is but haven't built it yet." Perfect match for the placeholder parsers.

---

### Step 14 — `src/main.py` lifespan

**Concept:** Lifespan constructs the long-lived resources (Qdrant client, embedder) at startup, tears them down at shutdown. They live on `app.state`.

**Replace your lifespan body:**

```python
# shape — replace the empty lifespan
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient

from api.document import router as DocumentRouter
from config import settings
from embeddings.local import embed_texts
from vector_store.qdrant import ensure_collection

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- startup ---
    app.state.qdrant_client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    app.state.embedder = TextEmbedding(model_name=settings.embedding_model)
    await ensure_collection(app.state.qdrant_client)
    embed_texts(app.state.embedder, ["warmup"])    # forces model load now
    yield
    # --- shutdown ---
    await app.state.qdrant_client.close()

app = FastAPI(lifespan=lifespan)
app.include_router(DocumentRouter, prefix="/document")

@app.get("/")
async def test():
    return {"message": "hello world"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

---

## Verification gauntlet

Once all 14 steps are in:

1. **Server starts cleanly:**
   ```
   uv run uvicorn main:app --reload --app-dir src
   ```
   First start: slow (model download). Subsequent: fast (~2–3 s).

2. **Hello-world works:** `GET http://localhost:8000/` returns `{"message": "hello world"}`.

3. **Swagger shows the endpoint:** `http://localhost:8000/docs` shows `POST /document/ingest` with a file-upload widget.

4. **Upload a markdown file with headers.** Response: `total_chunks > 0`, `sample_chunks` populated with correct `header_path` values.

5. **Upload a `.pdf`.** Response: HTTP **501 Not Implemented**, message: `"PDF parser is not yet implemented (file: ...)"`. **This proves the dispatch works.**

6. **Upload a `.txt`.** Response: HTTP **400**, `"Unsupported file type: .txt"`. The registry correctly rejected an unknown extension.

7. **Open Qdrant Cloud dashboard.** Your `documents` collection has `total_chunks` points. Click one — payload has `text`, `source_file`, `header_path`, `chunk_index`.

When all seven pass, the architecture is real, not just a diagram.

---

## When you add a new parser later

The whole point of this design. To add (say) CSV ingestion:

1. **Create `src/parsers/csv.py`** with `def parse(content: bytes, source_file: str) -> list[Chunk]` — real implementation.
2. **Add one line to `src/parsers/registry.py`**: `".csv": csv.parse,`.
3. **Optionally update `src/parsers/__init__.py`** if you want CSV exposed in `__all__` (not required).

That's it. Three files touched, two of them trivially. The service layer, the embeddings module, the vector store, the API, the lifespan — none of them change. They don't even know a new format was added.

That's the architecture paying its rent.

---

## Three DI patterns (repeated here for quick lookup)

| Pattern | Use it for | Example in this app |
| --- | --- | --- |
| Module-level singleton (`settings = Settings()`) | True constants, loaded once at import, used everywhere | `config.settings` |
| `@lru_cache` + `Depends` | Request-lifecycle things expensive to construct per-request | (none in v0) |
| `app.state` + lifespan + `Depends` | Resources with `.close()` / `__aexit__` | `app.state.qdrant_client`, `app.state.embedder` |

---

End of v0 build steps. Keep this file next to your editor.
