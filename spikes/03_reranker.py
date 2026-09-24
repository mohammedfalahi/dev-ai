import time
from sentence_transformers import CrossEncoder

def main():
    # 1. Load lightweight cross encoder model MiniLM L-6 v2
    print("Loading lightweight cross-encoder model 'cross-encoder/ms-marco-MiniLM-L-6-v2'...")
    # This model is pre-trained on MS MARCO for passage ranking.
    model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

    # 2. Define query and candidate documents with nuanced semantic differences
    query = "Checkout API failing with database connection timeout"
    
    doc_1 = "Runbook: Restart pgbouncer and increase max_client_conn when checkout service logs DB connection timeouts."
    doc_2 = "Runbook: Checkout UI button styling and client-side form validation."
    doc_3 = "Runbook: Redis cache connection timeout on the product catalog service."

    documents = [doc_1, doc_2, doc_3]
    doc_labels = ["Doc 1 (Exact Cause)", "Doc 2 (Distractor)", "Doc 3 (Hard Negative)"]

    # 3. Form query-document pairs
    pairs = [[query, doc] for doc in documents]

    print("\nScoring query-document pairs using the Cross-Encoder...")
    # Measure elapsed inference time
    start_time = time.perf_counter()
    scores = model.predict(pairs)
    end_time = time.perf_counter()
    
    elapsed_time = end_time - start_time

    # 4. Rank documents based on scores in descending order
    ranked_results = sorted(
        zip(doc_labels, documents, scores),
        key=lambda x: x[2],
        reverse=True
    )

    print("\n=========================================")
    print(f"QUERY: '{query}'")
    print(f"Inference Time for 3 pairs: {elapsed_time:.6f} seconds")
    print("=========================================")
    
    for rank, (label, content, score) in enumerate(ranked_results, 1):
        print(f"Rank {rank}: {label}")
        print(f"  Score:   {score:.4f}")
        print(f"  Content: \"{content}\"\n")

    # Mathematical and architectural explanation (in inline comments below)
    """
    ========================================================================================
    BI-ENCODERS VS. CROSS-ENCODERS: MATHEMATICAL AND ARCHITECTURAL ANALYSIS
    ========================================================================================

    1. Architectural Difference:
       
       Bi-Encoder (embeddings model, e.g., 'gemini-embedding-001'):
         - Query (Q) and Document (D) are processed separately (independently) through the network.
         - Output: Two fixed-size vectors, u = E_q(Q) and v = E_d(D).
         - Score calculation is incredibly simple: u . v or cosine(u, v).
         - Pros: u and v can be pre-computed. We can index millions of documents in a vector DB (like pgvector)
           and find matches in milliseconds using highly efficient Approximate Nearest Neighbor (ANN) indexes.
         - Cons: No cross-token interaction is computed during the encoding. The model cannot capture deep token-to-token
           contextual matching (e.g., distinguishing "Checkout API" context from "product catalog service" when "connection timeout" matches).
           
       Cross-Encoder (reranking model):
         - Query (Q) and Document (D) are concatenated and fed TOGETHER into the Transformer:
           Input = [CLS] Query [SEP] Document [EOS]
         - Full self-attention is applied across ALL tokens of both Q and D simultaneously.
         - Every word in the query is actively compared to every word in the document at every layer of the network.
         - Pros: Extremely high accuracy. It can detect that "Redis cache connection timeout on the product catalog service"
           is the WRONG context (hard negative) even though the terms "connection timeout" overlap heavily with the query.
         - Cons: Computationally massive. You cannot pre-compute document representations because the document must be
           processed jointly with the active search query.
           
    2. Computational Latency and Retrieve-Then-Rerank:
       - Since a Cross-Encoder must run the full transformer layers over a concatenated query-document string for *every* candidate,
         scoring a corpus of 100,000 documents at query-time would take minutes, which is unacceptable for real-time applications
         (especially On-call Voice, where turn latency target is < 800ms).
       - Therefore, the industry standard is the **Retrieve-Then-Rerank** paradigm:
         1. **Stage 1 (Retrieval - High Recall, Low Precision)**: Use cheap, fast methods like BM25 and a Bi-Encoder vector search
            to retrieve the Top-K candidates (e.g., K = 20 or 50) out of the entire database.
         2. **Stage 2 (Reranking - High Precision, Low Recall)**: Feed only the Top-K candidates to the Cross-Encoder.
            This leverages the high precision of the Cross-Encoder while keeping total inference time well within acceptable latency budgets.
    """

if __name__ == "__main__":
    main()
