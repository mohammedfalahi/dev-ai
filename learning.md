# Automated Learning Board

## [2026-09-23] Milestone 1: Embeddings Verification (Spike)

### 1. What was built & which files were modified
- Created directory `spikes/` and implemented the first spike script: `spikes/01_embeddings.py`.
- Verified embedding generation using the new Google GenAI SDK (`google-genai`) and computed cosine similarities using `numpy`.
- Files modified/created:
  - `spikes/01_embeddings.py` (Created)
  - `learning.md` (Modified/Created)

### 2. The Core Concept & Math/Logic behind it (Plain English)
- **Concept**: Semantic similarity allows the On-call Voice system to group and retrieve logs based on their underlying *meaning* rather than exact keyword matches.
- **Math/Logic**:
  - We fetched high-dimensional vectors (768 dimensions) representing the meaning of three sentences.
  - **Dot Product**: Measures the raw alignment of two vectors in direction. It sums the element-by-element multiplication of the vector components.
  - **Norm (Magnitude)**: The straight-line length of each vector.
  - **Cosine Similarity**: Normalizes the dot product by dividing it by the product of the magnitudes of the two vectors. This isolates the angular separation:
    $$\text{Cosine Similarity} = \cos(\theta) = \frac{\mathbf{u} \cdot \mathbf{v}}{\|\mathbf{u}\| \|\mathbf{v}\|}$$
    A score closer to $1$ ($\theta \to 0^\circ$) signifies that the vectors point in almost the identical direction (high semantic alignment, e.g., database connection issues), whereas a score closer to $0$ ($\theta \to 90^\circ$) signifies orthogonal directions (different semantic contexts, e.g., database issues vs. front-end CSS misalignment).

### 3. Interview Defense
- **Probable Interview Questions**:
  1. *Why calculate cosine similarity manually using NumPy instead of relying on a library or vector database helper?*
     - **Answer**: For a minimal, isolated spike, calculating it from scratch using NumPy ensures maximum performance, zero overhead, and eliminates dependencies on heavy vector storage libraries during verification. It also verifies our mathematical understanding directly.
  2. *What is the mathematical difference between Dot Product and Cosine Similarity, and when should each be used?*
     - **Answer**: The dot product includes both vector direction and length/magnitude. If your embeddings are not unit-normalized, long texts or highly frequent terms might skew the raw dot product. Cosine similarity divides by the vector norms, isolating pure angular direction and scaling the output to the $[-1, 1]$ range. When embeddings are pre-normalized to unit length (magnitude of 1), the dot product is mathematically equivalent to cosine similarity and is computationally cheaper to compute.
- **Architecture Choice (Why this over alternatives?)**:
  - We chose to run this as an isolated script inside `spikes/` following the "Smallest Unit of Isolation" principle. This keeps production application and contracts boundaries completely clean while quickly proving our SDK connection, dependencies, and math.
- **Failure Modes Prevented**:
  - **SDK & Dependency Mismatch**: Proves `google-genai` and `numpy` can be loaded and executed cleanly in the active virtual environment before writing complex adapter code.
  - **Zero-Vector / Division-by-Zero Protection**: Built-in guard inside the cosine similarity function prevents runtime `NaN` or crashes if an empty/zero vector is somehow returned or passed.

---

## [2026-09-23] Milestone 2: Lexical Retrieval Verification (BM25 Spike)

### 1. What was built & which files were modified
- Created the second spike script: `spikes/02_bm25.py`.
- Evaluated sparse lexical search using the `rank-bm25` library.
- Tested and scored a mini corpus of 3 runbooks against two distinct incident queries.
- Files modified/created:
  - `spikes/02_bm25.py` (Created)
  - `learning.md` (Modified)

### 2. The Core Concept & Math/Logic behind it (Plain English)
- **Concept**: BM25 (Best Matching 25) is a sparse lexical retrieval algorithm that ranks documents based on the exact occurrences of query terms, prioritizing rare, highly unique words (like error codes or hex signatures) over common words.
- **Math/Logic**:
  - **Inverse Document Frequency (IDF)**: Scores the scarcity of a word. A word like "0x80004005" appearing in only 1 of 3 documents gets a high positive score, whereas a word like "resolve" appearing in all documents gets a score near $0.0$.
  - **Term Frequency (TF)**: Scores the density of query words in the document, but with a logarithmic saturation curve regulated by the parameter $k_1$. This means a document repeating a word 10 times doesn't score 10 times higher than a document repeating it twice.
  - **Document Length Normalization**: Regulated by the parameter $b$. Longer documents are penalized because they have a higher probability of containing terms purely by chance. Short documents containing exact hits get boosted.

### 3. Interview Defense
- **Probable Interview Questions**:
  1. *Why did Query 2 ("Postgres database connection pool exhausted") fail to score higher than 0.52 on Doc 2 in BM25, despite being a direct semantic match?*
     - **Answer**: BM25 is strictly character-bound; it depends entirely on exact token overlap. While the concept (Postgres, connection pools) matches Doc 2 (pgbouncer, max_client_conn), the only exact token matched was the generic word "database" (giving a weak score of 0.5243). The specific keywords ("postgres", "connection", "pool", "exhausted") had zero overlap. This demonstrates the critical "vocabulary mismatch" problem in lexical search.
  2. *How does this spike prove the necessity of a Hybrid RAG architecture (as specified in ADR-005)?*
     - **Answer**:
       - **Pure Lexical Search (BM25)** is superb at locating exact error codes (`0x80004005`), specific log structures, and precise identifiers that vector models might dilute.
       - **Pure Vector Search (Dense)** is superb at capturing synonymy and abstract concepts (e.g., mapping "postgres pool exhausted" to "pgbouncer max_client_conn") but can miss exact unique hex codes due to high-dimensional smoothing.
       - **Hybrid RAG** combines both lexical (BM25) and semantic (Vector) search ranks using Reciprocal Rank Fusion (RRF) and a reranker, resolving the weaknesses of each to guarantee bulletproof, highly reliable runbook retrieval under stress.
- **Architecture Choice (Why this over alternatives?)**:
  - We used `rank-bm25`'s lightweight `BM25Okapi` in Python for local verification. This isolates retrieval-logic prototyping from complex SQL engines (like Postgres' full-text search) while providing the exact same math, laying a clean foundation for subsequent migrations.
- **Failure Modes Prevented**:
  - **Vocabulary Mismatch / Missed Runbooks**: Empirically proved that an engineer looking for "Postgres connection pools" might miss the "pgbouncer max_client_conn" runbook if we only used lexical search, preventing an outage escalation failure.
  - **Diluted Identifiers**: Proved that BM25 guarantees a 100% exact match on unique hex codes like `0x80004005`, preventing dense vectors from diluting high-importance error signatures during RAG retrieval.

---

## [2026-09-23] Milestone 3: Cross-Encoder Reranking Verification (Spike)

### 1. What was built & which files were modified
- Created the third spike script: `spikes/03_reranker.py`.
- Verified deep semantic reranking using `sentence-transformers` and the `"cross-encoder/ms-marco-MiniLM-L-6-v2"` model.
- Evaluated ranking accuracy and measured execution latency over three document candidates containing high-overlap "hard negatives".
- Files modified/created:
  - `spikes/03_reranker.py` (Created)
  - `learning.md` (Modified)

### 2. The Core Concept & Math/Logic behind it (Plain English)
- **Concept**: Cross-Encoders solve the lack of context matching in Bi-Encoders by feeding the Query and Document *jointly* into a single Transformer model.
- **Math/Logic**:
  - **Full Joint Self-Attention**: Rather than projecting the Query (Q) and Document (D) into independent vectors and calculating a simple dot product, a Cross-Encoder concatenates them: `[CLS] Query [SEP] Document [EOS]`.
  - The Transformer then runs self-attention over *both* sets of tokens at every single layer of the network. This allows every single token in the query to attend to every single token in the document, capturing deep contextual relationships.
  - This allows the model to realize that while "Redis cache connection timeout on the product catalog service" shares semantic concepts ("connection timeout") with "Checkout API failing with database connection timeout", the specific system context (Redis/product catalog vs Database/Checkout) is incorrect, yielding a much lower score (`-4.5385` vs `-0.4039`).

### 3. Interview Defense
- **Probable Interview Questions**:
  1. *What is the fundamental architectural and mathematical difference between Bi-Encoders and Cross-Encoders?*
     - **Answer**: 
       - **Bi-Encoders** compute embeddings for queries and documents *independently*. The vectors are static and scored using lightweight cosine similarity or dot-products. This allows pre-computation of document embeddings and lightning-fast sub-millisecond retrieval on millions of documents using ANN indexes.
       - **Cross-Encoders** concatenate query and document together as a single input sequence. Full joint self-attention is applied across all tokens, enabling deep token-to-token cross-correlation. This yields much higher relevance precision but requires running the full model on every query-document pair at query-time, preventing pre-computation.
  2. *Why can't we use a Cross-Encoder to rank our entire runbook corpus directly, and what architecture handles this?*
     - **Answer**: Joint self-attention over thousands or millions of documents at runtime is too computationally massive and slow, violating our strict sub-second conversational latency budget (target < 800ms). Instead, we use a **Retrieve-and-Rerank** (two-stage) pipeline:
       - **Stage 1 (Retrieval)**: A fast, cheap Bi-Encoder (vector search) or BM25 lexical search filters the database to a tiny subset of candidate documents (Top-K, e.g., K = 20 or 50).
       - **Stage 2 (Reranking)**: The precise Cross-Encoder model scores and re-orders only these Top-K candidates, ensuring highly accurate retrieval with extremely low, deterministic latency.
- **Architecture Choice (Why this over alternatives?)**:
  - We chose `cross-encoder/ms-marco-MiniLM-L-6-v2` because it is extremely lightweight (90MB), runs super fast on CPU, and is pre-trained on MS MARCO for passage ranking. This allows local validation of reranking logic without setting up paid external third-party APIs (like Cohere or Voyage), while implementing the exact same core Transformer logic.
- **Failure Modes Prevented**:
  - **Inaccurate Guidance (Hard Negatives)**: Prevents the system from surfacing a product catalog Redis runbook to an engineer troubleshooting a database checkout failure, which could lead to incorrect mitigation procedures being executed.
  - **Conversational Latency Outages**: Prevents the system from stalling or crashing by restricting expensive joint attention operations strictly to a pre-filtered Top-K set.

---

## [2026-09-23] Milestone 4: Embedding Model Migration to gemini-embedding-001

### 1. What was built & which files were modified
- Upgraded the dense embedding model across the workspace from `text-embedding-004` to `gemini-embedding-001`.
- Configured Matryoshka Representation Learning (MRL) truncation to force `output_dimensionality=768` on `gemini-embedding-001`.
- Aligned persistence schema definitions inside `.context/architecture.md` to reflect `embedding vector(768)` (reduced from `1024` dimensions).
- Files modified/created:
  - `spikes/01_embeddings.py` (Modified)
  - `spikes/03_reranker.py` (Modified architectural comments)
  - `.context/library-docs.md` (Modified)
  - `.context/architecture.md` (Modified SQL Schema)
  - `learning.md` (Modified)

### 2. The Core Concept & Math/Logic behind it (Plain English)
- **Active Lifecycle vs. Retiring Endpoints**: Upgrading to `gemini-embedding-001` ensures we are using an active, production-grade model with ongoing support, larger context window capacity, and optimal latency.
- **Matryoshka Representation Learning (MRL)**: 
  - Standard deep learning embeddings are fixed-dimensional. `gemini-embedding-001` has a default native output size of **3072** dimensions.
  - MRL trains the model such that semantic information is nested sequentially—the first coordinates (dimensions) contain the vast majority of the information density, behaving like nested Russian dolls (Matryoshkas).
  - By passing `output_dimensionality=768` via the SDK config, the API truncates the output vectors to 768 dimensions directly at the model head. This preserves almost all the semantic accuracy of the larger 3072-dimensional embedding while saving **75% of vector storage and indexing memory** in `pgvector`.

### 3. Interview Defense
- **Probable Interview Questions**:
  1. *How does Matryoshka Representation Learning preserve similarity performance when we discard 75% of the vector dimensions (from 3072 down to 768)?*
     - **Answer**: MRL explicitly constructs the loss function during model training to enforce that sub-vectors (prefixes) are themselves highly expressive and optimized representations. Our spike verified this: cosine similarity contrast remains extremely high, with `0.6740` for DB connection issues and `0.4531` for DB vs CSS issues, proving the 768-dimensional slice is highly discriminative.
  2. *Why is it critical in production systems to proactively migrate from retiring endpoints like text-embedding-004 to active models like gemini-embedding-001?*
     - **Answer**: AI platform providers actively retire legacy endpoints. Using outdated models risks deprecation outages, receives slower security patches, fails to leverage newer hardware acceleration, and leaves us locked out of larger context windows. Migrating early, and encapsulating the model parameter under repository-owned adapters, prevents future production downtime.
- **Architecture Choice (Why this over alternatives?)**:
  - We configured MRL on the model side rather than doing client-side vector slicing. This decreases network transfer bandwidth (sending 768 floats instead of 3072 floats over the network), reduces Postgres pgvector indexing overhead, and simplifies our persistence layer.
- **Failure Modes Prevented**:
  - **Vector Dimension Mismatch**: Aligning `.context/architecture.md` strictly to `vector(768)` prevents schema-to-application mismatches when initializing tables in our production environment.
  - **Out-of-Memory / High Storage Costs**: Discarding unnecessary dimensions prevents massive index bloat in `pgvector` memory spaces, preserving sub-second search latencies under heavy load.

---

## [2026-09-23] Milestone 5: Reciprocal Rank Fusion (RRF) Hybrid Search

### 1. What was built & which files were modified
- Created the fourth spike script: `spikes/04_rrf.py`.
- Independently tokenized, indexed, and scored a 5-document incident runbook corpus against a multi-concept query using `BM25Okapi` (Lexical Channel) and `gemini-embedding-001` (Semantic Channel).
- Implemented the Reciprocal Rank Fusion (RRF) algorithm from scratch using NumPy and verified the unified hybrid rank list output.
- Files modified/created:
  - `spikes/04_rrf.py` (Created)
  - `learning.md` (Modified)

### 2. The Core Concept & Math/Logic behind it (Plain English)
- **Concept**: RRF merges rank-ordered lists from multiple search algorithms into a single unified ranked list, combining the strengths of exact keyword matches and abstract semantic understanding.
- **Math/Logic**:
  - **Scale Mismatch**: BM25 yields unbounded positive floats (ranging from $0.0$ to $10+$ based on term rarity). Cosine similarity is strictly bounded between $[-1, 1]$ (often clustered between $0.3$ and $0.8$ for positive candidates). Summing them directly is mathematically nonsensical.
  - **Rank-Based Score Formulation**: RRF solves this by ignoring raw score values entirely, looking only at the *rank position* (1st, 2nd, 3rd, etc.) of a document in each list:
    $$\text{RRF\_Score}(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
  - **Smoothing Constant ($k = 60$)**: Prevents outliers that score 1st in only one list from overwhelming consistently good performers. For example, if $k = 0$, a document placing 1st in lexical and 50th in semantic gets a massive score of $1.02$, while a document placing 2nd in both lists only gets $1.00$. With $k = 60$, the hyperbola flattens: the 1st/50th document gets `0.02548`, whereas the consistent 2nd/2nd document gets `0.03226`, correctly winning.

### 3. Interview Defense
- **Probable Interview Questions**:
  1. *Why does our RRF hybrid search yield exactly identical scores for Doc 2 and Doc 4 (both ranking 1st in the final list with a score of 0.032522)?*
     - **Answer**: Doc 2 was ranked 1st by BM25 (matching semantic synonyms via database/pool terms) and 2nd by Dense vectors. Doc 4 was ranked 2nd by BM25 (exact match of hex code `0x80004005`) and 1st by Dense vectors. Under RRF, their scores are:
       - Doc 2: $1 / (60 + 1) + 1 / (60 + 2) = 1/61 + 1/62 = 0.032522$
       - Doc 4: $1 / (60 + 2) + 1 / (60 + 1) = 1/62 + 1/61 = 0.032522$
       Their symmetrical performance highlights that RRF perfectly balances lexical precision (hex code) and semantic recall (database pool exhaustion).
  2. *What is the advantage of RRF over simple weighted score combinations (e.g., alpha * Lexical_Score + (1-alpha) * Semantic_Score)?*
     - **Answer**: Weighted score combinations require precise normalization (like Min-Max or Standard scaling), which are highly volatile and change every time the document database size grows or a new query is executed. RRF is completely scale-free and non-parametric with respect to score distributions; it relies entirely on ordinal rankings, making it extremely robust and mathematically stable across any corpus size or query type.
- **Architecture Choice (Why this over alternatives?)**:
  - We implemented RRF natively in Python to isolate and mathematically test the ranking behavior. This algorithm forms the direct software specification for our PostgreSQL full-text search and `pgvector` hybrid retrieval engine in the `apps/investigator` application boundary.
- **Failure Modes Prevented**:
  - **Vocabulary Mismatch Escapes**: Prevents critical runbooks (like Doc 2) from being completely missed by BM25 when the query uses synonyms (like "postgres") not found in the runbook content.
  - **Diluted Critical Technical Identifiers**: Prevents dense embeddings from diluting highly specific identifiers (like hex `0x80004005` in Doc 4) under deep vector averaging, ensuring that the correct exact-match runbook remains at the absolute top of the incident brief list.

---

## [2026-09-24] Milestone 6: Datastore Infrastructure & Hybrid Schema Initialization (Track 2)

### 1. What was built & which files were modified
- Initialized PostgreSQL 16 container with `pgvector` extension via Docker Compose (`docker-compose.yml`).
- Added `psycopg` database driver to project dependencies via `uv`.
- Authored initial SQL schema migration `infra/migrations/001_init_schema.sql` covering:
  - `vector` extension enablement (`CREATE EXTENSION IF NOT EXISTS vector`).
  - Core relational and incident management tables: `incidents`, `alerts`, `runbooks`, `approvals`, `audit_log`.
  - Dual representation for runbook search in `runbook_chunks`: `embedding vector(768)` for dense semantic vector search alongside `fts tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED` for sparse lexical retrieval.
  - Search indexes: Generalized Inverted Index (GIN) on `fts` and Hierarchical Navigable Small World (HNSW) index on `embedding` using cosine distance ops (`vector_cosine_ops`).
- Created and executed automated database migration and schema verification runner `infra/run_migrations.py`.
- Files modified/created:
  - `docker-compose.yml` (Created)
  - `infra/migrations/001_init_schema.sql` (Created)
  - `infra/run_migrations.py` (Created)
  - `pyproject.toml` & `uv.lock` (Modified with `psycopg[binary]`)
  - `learning.md` (Modified)

### 2. The Core Concept & Math/Logic behind it (Plain English)
- **Concept: Dual Representation Strategy in a Single Datastore**:
  - Rather than provisioning and synchronizing two disconnected clusters (e.g., Elasticsearch for text and Pinecone for embeddings), we maintain a **unified dual representation** within a single PostgreSQL table (`runbook_chunks`).
  - **Dense Channel (`embedding vector(768)`)**: Captures high-dimensional conceptual relationships, synonyms, and generalized troubleshooting intent generated via `gemini-embedding-001` with MRL dimensionality reduction.
  - **Sparse Channel (`fts tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED`)**: Captures exact technical lexemes, error strings, flags, and system codes using PostgreSQL's native document tokenization, dictionary normalization, and stemmer. By defining it as a `GENERATED ALWAYS ... STORED` column, PostgreSQL guarantees write-time consistency: the `tsvector` is deterministically computed and persisted upon every insert or update, completely eliminating cache/state drift between raw text and searchable tokens.
- **Math/Logic: GIN vs. HNSW Indexing Mechanics**:
  - **GIN (Generalized Inverted Index) for Sparse FTS**: Inverts the relation from document $\to$ words into word $\to$ posting list of document pointers. Searching for a term runs in $O(\log N)$ tree traversal to locate the term dictionary entry, followed by set intersections across posting lists for multi-term queries.
  - **HNSW (Hierarchical Navigable Small World) for Dense Vector Search**: Builds a multi-layer graph where lower layers have high vertex density (local clustering) and upper layers have long-range skip edges. Nearest neighbor search starts at the top sparse layer with greedy routing and descends layer by layer, achieving logarithmic search complexity ($O(\log N)$) without needing to exhaustively evaluate $O(N)$ high-dimensional floating-point vector distances.

### 3. Interview Defense
- **Probable Interview Questions**:
  1. *What is the indexing and memory overhead of pgvector HNSW compared to IVFFlat, and why did we choose HNSW for our incident investigation hot-path?*
     - **Answer**:
       - **IVFFlat (Inverted File Flat)** partitions vector space into Voronoi cells via k-means clustering. It requires an initial training step, has low build memory, and smaller disk footprint, but query recall drops significantly under real-time inserts unless lists are frequently rebuilt. Furthermore, achieving high recall requires probing many lists (`ivfflat.probes`), which causes erratic query latencies under load.
       - **HNSW** maintains a multi-layer proximity graph with parameters `m` (maximum connections per node) and `ef_construction` (dynamic candidate list size during construction). It uses more RAM (roughly $1.5\times$ to $2\times$ raw vector size to store graph edges and pointers) and has higher build times. However, HNSW requires **no training phase**, supports seamless real-time incremental inserts without degradation, and delivers ultra-fast, deterministic sub-10ms query latencies with $>95\%$ recall. For safety-critical incident response where an on-call engineer needs immediate runbook context on a voice call, deterministic retrieval latency completely outweighs the additional memory overhead.
  2. *How does the dual representation (vector(768) + generated tsvector) impact write amplification, disk storage efficiency, and vacuum performance compared to an external vector database?*
     - **Answer**:
       - Storing both `vector(768)` (approx. 3 KB per chunk for 768 32-bit floats) and `tsvector` alongside text increases row width and WAL write amplification during chunk ingestion.
       - However, this cost is vastly overshadowed by operational simplicity and transaction guarantees. With an external vector DB (e.g. Pinecone/Qdrant), keeping relational runbook metadata, access policies, and vectors in sync requires distributed dual-writes, outbox patterns, or CDC pipelines that risk silent desynchronization or orphaned embeddings.
       - In PostgreSQL with `pgvector`, transactions are ACID-compliant: a runbook chunk insert, its full-text generated vector, its dense vector, and its relational metadata commit or rollback together. For storage efficiency, pairing Matryoshka dimensionality reduction (truncating from 3072 to 768 dimensions) already saves 75% of raw vector footprint, more than offsetting the incremental cost of the `tsvector` column and GIN index.
- **Architecture Choice (Why this over alternatives?)**:
  - We chose unified PostgreSQL 16 with `pgvector` rather than splitting our stack across dedicated search engines (OpenSearch) and vector databases. This single-engine architecture eliminates network hops between disparate datastores, enables atomic transactions, simplifies local testing via Docker Compose, and allows running hybrid RRF queries directly in SQL.
- **Failure Modes Prevented**:
  - **Split-Brain State & Orphaned Chunks**: Eliminates the catastrophic failure mode where an updated or deleted runbook in the primary database remains active in an external vector index, preventing out-of-date or dangerous operational procedures from being served during live incidents.
  - **Text-to-FTS Cache Desynchronization**: Utilizing a PostgreSQL `GENERATED ALWAYS ... STORED` column guarantees that the lexical search index can never diverge from the actual chunk content.

