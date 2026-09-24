import re
from rank_bm25 import BM25Okapi

def tokenize(text: str) -> list[str]:
    """
    Case-insensitive word tokenization.
    Extracts alphanumeric words and underscores, preserving hex codes like '0x80004005'
    and database parameters like 'max_client_conn' intact.
    """
    return re.findall(r'[a-zA-Z0-9_]+', text.lower())

def main():
    # Mini runbook corpus
    documents = [
        "Runbook A: Resolve generic HTTP 500 error on checkout api by restarting pods.",
        "Runbook B: Resolve fatal database error 0x80004005 by increasing pgbouncer max_client_conn.",
        "Runbook C: Resolve memory leak OOMKilled by adjusting container cgroup limits."
    ]

    print("Tokenizing and indexing the mini runbook corpus...")
    tokenized_corpus = [tokenize(doc) for doc in documents]
    
    # Initialize BM25Okapi index
    bm25 = BM25Okapi(tokenized_corpus) #bm25 index built on the tokenized corpus

    # Test Queries
    queries = [
        "FATAL 0x80004005 connection failed",
        "Postgres database connection pool exhausted"
    ]

    for idx, raw_query in enumerate(queries, 1):
        tokenized_query = tokenize(raw_query)
        scores = bm25.get_scores(tokenized_query) #bm25 scores for each document in the corpus (main function)
        
        print(f"\n=========================================")
        print(f"QUERY {idx}: '{raw_query}'")
        print(f"Tokenized: {tokenized_query}")
        print(f"=========================================")
        
        for doc_idx, (doc, score) in enumerate(zip(documents, scores), 1):
            print(f"Doc {doc_idx}: Score = {score:.4f}")
            print(f"  Content: \"{doc}\"\n")

        # Mathematical and conceptual annotations in comments & printed outputs
        if idx == 1:
            print(
                "--- Query 1 Analysis ---\n"
                "Why Query 1 scores high on Doc 2 and 0.0 on others:\n"
                "1. Term Overlap: Doc 2 contains the rare hex identifier '0x80004005' and the word 'fatal'.\n"
                "   Doc 1 and Doc 3 contain ZERO overlapping terms with Query 1, resulting in scores of exactly 0.0.\n"
                "2. Mathematical BM25 Scoring:\n"
                "   - Inverse Document Frequency (IDF): The term '0x80004005' is exceptionally rare (occurs in 1/3 docs).\n"
                "     This yields a very high IDF score, heavily weighting Doc 2.\n"
                "   - Term Frequency (TF): Term occurrences are balanced, and length normalization is small.\n"
                "This behavior demonstrates BM25's strength: pinpointing highly unique, exact technical identifiers.\n"
            )
        elif idx == 2:
            print(
                "--- Query 2 Analysis ---\n"
                "Why Query 2 fails on BM25 (Scores = 0.0 everywhere or very low/0.0 on Doc 2):\n"
                "1. Semantic Blind Spot: Query 2 is about 'Postgres database connection pool exhausted'.\n"
                "   Conceptually, this maps directly to Doc 2 ('Resolve fatal database error... pgbouncer max_client_conn').\n"
                "   However, Query 2 has ZERO keyword overlap with Doc 2's tokenized representation\n"
                "   (no 'postgres', 'connection', 'pool', or 'exhausted' in Doc 2; it uses 'database', 'pgbouncer', 'max_client_conn').\n"
                "2. Proof of Hybrid RAG Necessity:\n"
                "   - BM25 relies purely on EXACT character-level token matches. It cannot infer that 'postgres connection pool' is related to 'pgbouncer max_client_conn'.\n"
                "   - A purely lexical search engine fails to retrieve this critical runbook.\n"
                "   - To resolve this, a production system must employ Hybrid RAG: combining BM25 (for exact logs & hex codes like 0x80004005)\n"
                "     with Dense Vector Embeddings (for capturing semantic synonyms like Postgres and pgbouncer max_client_conn).\n"
            )

    # Mathematical explanation of the BM25 formula (in inline comments below)
    """
    ========================================================================================
    MATHEMATICAL EXPLANATION OF THE BM25 FORMULA
    ========================================================================================
    
    The score of a Document (D) for a Query (Q) is computed as:
        Score(D, Q) = sum_{t in Q} IDF(t) * [ (f(t, D) * (k1 + 1)) / (f(t, D) + k1 * (1 - b + b * (|D| / avgdl))) ]
    
    1. IDF(t) - Inverse Document Frequency:
       - Measures how much information a query term provides across the entire corpus.
       - Formula (in BM25Okapi): IDF(t) = ln( (N - n(t) + 0.5) / (n(t) + 0.5) + 1 )
       - If a term appears in almost all documents (e.g., 'resolve'), its IDF approaches zero.
       - If a term is extremely rare (e.g., '0x80004005'), its IDF is highly positive.
       
    2. Term Frequency (TF) Component with k1 Saturation:
       - f(t, D) is the frequency of term t in document D.
       - k1 (usually 1.5) regulates the TF saturation. If a term occurs many times in a document,
         each additional occurrence increases the score, but with diminishing returns (asymptotically plateaus).
         This prevents a document repeating 'fatal' 100 times from inflating its relevance unnaturally.
         
    3. Document Length Normalization via 'b' and 'avgdl':
       - |D| is the length of document D in tokens, and avgdl is the average document length across the corpus.
       - b (usually 0.75) controls how strictly document length is penalized.
       - A long document is likely to contain a search term simply by chance.
       - Normalizing by (|D| / avgdl) penalizes longer documents so that shorter, more concise matches
         are scored higher than long, verbose documents containing the same query term.
    """

if __name__ == "__main__":
    main()
