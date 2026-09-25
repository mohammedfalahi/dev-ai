from pathlib import Path

from packages.knowledge.chunker import (
    chunk_markdown_file,
    chunk_markdown_text,
    slugify,
)

RUNBOOKS_FILE = Path("data/generated/runbooks.md")


def test_chunk_generated_runbooks():
    """Verify chunking against the 6 verified operational runbooks in data/generated/runbooks.md."""
    assert RUNBOOKS_FILE.is_file(), f"Test fixture not found: {RUNBOOKS_FILE}"

    chunks = chunk_markdown_file(RUNBOOKS_FILE)
    assert len(chunks) > 0, "No chunks were produced from runbooks.md"

    # 1. Assert all 6 runbooks are extracted
    extracted_runbook_ids = {chunk.runbook_id for chunk in chunks}
    expected_runbook_ids = {
        "RB-PG-001",
        "RB-PG-002",
        "RB-REDIS-001",
        "RB-STRIPE-001",
        "RB-K8S-001",
        "RB-EDGE-001",
    }
    assert expected_runbook_ids.issubset(extracted_runbook_ids), (
        f"Missing expected runbooks: {expected_runbook_ids - extracted_runbook_ids}"
    )
    assert len(extracted_runbook_ids) == 6, (
        f"Expected 6 runbooks, found {len(extracted_runbook_ids)}"
    )

    # 2. Assert chunk IDs are deterministic and unique
    chunk_ids = [chunk.chunk_id for chunk in chunks]
    assert len(chunk_ids) == len(set(chunk_ids)), (
        f"Duplicate chunk IDs found: {chunk_ids}"
    )

    # Re-running parsing produces identical chunk IDs (determinism)
    chunks_second_run = chunk_markdown_file(RUNBOOKS_FILE)
    assert [c.chunk_id for c in chunks_second_run] == chunk_ids

    # 3. Assert every chunk has intact bash/SQL code blocks (matching ``` pairs)
    for chunk in chunks:
        fence_count = chunk.content.count("```")
        assert fence_count % 2 == 0, (
            f"Broken code fence in chunk '{chunk.chunk_id}': found {fence_count} backtick fences (must be even)"
        )

    # 4. Assert no chunk has an empty heading_path or empty search_text
    for chunk in chunks:
        assert isinstance(chunk.heading_path, list)
        assert len(chunk.heading_path) > 0, (
            f"Empty heading_path for chunk '{chunk.chunk_id}'"
        )
        assert all(isinstance(h, str) and h.strip() for h in chunk.heading_path), (
            f"Invalid heading item in chunk '{chunk.chunk_id}': {chunk.heading_path}"
        )

        assert chunk.content.strip(), f"Empty content for chunk '{chunk.chunk_id}'"
        assert chunk.search_text.strip(), (
            f"Empty search_text for chunk '{chunk.chunk_id}'"
        )
        assert chunk.token_count > 0, (
            f"Non-positive token count for chunk '{chunk.chunk_id}'"
        )

        # Verify context enrichment breadcrumb formatting
        breadcrumbs = " > ".join(chunk.heading_path)
        expected_prefix = f"Service: {chunk.service} | "
        assert chunk.search_text.startswith(expected_prefix), (
            f"search_text in '{chunk.chunk_id}' does not start with expected service prefix: {chunk.search_text[:50]}"
        )
        assert f"Path: {breadcrumbs}" in chunk.search_text


def test_code_block_protection_header_detection():
    """Verify headers inside code fences (e.g. bash comments starting with ##) are not split."""
    sample_md = """---
runbook_id: RB-TEST-001
title: Test Header In Code Block
service: test-svc
---

# Test Header In Code Block

## Diagnostic Script

Here is the diagnostic script:

```bash
## This is a comment inside bash script, NOT a markdown header
kubectl get pods
### Another sub-comment inside code
echo "healthy"
```

## Next Steps

Follow the standard procedure.
"""
    chunks = chunk_markdown_text(sample_md)
    # Should only create 2 chunks: 'Diagnostic Script' and 'Next Steps'
    assert len(chunks) == 2
    assert chunks[0].heading_path == ["Diagnostic Script"]
    assert "## This is a comment inside bash script" in chunks[0].content
    assert "### Another sub-comment inside code" in chunks[0].content
    assert chunks[0].content.count("```") == 2
    assert chunks[1].heading_path == ["Next Steps"]


def test_long_section_subdivision_preserving_code_blocks():
    """Verify that sections exceeding 600 words are subdivided across paragraph boundaries

    while keeping code blocks intact.
    """
    long_paragraph = "word " * 400
    code_block = (
        "```sql\n" + ("SELECT * FROM orders WHERE status = 'failed';\n" * 20) + "```\n"
    )
    second_paragraph = "recovery " * 350

    sample_md = f"""---
runbook_id: RB-LONG-001
title: Long Section Runbook
service: checkout
---

# Long Section Runbook

## Large Section

{long_paragraph}

{code_block}

{second_paragraph}
"""
    chunks = chunk_markdown_text(sample_md)
    # Since total words exceed 600, it must subdivide into at least 2 chunks
    assert len(chunks) >= 2
    for chunk in chunks:
        # All chunks share the same heading_path
        assert chunk.heading_path == ["Large Section"]
        # Code fence must remain intact if present in chunk
        assert chunk.content.count("```") % 2 == 0

    # Ensure chunk IDs follow {runbook_id}::{section_slug}::{idx}
    assert chunks[0].chunk_id == "RB-LONG-001::large-section::0"
    assert chunks[1].chunk_id == "RB-LONG-001::large-section::1"


def test_slugify():
    assert slugify("Initial checks — read-only") == "initial-checks-read-only"
    assert slugify("PostgreSQL & Redis Status (v1.0)") == "postgresql-redis-status-v10"
    assert slugify("   Clean   Slug   ") == "clean-slug"
