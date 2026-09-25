import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RunbookChunk(BaseModel):
    chunk_id: str = Field(
        description="Unique deterministic chunk ID: {runbook_id}::{section_slug}::{idx}"
    )
    runbook_id: str = Field(description="Identifier of the parent runbook")
    service: str = Field(description="Target service name")
    heading_path: list[str] = Field(
        description="Breadcrumb heading path (e.g. ['Initial checks — read-only'])"
    )
    content: str = Field(description="Clean markdown content for LLM synthesis")
    search_text: str = Field(
        description="Context-enriched text for vector and BM25 search"
    )
    token_count: int = Field(
        description="Estimated token count using regex tokenization"
    )


def slugify(text: str) -> str:
    """Generate a clean URL/identifier-friendly slug from a section title."""
    # Remove non-alphanumeric characters (excluding spaces and hyphens)
    cleaned = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[-\s]+", "-", cleaned)
    return slug or "section"


def count_tokens(text: str) -> int:
    """Fast regex-based token counter (matches words or individual punctuation symbols)."""
    return len(re.findall(r"\w+|[^\w\s]", text))


def _split_into_blocks(text: str) -> list[str]:
    """Split section content into atomic markdown blocks (paragraphs and code fences).

    Code fences (``` ... ```) are treated as single indivisible atomic blocks.
    """
    lines = text.splitlines(keepends=True)
    blocks: list[str] = []
    current_block: list[str] = []
    in_code_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            current_block.append(line)
            if not in_code_fence:
                # Closed code fence: end current block
                blocks.append("".join(current_block).strip())
                current_block = []
            continue

        if in_code_fence:
            current_block.append(line)
            continue

        # Outside code fence: blank line denotes paragraph boundary
        if not stripped:
            if current_block:
                blocks.append("".join(current_block).strip())
                current_block = []
        else:
            current_block.append(line)

    if current_block:
        blocks.append("".join(current_block).strip())

    return [b for b in blocks if b]


def _subdivide_section(content: str, max_words: int = 600) -> list[str]:
    """Subdivide a section into sub-chunks if total words exceed max_words.

    Maintains code block integrity by operating over atomic blocks.
    """
    blocks = _split_into_blocks(content)
    if not blocks:
        return []

    chunks: list[str] = []
    current_chunk_blocks: list[str] = []
    current_word_count = 0

    for block in blocks:
        block_words = len(block.split())
        if current_chunk_blocks and (current_word_count + block_words > max_words):
            # Finalize current chunk
            chunks.append("\n\n".join(current_chunk_blocks))
            current_chunk_blocks = [block]
            current_word_count = block_words
        else:
            current_chunk_blocks.append(block)
            current_word_count += block_words

    if current_chunk_blocks:
        chunks.append("\n\n".join(current_chunk_blocks))

    return chunks


def _extract_runbook_documents(full_text: str) -> list[tuple[dict[str, Any], str]]:
    """Extract frontmatter and body pairs from markdown files.

    Supports both single-document runbooks and multi-document aggregated markdown files.
    """
    pattern = re.compile(r"(?:^|\n)---\s*\n(.*?)\n---\s*(?:\n|$)", re.DOTALL)
    matches = list(pattern.finditer(full_text))

    if not matches:
        # No frontmatter found; treat as single document with default metadata
        return [({}, full_text.strip())]

    documents: list[tuple[dict[str, Any], str]] = []
    for i, match in enumerate(matches):
        fm_raw = match.group(1)
        try:
            frontmatter = yaml.safe_load(fm_raw) or {}
        except yaml.YAMLError:
            frontmatter = {}

        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        body = full_text[body_start:body_end].strip()
        documents.append((frontmatter, body))

    return documents


def _parse_runbook_sections(
    body: str, default_title: str
) -> list[tuple[list[str], str]]:
    """Parse markdown body into sections based on ## and ### headers.

    Code fences are strictly protected so comments or code lines starting with
    ## or ### are never treated as markdown headers.
    """
    lines = body.splitlines()
    sections: list[tuple[list[str], str]] = []

    current_h2: str | None = None
    current_h3: str | None = None
    current_lines: list[str] = []
    in_code_fence = False

    def finalize_current():
        nonlocal current_lines
        content = "\n".join(current_lines).strip()
        if content:
            if current_h2 and current_h3:
                heading_path = [current_h2, current_h3]
            elif current_h2:
                heading_path = [current_h2]
            elif current_h3:
                heading_path = [current_h3]
            else:
                heading_path = ["Overview"]
            sections.append((heading_path, content))
        current_lines = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            current_lines.append(line)
            continue

        if not in_code_fence:
            # Check for H1 (document title) - ignore header line itself if seen at start
            if stripped.startswith("# ") and not stripped.startswith("## "):
                continue

            # Check for H2
            if stripped.startswith("## ") and not stripped.startswith("### "):
                finalize_current()
                current_h2 = stripped[3:].strip()
                current_h3 = None
                continue

            # Check for H3
            if stripped.startswith("### "):
                finalize_current()
                current_h3 = stripped[4:].strip()
                continue

        current_lines.append(line)

    finalize_current()
    return sections


def chunk_markdown_text(
    text: str, default_metadata: dict[str, Any] | None = None
) -> list[RunbookChunk]:
    """Parse and chunk markdown text into a list of structured RunbookChunk instances."""
    documents = _extract_runbook_documents(text)
    chunks: list[RunbookChunk] = []

    for doc_fm, doc_body in documents:
        merged_fm = {**(default_metadata or {}), **doc_fm}
        runbook_id = str(
            merged_fm.get("runbook_id") or merged_fm.get("id") or "UNKNOWN"
        )
        title = str(merged_fm.get("title") or "Runbook")
        service = str(merged_fm.get("service") or "general")

        sections = _parse_runbook_sections(doc_body, default_title=title)

        for heading_path, section_content in sections:
            # Subdivide if section exceeds 600 words
            sub_contents = _subdivide_section(section_content, max_words=600)
            section_slug = slugify(heading_path[-1])

            for idx, content in enumerate(sub_contents):
                clean_content = content.strip()
                if not clean_content:
                    continue

                chunk_id = f"{runbook_id}::{section_slug}::{idx}"
                breadcrumbs = " > ".join(heading_path)
                search_text = f"Service: {service} | Runbook: {title} | Path: {breadcrumbs}\n\n{clean_content}"
                tokens = count_tokens(clean_content)

                chunk = RunbookChunk(
                    chunk_id=chunk_id,
                    runbook_id=runbook_id,
                    service=service,
                    heading_path=heading_path,
                    content=clean_content,
                    search_text=search_text,
                    token_count=tokens,
                )
                chunks.append(chunk)

    return chunks


def extract_runbooks_and_chunks(
    file_path: str | Path,
) -> tuple[list[dict[str, Any]], list[RunbookChunk]]:
    """Read a markdown file and extract both runbook metadata records and RunbookChunks."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Runbook file not found: {path}")

    text = path.read_text(encoding="utf-8")
    documents = _extract_runbook_documents(text)

    runbooks: list[dict[str, Any]] = []
    chunks: list[RunbookChunk] = []

    for doc_fm, doc_body in documents:
        runbook_id = str(doc_fm.get("runbook_id") or doc_fm.get("id") or "UNKNOWN")
        title = str(doc_fm.get("title") or "Runbook")
        service = str(doc_fm.get("service") or "general")
        tags = [str(t) for t in (doc_fm.get("tags") or [])]
        source_url = doc_fm.get("source_url")
        last_verified_at = doc_fm.get("last_verified_at") or "NOW()"
        owner = str(doc_fm.get("owner") or "Platform")

        runbooks.append(
            {
                "id": runbook_id,
                "title": title,
                "service": service,
                "tags": tags,
                "source_url": source_url,
                "last_verified_at": last_verified_at,
                "owner": owner,
            }
        )

        sections = _parse_runbook_sections(doc_body, default_title=title)

        for heading_path, section_content in sections:
            sub_contents = _subdivide_section(section_content, max_words=600)
            section_slug = slugify(heading_path[-1])

            for idx, content in enumerate(sub_contents):
                clean_content = content.strip()
                if not clean_content:
                    continue

                chunk_id = f"{runbook_id}::{section_slug}::{idx}"
                breadcrumbs = " > ".join(heading_path)
                search_text = f"Service: {service} | Runbook: {title} | Path: {breadcrumbs}\n\n{clean_content}"
                tokens = count_tokens(clean_content)

                chunk = RunbookChunk(
                    chunk_id=chunk_id,
                    runbook_id=runbook_id,
                    service=service,
                    heading_path=heading_path,
                    content=clean_content,
                    search_text=search_text,
                    token_count=tokens,
                )
                chunks.append(chunk)

    return runbooks, chunks


def chunk_markdown_file(file_path: str | Path) -> list[RunbookChunk]:
    """Read a markdown file from disk and chunk it using structure-aware contextual parsing."""
    _, chunks = extract_runbooks_and_chunks(file_path)
    return chunks
