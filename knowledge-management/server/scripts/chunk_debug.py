"""
Strategy 3 chunking — visualised in three stages.

Run from the server/ directory:

    uv run python scripts/chunk_debug.py samples/rag-guide.md

What you'll see:

  STAGE 1 — MarkdownHeaderTextSplitter ONLY
            Splits the document at heading boundaries. No size limit.
            Each output is a "section" tagged with its heading path.
            Notice: section sizes vary wildly. Some sections will be
            much larger than chunk_size — they'll need Stage 2.

  STAGE 2 — Add RecursiveCharacterTextSplitter inside each section
            Sections larger than chunk_size get split into multiple
            size-limited pieces. Sections smaller than chunk_size
            pass through unchanged. Adjacent pieces inside the same
            section share `chunk_overlap` characters of context.

  STAGE 3 — Your parsers/markdown.py output (Chunk objects)
            What your real parser produces: each piece from Stage 2
            wrapped in a Chunk with source_file, chunk_index, and
            header_path-in-metadata. Stage 3 only runs once you've
            implemented parsers/markdown.py.

The whole point of this script is to make the abstract "what does
header-aware then recursive splitting do?" question concrete.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make src/ importable so we can read settings (and the parser, once you write it)
SERVER_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_ROOT / "src"))

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from config import settings


HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]
LINE = "─" * 80


def preview(text: str, n: int = 90) -> str:
    """Collapse whitespace and truncate, so output stays on one line."""
    cleaned = " ".join(text.split())
    return cleaned[:n] + ("..." if len(cleaned) > n else "")


def header_path_of(metadata: dict) -> list[str]:
    """Pull h1/h2/h3 (in order, only the ones present) into a list."""
    return [metadata[k] for k in ("h1", "h2", "h3") if k in metadata]


def stage1_header_split_only(text: str) -> list:
    print(LINE)
    print("STAGE 1 — MarkdownHeaderTextSplitter (header boundaries only, no size limit)")
    print(LINE)

    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS)
    docs = splitter.split_text(text)

    for i, doc in enumerate(docs):
        path = header_path_of(doc.metadata)
        path_str = " > ".join(path) if path else "(no header — pre-heading text)"
        warn = "  ⚠ exceeds chunk_size" if len(doc.page_content) > settings.chunk_size else ""
        print(f"\n  Section {i:>2}  [{len(doc.page_content):>5} chars]{warn}")
        print(f"     path:     {path_str}")
        print(f"     metadata: {doc.metadata}")
        print(f"     content:  {preview(doc.page_content, 110)}")

    print()
    print(f"  → {len(docs)} sections produced.")
    over = sum(1 for d in docs if len(d.page_content) > settings.chunk_size)
    if over:
        print(f"  → {over} section(s) exceed chunk_size={settings.chunk_size}; Stage 2 will split them.")
    else:
        print(f"  → All sections fit within chunk_size={settings.chunk_size}; Stage 2 will pass them through.")
    print()
    return docs


def stage2_add_recursive_split(header_docs: list) -> None:
    print(LINE)
    print(
        f"STAGE 2 — RecursiveCharacterTextSplitter inside each section "
        f"(chunk_size={settings.chunk_size}, overlap={settings.chunk_overlap})"
    )
    print(LINE)

    recursive = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
    )

    total = 0
    for i, doc in enumerate(header_docs):
        path = header_path_of(doc.metadata)
        path_str = " > ".join(path) if path else "(no header)"
        pieces = recursive.split_text(doc.page_content)

        if len(pieces) == 1:
            print(f"\n  Section {i:>2} [{path_str}]")
            print(f"     → 1 piece ({len(pieces[0])} chars) — passed through, no further split")
        else:
            print(f"\n  Section {i:>2} [{path_str}]  ⚠ section was too big, split into {len(pieces)} pieces")
            for j, p in enumerate(pieces):
                marker = "└─" if j == len(pieces) - 1 else "├─"
                print(f"     {marker} piece {j} [{len(p):>4} chars]  {preview(p, 80)}")
        total += len(pieces)

    print()
    print(f"  → {len(header_docs)} sections → {total} pieces total after size-limited splitting.")
    print(f"  → Notice: split pieces within the same section share the same header_path.")
    print()


def stage3_parser_output(text: str, source_file: str) -> None:
    print(LINE)
    print("STAGE 3 — Your parsers/markdown.py output (Chunk objects)")
    print(LINE)

    try:
        from parsers.markdown import parse  # noqa: PLC0415 — intentional lazy import
    except (ImportError, AttributeError) as e:
        print()
        print(f"  parsers/markdown.py doesn't yet export `parse()` — {e}")
        print("  Complete Step 5 in docs/V0_BUILD_STEPS.md, then re-run this script.")
        print()
        return

    chunks = parse(text.encode("utf-8"), source_file=source_file)

    for c in chunks:
        path = c.metadata.get("header_path", [])
        path_str = " > ".join(path) if path else "(no header)"
        print(f"\n  Chunk {c.chunk_index:>2}  [{len(c.text):>4} chars]")
        print(f"     source_file: {c.source_file}")
        print(f"     header_path: {path}")
        print(f"     location:    {path_str}")
        print(f"     metadata:    {c.metadata}")
        print(f"     text:        {preview(c.text, 110)}")

    print()
    print(f"  → {len(chunks)} Chunk objects produced.")
    print(f"  → Each has a unique chunk_index and inherits its section's header_path.")

    # Sanity checks worth eyeballing
    sections_seen: dict[tuple, int] = {}
    for c in chunks:
        key = tuple(c.metadata.get("header_path", []))
        sections_seen[key] = sections_seen.get(key, 0) + 1
    multi_chunk_sections = {k: v for k, v in sections_seen.items() if v > 1}
    if multi_chunk_sections:
        print()
        print("  Multi-chunk sections (Strategy 3 size-limit kicked in here):")
        for path, count in multi_chunk_sections.items():
            label = " > ".join(path) if path else "(no header)"
            print(f"     • {label}  →  {count} chunks")
    print()


def main(path: Path) -> None:
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    print()
    print(f"  Loaded: {path}")
    print(f"  Size:   {len(text)} chars")
    print(f"  Config: chunk_size={settings.chunk_size}, chunk_overlap={settings.chunk_overlap}")
    print()

    header_docs = stage1_header_split_only(text)
    stage2_add_recursive_split(header_docs)
    stage3_parser_output(text, source_file=path.name)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run python scripts/chunk_debug.py <path-to-markdown>")
        sys.exit(1)
    main(Path(sys.argv[1]))
