# embeddings.py
from sentence_transformers import SentenceTransformer
import numpy as np

# Load model once at start
model = SentenceTransformer("all-MiniLM-L6-v2")  # 384-dim embeddings, small & fast

def embed_text(text: str) -> np.ndarray:
    """Convert a string into an embedding vector using SentenceTransformers."""
    return model.encode([text], convert_to_numpy=True)[0]

def cosine_sim(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    vec1 = np.array(vec1)
    vec2 = np.array(vec2)
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

def extract_text_from_jira_description(description: dict) -> str:
    """Flatten Jira description content into plain text."""
    if not description or "content" not in description:
        return ""
    parts = []
    for block in description.get("content", []):
        if "content" in block:
            for inner in block["content"]:
                if inner.get("type") == "text":
                    parts.append(inner.get("text", ""))
    return " ".join(parts).strip()
