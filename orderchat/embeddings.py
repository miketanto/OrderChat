from __future__ import annotations
from typing import List, Tuple
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer

# Lightweight embedding + simple classifier to gate LLM usage

class IntentGate:
    def __init__(self):
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        # Simple logistic regression on pooled embeddings
        self.clf = Pipeline([
            ('scaler', StandardScaler(with_mean=False)),
            ('logreg', LogisticRegression(max_iter=1000))
        ])
        self.trained = False

    def embed(self, texts: List[str]) -> np.ndarray:
        return np.array(self.model.encode(texts, normalize_embeddings=True))

    def fit(self, X_texts: List[str], y: List[int]):
        X = self.embed(X_texts)
        self.clf.fit(X, y)
        self.trained = True

    def predict_proba(self, texts: List[str]) -> np.ndarray:
        X = self.embed(texts)
        if not self.trained:
            # Fallback: similarity to prototypical start words
            protos = self.embed(["start order", "order food", "see menu", "confirm order"])  # 4xD
            sims = cosine_similarity(X, protos).max(axis=1)
            # Return 2-class proba-like array
            probs = np.vstack([1 - sims, sims]).T
            return probs
        return self.clf.predict_proba(X)

    def should_gate_llm(self, text: str, threshold: float = 0.6) -> bool:
        # True means: send to LLM
        proba = self.predict_proba([text])[0][1]
        return proba < threshold  # if not intent-like, avoid LLM
