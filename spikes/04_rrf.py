import re

import numpy as np
from google import genai
from google.genai import types
from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    """
    Case-insensitive word tokenization.
    Extracts alphanumeric words and underscores, preserving hex codes and underscores.
    """
    return re.findall(r'[a-zA-Z0-9_]+', text.lower())

def compute_cosine_similarity(vec_x: np.ndarray, vec_y: np.ndarray) -> float:
    """
    Computes standard cosine similarity between two vectors.
    """
    dot_product = np.dot(vec_x, vec_y)
    norm_x = np.linalg.norm(vec_x)
    norm_y = np.linalg.norm(vec_y)
    if norm_x == 0 or norm_y == 0:
        return 0.0
    return float(dot_product / (norm_x * norm_y))

def main():
    # 1. Corpus of 5 realistic incident runbooks
    documents = [
        "Runbook: Restart checkout API deployment when HTTP 500 error spike occurs on gateway.",
        "Runbook: Increase pgbouncer max_client_conn and inspect active locks on fatal DB connection pool exhaustion.",
        "Runbook: Clear Redis cache keys and restart cluster on memory leak OOMKilled alerts.",
        "Runbook: Diagnose 0x80004005 database authentication and handshake timeouts.",
        "Runbook: Fix CSS flexbox alignment and responsiveness on payment checkout buttons."
    ]
    doc_ids = [f"Doc {i}" for i in range(1, 6)]

    # Sample query
    query = "FATAL 0x80004005 postgres pool exhausted"

    print(f"Query: \"{query}\"\n")

    # ==================================================================================
    # CHANNEL A: Sparse Lexical (BM25)
    # ==================================================================================
    print("Executing Channel A (BM25 Lexical Retrieval)...")
    tokenized_corpus = [tokenize(doc) for doc in documents]
    tokenized_query = tokenize(query)
    
    bm25 = BM25Okapi(tokenized_corpus)
    bm25_scores = bm25.get_scores(tokenized_query)
    
    # Sort and rank Channel A (1-based ranks)
    # If scores are identical, Python's stable sort maintains order.
    ranked_bm25 = sorted(
        enumerate(bm25_scores),
        key=lambda x: x[1],
        reverse=True
    )
    
    # Map doc_id to its BM25 score and rank
    bm25_rankings = {}
    for rank, (doc_idx, score) in enumerate(ranked_bm25, 1):
        bm25_rankings[doc_ids[doc_idx]] = {"score": score, "rank": rank, "content": documents[doc_idx]}

    # ==================================================================================
    # CHANNEL B: Dense Vector (gemini-embedding-001 with MRL 768)
    # ==================================================================================
    print("Executing Channel B (gemini-embedding-001 with MRL output_dimensionality=768)...")
    client = genai.Client()
    
    # Generate embeddings in batch for query + 5 documents
    all_texts = [query] + documents
    response = client.models.embed_content(
        model='gemini-embedding-001',
        contents=all_texts,
        config=types.EmbedContentConfig(
            output_dimensionality=768
        )
    )
    
    # Extract query vector and document vectors
    query_vector = np.array(response.embeddings[0].values)
    doc_vectors = [np.array(emb.values) for emb in response.embeddings[1:]]
    
    # Calculate cosine similarity for all documents
    dense_scores = [compute_cosine_similarity(query_vector, vec) for vec in doc_vectors]
    
    # Sort and rank Channel B (1-based ranks)
    ranked_dense = sorted(
        enumerate(dense_scores),
        key=lambda x: x[1],
        reverse=True
    )
    
    # Map doc_id to its Dense score and rank
    dense_rankings = {}
    for rank, (doc_idx, score) in enumerate(ranked_dense, 1):
        dense_rankings[doc_ids[doc_idx]] = {"score": score, "rank": rank, "content": documents[doc_idx]}

    # ==================================================================================
    # RECIPROCAL RANK FUSION (RRF)
    # ==================================================================================
    print("Computing Reciprocal Rank Fusion (RRF)...")
    k = 60  # Standard smoothing constant
    
    rrf_scores = {}
    for d_id in doc_ids:
        rank_bm25 = bm25_rankings[d_id]["rank"]
        rank_dense = dense_rankings[d_id]["rank"]
        
        # Calculate standard RRF score
        score_rrf = (1.0 / (k + rank_bm25)) + (1.0 / (k + rank_dense))
        rrf_scores[d_id] = {
            "score": score_rrf,
            "rank_bm25": rank_bm25,
            "score_bm25": bm25_rankings[d_id]["score"],
            "rank_dense": rank_dense,
            "score_dense": dense_rankings[d_id]["score"],
            "content": bm25_rankings[d_id]["content"]
        }
        
    # Sort final RRF merged ranking
    ranked_rrf = sorted(
        rrf_scores.items(),
        key=lambda x: x[1]["score"],
        reverse=True
    )

    # ==================================================================================
    # PRINT RESULTS
    # ==================================================================================
    print("\n" + "="*80)
    print("CHANNEL A: BM25 RANKED RESULTS (LEXICAL)")
    print("="*80)
    for doc_id, data in sorted(bm25_rankings.items(), key=lambda x: x[1]["rank"]):
        print(f"Rank {data['rank']}: {doc_id} | Score: {data['score']:.4f}")
        print(f"  Content: \"{data['content']}\"\n")

    print("="*80)
    print("CHANNEL B: DENSE EMBEDDING RANKED RESULTS (SEMANTIC)")
    print("="*80)
    for doc_id, data in sorted(dense_rankings.items(), key=lambda x: x[1]["rank"]):
        print(f"Rank {data['rank']}: {doc_id} | Score: {data['score']:.4f}")
        print(f"  Content: \"{data['content']}\"\n")

    print("="*80)
    print("FINAL HYBRID MERGED RESULTS: RECIPROCAL RANK FUSION (RRF)")
    print("="*80)
    for final_rank, (doc_id, data) in enumerate(ranked_rrf, 1):
        print(f"Rank {final_rank}: {doc_id} | RRF Score: {data['score']:.6f}")
        print(f"  [BM25 Rank: {data['rank_bm25']} (Score: {data['score_bm25']:.4f})] "
              f"[Dense Rank: {data['rank_dense']} (Score: {data['score_dense']:.4f})]")
        print(f"  Content: \"{data['content']}\"\n")

    # Mathematical explanation in terminal print for completeness & clarity
    print(
        "--- RRF Architectural Insights ---\n"
        "1. The Scale Mismatch Problem:\n"
        "   - BM25 scores are unbounded positive floats (e.g. from 0.0 up to 10+ depending on IDF and lengths).\n"
        "   - Cosine Similarity is bounded between -1.0 and 1.0 (with positive semantic matches usually between 0.2 and 0.8).\n"
        "   - Directly summing raw scores would allow BM25's larger numbers to completely swamp and ignore the dense scores.\n"
        "   - Normalizing raw scores (e.g. Min-Max) is volatile because scores shift dynamically per query and corpus sizes.\n"
        "   - RRF solves this elegantly by discarding raw scores completely and fusing strictly based on document RANKS (1st, 2nd, etc.).\n"
        "\n"
        "2. The Role of the Smoothing Constant (k = 60):\n"
        "   - The RRF score is sum(1 / (k + rank)).\n"
        "   - If k = 0, a document ranked 1st has score 1.0, and 2nd has 0.5 (a massive 0.5 penalty drop).\n"
        "   - If k = 60, a document ranked 1st has score 1/61 (~0.01639), and 2nd has 1/62 (~0.01612) (a tiny 0.00027 difference).\n"
        "   - A smoothing constant of 60 ensures that outliers top-ranked in only one list do not drown out\n"
        "     consistent performers that place well across both channels (e.g., scoring highly in both lexical and semantic).\n"
    )

    # Inline mathematical comments:
    """
    ========================================================================================
    RECIPROCAL RANK FUSION (RRF) MATH ANALYSIS
    ========================================================================================
    RRF computes a single score for each document d by summing the reciprocals of its ranks
    across M different rank-ordered retrieval lists (e.g., Lexical and Semantic):
    
        RRF_Score(d) = sum_{m in M} ( 1 / (k + r_m(d)) )
        
    Where:
      - r_m(d) is the 1-based rank position of document d in the list m.
      - k is a constant parameter (empirically optimized to 60) that regulates rank penalization.
      
    1. Why Rank Fusion?
       BM25 and Vector scores represent completely different mathematical scales and cannot be directly compared.
       BM25 is based on term frequency and document statistics (unbounded, often > 1).
       Cosine similarity is an angular calculation (bounded [-1, 1]).
       Direct summation, weighted addition, or heuristic scaling are highly unstable across different corpora.
       RRF bypasses score calibration issues by treating the retrieval outputs as pure sorted lists of preferences.
       
    2. Role of the constant 'k':
       The constant 'k' serves to flatten the hyperbola of reciprocal ranks (1/x).
       - Without k (k = 0), the drop between rank 1 and 2 is huge (1/1 - 1/2 = 0.50). 
         A document that gets rank 1 in lexical but rank 50 in semantic scores 1/1 + 1/50 = 1.02.
         A document that gets rank 2 in both scores 1/2 + 1/2 = 1.00. 
         Here, a highly volatile 1st place outlier in a single channel wins, ignoring the mutual consistency.
       - With k = 60, the drop between rank 1 and 2 is extremely subtle (1/61 - 1/62 = 0.00027).
         Doc 1 (rank 1 and 50) scores 1/61 + 1/110 = 0.01639 + 0.00909 = 0.02548.
         Doc 2 (rank 2 and 2) scores 1/62 + 1/62 = 0.01613 + 0.01613 = 0.03226.
         Now, the consistent performer (Doc 2) correctly wins. RRF rewards stability across models.
    """

if __name__ == "__main__":
    main()
