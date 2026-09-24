import numpy as np
from google import genai
from google.genai import types

def compute_cosine_similarity(vec_x: np.ndarray, vec_y: np.ndarray) -> float:
    """
    Computes the cosine similarity between two vectors.
    
    Mathematical explanation:
    Cosine similarity is defined as:
        similarity = (X . Y) / (||X|| * ||Y||)
    
    1. The Dot Product (X . Y):
       - Calculated as the sum of the element-wise products: sum(x_i * y_i).
       - Geometrically, it represents the projection of Vector X onto Vector Y multiplied by the magnitude of Y.
       - It is a measure of directional alignment: it is positive if they point in a similar general direction,
         zero if they are orthogonal, and negative if they point in opposite directions.
         
    2. Vector Angle (theta) and Norms (||X||, ||Y||):
       - The magnitude (norm) of a vector represents its length: sqrt(sum(x_i^2)).
       - Dividing the dot product by the product of the norms isolates the angular direction from the magnitude,
         yielding cos(theta), where theta is the angle between the two vectors in the high-dimensional space.
       - A cosine similarity of 1 (theta = 0°) means the vectors are perfectly aligned (pointing in the identical direction),
         representing identical semantic meaning.
       - A cosine similarity of 0 (theta = 90°) means the vectors are orthogonal (independent/perpendicular),
         representing completely unrelated concepts.
    """
    dot_product = np.dot(vec_x, vec_y)
    norm_x = np.linalg.norm(vec_x)
    norm_y = np.linalg.norm(vec_y)
    
    if norm_x == 0 or norm_y == 0:
        return 0.0
        
    return float(dot_product / (norm_x * norm_y))

def main():
    # Sentences to embed
    sentence_a = "FATAL: remaining connection slots are reserved for non-replication superuser connections"
    sentence_b = "Database connection pool exhausted on postgres checkout cluster"
    sentence_c = "CSS layout misalignment on the checkout pay button"

    print("Initializing Google GenAI Client...")
    client = genai.Client()

    print("Generating embeddings using model 'gemini-embedding-001' with MRL output_dimensionality=768...")
    # Request embeddings in batch for optimal efficiency
    response = client.models.embed_content(
        model='gemini-embedding-001',
        contents=[sentence_a, sentence_b, sentence_c],
        config=types.EmbedContentConfig(
            output_dimensionality=768
        )
    )

    # Convert embedding values to numpy arrays
    vector_a = np.array(response.embeddings[0].values)
    vector_b = np.array(response.embeddings[1].values)
    vector_c = np.array(response.embeddings[2].values)

    # 1. Print Embedding vector dimension
    dimension = vector_a.shape[0]
    print(f"\nEmbedding Vector Dimension: {dimension}")

    # 2. Print the first 5 float values of Vector A
    print(f"First 5 float values of Vector A (Database Slot Exhaustion): {vector_a[:5].tolist()}")

    # 3. Compute and print cosine similarity for (A, B) and (A, C)
    sim_a_b = compute_cosine_similarity(vector_a, vector_b)
    sim_a_c = compute_cosine_similarity(vector_a, vector_c)

    print(f"\nCosine Similarity between A & B (Both DB Connection Issues): {sim_a_b:.4f}")
    print(f"Cosine Similarity between A & C (DB issue vs. CSS layout issue): {sim_a_c:.4f}")

if __name__ == "__main__":
    main()
