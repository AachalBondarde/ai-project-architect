"""Hugging Face RAG: sentence-transformers embeddings, hashing fallback if offline."""
import os
import re

import numpy as np
KB = [
 ("architecture","Modular monolith suits teams under 10 and under 50k users; microservices need independent scaling and ops maturity."),
 ("architecture","Event-driven architecture with a queue decouples notifications and slow AI tasks from request paths."),
 ("database","PostgreSQL fits relational data with transactions; MongoDB fits flexible documents; Redis for caching and sessions."),
 ("security","Apply OWASP Top 10: JWT with short expiry, RBAC, input validation, rate limiting, secrets in env or vault, TLS."),
 ("scalability","Cache hot reads in Redis, add a CDN for static assets, scale stateless API pods horizontally behind a load balancer."),
 ("deployment","Docker plus docker-compose for dev; managed container platform with CI/CD and health checks for production."),
 ("technology","React with FastAPI is a productive pairing; FastAPI gives async IO, OpenAPI docs and Pydantic validation."),
]
_model=None
_embedding_backend="huggingface"
def _embed(texts):
    global _model, _embedding_backend
    try:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model=SentenceTransformer(
                os.getenv("HUGGINGFACE_EMBEDDING_MODEL", os.getenv("HUGGINGFACE_MODEL", "sentence-transformers/all-MiniLM-L6-v2")),
                token=os.getenv("HUGGINGFACE_API_KEY") or None,
            )
        return np.array(_model.encode(texts,normalize_embeddings=True))
    except Exception:
        _embedding_backend="offline-hashing-fallback"
        out=np.zeros((len(texts),256))
        for i,t in enumerate(texts):
            for w in re.findall(r"\w+",t.lower()): out[i,hash(w)%256]+=1
        return out/(np.linalg.norm(out,axis=1,keepdims=True)+1e-9)
def retrieve(query,k=3):
    d=_embed([t for _,t in KB]); q=_embed([query])[0]
    idx=np.argsort(-(d@q))[:k]
    return [KB[i][1] for i in idx]

def embedding_backend():
    return _embedding_backend
