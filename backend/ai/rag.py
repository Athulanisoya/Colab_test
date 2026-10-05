"""Offline dense LSA embeddings in an exact SQLite vector store.

The encoder is classical latent semantic analysis, not a pretrained neural
embedding model. Bilingual topic aliases are explicit, reviewable reference
data. Corpus changes invalidate the store; no hosted provider is contacted.
"""

import json
from pathlib import Path
from datetime import date
import hashlib
import re
import sqlite3
from threading import RLock
import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


CORPUS = Path(__file__).resolve().parents[2] / "data/raw/safety_knowledge.json"
_lock = RLock()
_cached = None
ALIASES = {
    "floodwater": ("inundation", "flooded street", "flooded road", "cross the water", "വെള്ളത്തിലൂടെ", "വെള്ളപ്പൊക്കജലം", "വെള്ളപ്പൊക്കത്തിൽ", "പ്രളയജലം"),
    "drive flooded road": ("വാഹനം", "ഓടിക്ക", "വണ്ടി", "cross flooded", "cross the flooded", "walking through"),
    "food drinking water": ("കുടിക്ക", "കുടിവെള്ള", "ഭക്ഷണം", "eat", "potable", "contaminated"),
    "generator carbon monoxide": ("ജനറേറ്റ", "gas engine", "power generator"),
    "electrical power wires": ("വൈദ്യുത", "വയർ", "കറന്റ്", "switch", "electric shock"),
    "evacuation shelter higher ground": ("ഒഴിപ്പി", "അഭയ", "രക്ഷാകേന്ദ്ര", "evacuate", "where to go"),
    "prepare emergency kit": ("തയ്യാറ", "സജ്ജ", "preparation", "supplies to pack"),
}


def _expanded(text):
    folded = text.casefold()
    return text + " " + " ".join(topic for topic, words in ALIASES.items() if any(word in folded for word in words))


class LocalVectorStore:
    """SQLite stores normalized dense vectors and provenance; cosine is exact."""
    def __init__(self, documents, fingerprint):
        self.documents = documents
        self.fingerprint = fingerprint
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
        texts = [_expanded(doc["title"] + " " + doc["text"] + " " + doc.get("retrieval_aliases", "")) for doc in documents]
        lexical = self.vectorizer.fit_transform(texts)
        self.encoder = TruncatedSVD(n_components=min(32, len(documents)-1, lexical.shape[1]-1), random_state=42)
        embeddings = normalize(self.encoder.fit_transform(lexical)).astype(np.float32)
        self.lexical = lexical
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.execute("CREATE TABLE vectors (id TEXT PRIMARY KEY, dimensions INTEGER NOT NULL, embedding BLOB NOT NULL, document TEXT NOT NULL, corpus_hash TEXT NOT NULL)")
        self.db.executemany("INSERT INTO vectors VALUES (?,?,?,?,?)", [(doc["id"],len(vec),vec.tobytes(),json.dumps(doc,ensure_ascii=False),fingerprint) for doc,vec in zip(documents,embeddings)])
        self.db.commit()
    def query(self, query, limit):
        lexical = self.vectorizer.transform([_expanded(query)])
        if lexical.nnz == 0: return []
        vector = normalize(self.encoder.transform(lexical))[0]
        lexical_scores = cosine_similarity(lexical,self.lexical)[0]
        rows = self.db.execute("SELECT dimensions,embedding,document FROM vectors ORDER BY rowid").fetchall()
        matches = []
        for index,(dimensions,blob,raw) in enumerate(rows):
            dense = np.frombuffer(blob,dtype=np.float32,count=dimensions)
            score = .55 * float(np.dot(vector,dense)) + .45 * float(lexical_scores[index])
            # Dense relatedness cannot establish relevance without a vocabulary anchor.
            if lexical_scores[index] <= .025 or score <= .08: continue
            doc = json.loads(raw)
            age = (date.today()-date.fromisoformat(doc["checked_on"])).days
            if age < 0 or age > 180: continue  # stale/future provenance is not approved
            matches.append(dict(doc,relevance=round(score,3),retrieval_method="dense_lsa_sqlite_exact_cosine",corpus_hash=self.fingerprint,source_age_days=age,source_status="offline_checked_reference"))
        return sorted(matches,key=lambda doc:doc["relevance"],reverse=True)[:limit]


def _index():
    global _cached
    contents = CORPUS.read_bytes()
    fingerprint = hashlib.sha256(contents).hexdigest()
    with _lock:
        if _cached is None or _cached.fingerprint != fingerprint:
            documents = json.loads(contents.decode("utf-8"))
            if len(documents) < 2: raise ValueError("Dense safety corpus requires at least two documents")
            if any(not doc["url"].startswith(("https://www.cdc.gov/","https://imdagrimet.gov.in/")) for doc in documents):
                raise ValueError("Unapproved corpus source")
            if _cached is not None: _cached.db.close()
            _cached = LocalVectorStore(documents,fingerprint)
        return _cached


def retrieve_safety(query: str, limit: int = 3) -> list[dict]:
    with _lock:
        return _index().query(query,min(max(limit,1),3))

