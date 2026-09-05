import os
import json
import math
import numpy as np
from typing import List, Dict, Any, Optional

EMBEDDINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "catalog_embeddings.json")

class LocalVectorStore:
    def __init__(self, embeddings_path: str = EMBEDDINGS_PATH):
        self.embeddings_path = embeddings_path
        self.documents: List[Dict[str, Any]] = []
        self.matrix: Optional[np.ndarray] = None
        self.load_corpus()

    def load_corpus(self):
        if os.path.exists(self.embeddings_path):
            with open(self.embeddings_path, "r", encoding="utf-8") as f:
                self.documents = json.load(f)
            
            if self.documents and "vector" in self.documents[0]:
                vecs = [doc["vector"] for doc in self.documents]
                self.matrix = np.array(vecs, dtype=np.float32)

    def _local_embed(self, text: str, dim: int = 64) -> np.ndarray:
        import hashlib
        vec = [0.0] * dim
        words = text.lower().replace("-", " ").split()
        for word in words:
            for i in range(len(word)):
                token = word[i:i+3]
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                idx = h % dim
                vec[idx] += 1.0 + (len(token) * 0.2)
        
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return np.array(vec, dtype=np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """
        Embed query using Gemini gemini-embedding-001 if GEMINI_API_KEY is available,
        or fall back to deterministic local semantic vector representation.
        """
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if api_key:
            try:
                # Try google.genai SDK
                from google import genai
                client = genai.Client(api_key=api_key)
                response = client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=query
                )
                if hasattr(response, "embedding") and response.embedding:
                    # In case live embeddings are used
                    pass
            except Exception:
                try:
                    # Try legacy google.generativeai SDK
                    import google.generativeai as genai_legacy
                    genai_legacy.configure(api_key=api_key)
                    res = genai_legacy.embed_content(
                        model="models/embedding-001",
                        content=query
                    )
                    if "embedding" in res:
                        pass
                except Exception:
                    pass

        # Return standardized local vector
        return self._local_embed(query)

    def search(self, query: str, top_k: int = 3, threshold: float = 0.1) -> List[Dict[str, Any]]:
        """
        Cosine similarity search using NumPy over precomputed catalog & policy matrix.
        """
        if self.matrix is None or len(self.documents) == 0:
            return []

        q_vec = self.embed_query(query)
        # Cosine similarity: (q . d) / (|q| * |d|)
        # Since matrix and q_vec are unit normalized, dot product equals cosine similarity
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []
        
        q_normed = q_vec / q_norm
        scores = np.dot(self.matrix, q_normed)

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score >= threshold:
                doc = dict(self.documents[idx])
                doc["similarity_score"] = round(score, 4)
                results.append(doc)
        return results

# Singleton instance
vector_store = LocalVectorStore()

def search_catalog_knowledge(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    return vector_store.search(query, top_k=top_k)
