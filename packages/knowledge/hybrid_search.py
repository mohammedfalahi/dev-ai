import os
from dataclasses import dataclass

import psycopg
from google import genai
from google.genai import types
from pydantic import BaseModel
from sentence_transformers import CrossEncoder

from packages.core.config import settings
from packages.observability import trace_span

# Lazy-loaded model to prevent instantiation overhead when not searching
_cross_encoder = None


class RetrievalResult(BaseModel):
    chunk_id: str
    runbook_id: str
    service: str
    heading_path: list[str]
    content: str
    dense_rank: int | None
    fts_rank: int | None
    rrf_score: float
    rerank_score: float


@dataclass
class _Candidate:
    chunk_id: str
    runbook_id: str
    service: str
    heading_path: list[str]
    content: str
    dense_rank: int | None = None
    fts_rank: int | None = None


def get_postgres_connection():
    return psycopg.connect(os.environ.get("DATABASE_URL", settings.db_conn_str))


def search_runbooks(
    query: str, top_k: int = 3, min_rerank_score: float | None = None
) -> list[RetrievalResult]:
    """
    Search runbooks using a Retrieve-and-Rerank hybrid pipeline.

    Stage 1:
      a) Fetch Top-10 using pgvector (Dense Semantic Search).
      b) Fetch Top-10 using tsvector (Sparse Lexical Search).
      c) Merge ranks using Reciprocal Rank Fusion (RRF, k=60).
    Stage 2:
      a) Rerank Top-5 fused candidates using MS-MARCO Cross-Encoder.
      b) Apply refusal gate (`min_rerank_score`) to reject out-of-domain queries.
    """
    if min_rerank_score is None:
        min_rerank_score = settings.min_rerank_score

    global _cross_encoder
    if _cross_encoder is None:
        # Load lightweight Cross-Encoder. MS-MARCO outputs raw negative logits.
        _cross_encoder = CrossEncoder(settings.reranker_model)

    with trace_span(
        name="hybrid_search_runbooks",
        as_type="retriever",
        input={"query": query, "top_k": top_k, "min_rerank_score": min_rerank_score},
    ) as retriever_span:
        # 1. Compute query embedding vector and fetch dense candidates
        with trace_span(
            name="dense_retrieval_pgvector",
            as_type="retriever",
            input={"query": query, "embedding_model": settings.embedding_model, "limit": 10},
        ) as dense_span:
            client = genai.Client()
            response = client.models.embed_content(
                model=settings.embedding_model,
                contents=query,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=settings.embedding_dim,
                ),
            )
            if not response.embeddings or not response.embeddings[0].values:
                raise ValueError("Failed to retrieve embeddings from model")
            query_vector = response.embeddings[0].values

            candidates: dict[str, _Candidate] = {}

            with get_postgres_connection() as conn, conn.cursor() as cur:
                # 2. Fetch top 10 dense candidates (pgvector cosine distance)
                cur.execute(
                    f"""
                    SELECT rc.id, rc.runbook_id, r.service, rc.heading_path, rc.content,
                           (rc.embedding <=> %s::vector({settings.embedding_dim})) AS dist
                    FROM runbook_chunks rc
                    JOIN runbooks r ON rc.runbook_id = r.id
                    ORDER BY dist ASC
                    LIMIT 10;
                    """,
                    (f"[{','.join(str(f) for f in query_vector)}]",),
                )

                dense_rows = cur.fetchall()
                for rank, row in enumerate(dense_rows, start=1):
                    chunk_id, runbook_id, service, heading_path, content, _dist = row
                    candidates[chunk_id] = _Candidate(
                        chunk_id=chunk_id,
                        runbook_id=runbook_id,
                        service=service,
                        heading_path=heading_path,
                        content=content,
                        dense_rank=rank,
                    )
            dense_span.update(output={"dense_candidates_count": len(dense_rows)})

        # 2. Fetch top 10 sparse FTS candidates (Postgres plainto_tsquery)
        with trace_span(
            name="sparse_retrieval_bm25_fts",
            as_type="retriever",
            input={"query": query, "limit": 10},
        ) as sparse_span:
            with get_postgres_connection() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT rc.id, rc.runbook_id, r.service, rc.heading_path, rc.content,
                           ts_rank_cd(rc.fts, plainto_tsquery('english', %s)) AS rank
                    FROM runbook_chunks rc
                    JOIN runbooks r ON rc.runbook_id = r.id
                    WHERE rc.fts @@ plainto_tsquery('english', %s)
                    ORDER BY rank DESC
                    LIMIT 10;
                    """,
                    (query, query),
                )

                fts_rows = cur.fetchall()
                for rank, row in enumerate(fts_rows, start=1):
                    chunk_id, runbook_id, service, heading_path, content, _ts_rank = row
                    if chunk_id in candidates:
                        candidates[chunk_id].fts_rank = rank
                    else:
                        candidates[chunk_id] = _Candidate(
                            chunk_id=chunk_id,
                            runbook_id=runbook_id,
                            service=service,
                            heading_path=heading_path,
                            content=content,
                            fts_rank=rank,
                        )
            sparse_span.update(output={"sparse_candidates_count": len(fts_rows)})

        if not candidates:
            retriever_span.update(output={"results_count": 0, "refused": True})
            return []

        # 3. Merge using Reciprocal Rank Fusion (RRF)
        k_rrf = 60
        fused_scores = {}
        with trace_span(
            name="rrf_fusion",
            as_type="span",
            input={"total_candidates": len(candidates), "k_rrf": k_rrf},
        ) as rrf_span:
            for chunk_id, c in candidates.items():
                score = 0.0
                if c.dense_rank is not None:
                    score += 1.0 / (k_rrf + c.dense_rank)
                if c.fts_rank is not None:
                    score += 1.0 / (k_rrf + c.fts_rank)
                fused_scores[chunk_id] = score

            # Sort and take top 5 fused candidates for reranking
            sorted_fused = sorted(
                fused_scores.items(), key=lambda item: item[1], reverse=True
            )
            top_5_fused = sorted_fused[:5]
            rrf_span.update(output={"fused_top_5": [cid for cid, _ in top_5_fused]})

        # 4. Score using MS-MARCO Cross-Encoder and apply refusal gate
        final_results = []
        with trace_span(
            name="cross_encoder_rerank_cutoff",
            as_type="span",
            input={
                "candidates_count": len(top_5_fused),
                "model": settings.reranker_model,
                "min_rerank_score": min_rerank_score,
            },
        ) as rerank_span:
            cross_encoder_inputs = []
            candidates_to_rerank = []

            for chunk_id, _ in top_5_fused:
                c = candidates[chunk_id]
                breadcrumb = " > ".join(c.heading_path)
                enriched_input = f"Service: {c.service} | Path: {breadcrumb} | {c.content}"
                cross_encoder_inputs.append([query, enriched_input])
                candidates_to_rerank.append(c)

            # Output is a NumPy array of raw logits
            rerank_scores = _cross_encoder.predict(cross_encoder_inputs)

            for i, c in enumerate(candidates_to_rerank):
                rrf_score = fused_scores[c.chunk_id]
                rerank_score = float(rerank_scores[i])

                final_results.append(
                    RetrievalResult(
                        chunk_id=c.chunk_id,
                        runbook_id=c.runbook_id,
                        service=c.service,
                        heading_path=c.heading_path,
                        content=c.content,
                        dense_rank=c.dense_rank,
                        fts_rank=c.fts_rank,
                        rrf_score=rrf_score,
                        rerank_score=rerank_score,
                    )
                )

            # Sort descending by rerank score
            final_results.sort(key=lambda x: x.rerank_score, reverse=True)
            top_score = final_results[0].rerank_score if final_results else None
            refused = top_score is None or top_score < min_rerank_score
            rerank_span.update(output={"top_rerank_score": top_score, "refused": refused})

        # Refusal gate check on the absolute best candidate
        if final_results[0].rerank_score < min_rerank_score:
            retriever_span.update(
                output={"results_count": 0, "refused": True, "top_rerank_score": top_score}
            )
            return []

        returned = final_results[:top_k]
        retriever_span.update(
            output={
                "results_count": len(returned),
                "refused": False,
                "top_rerank_score": returned[0].rerank_score,
                "chunk_ids": [r.chunk_id for r in returned],
            }
        )
        return returned
