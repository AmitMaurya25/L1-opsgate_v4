"""Hybrid retrieval over the synthetic KB: BM25 (keyword) + TF-IDF char-ngram vectors, fused with RRF.
RRF only RANKS; a separate relevance gate (idf-weighted query-term coverage) decides whether evidence is usable.
Chunks containing instruction-like text are dropped (retrieved content is untrusted data)."""
import json, math, re
from pathlib import Path
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import config as C, guard

STOP = set('a an the is are to of and or in on my i me it for with can how do does what this that be not but get have has was were at by from when why you your please help am so there very about'.split())

def stem(w):
    for suf in ('ing', 'ed'):
        if w.endswith(suf) and len(w) > len(suf) + 3: return w[:-len(suf)]
    return w[:-1] if w.endswith('s') and not w.endswith('ss') and len(w) > 3 else w

def toks(s):
    return [stem(w) for w in re.findall(r'[a-z0-9]+', s.lower()) if w not in STOP and (len(w) > 1)]

def label(h): return f"{h['article_id']} §{h['section']}"

class KB:
    def __init__(self, path=None):
        raw = json.loads(Path(path or Path(__file__).parent / 'data' / 'kb.json').read_text())
        self.chunks = [c for c in raw if not guard.INJ.search(c['text'])]
        self.dropped = len(raw) - len(self.chunks)
        docs = [f"{c['title']} {c['text']} {' '.join(c['tags'])}" for c in self.chunks]
        self.dt = [toks(d) for d in docs]; self.N = len(docs)
        self.df = {}
        for d in self.dt:
            for t in set(d): self.df[t] = self.df.get(t, 0) + 1
        self.avg = sum(map(len, self.dt)) / self.N
        self.vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 5), sublinear_tf=True)
        self.M = self.vec.fit_transform(docs)
        self.ids = {c['chunk_id'] for c in self.chunks}

    def idf(self, t): return math.log(1 + (self.N + 1) / (self.df.get(t, 0) + .5))

    def bm25(self, q, i, k1=1.5, b=.75):
        d = self.dt[i]; s = 0.0
        for t in set(q):
            f = d.count(t)
            if f: s += self.idf(t) * f * (k1 + 1) / (f + k1 * (1 - b + b * len(d) / self.avg))
        return s

    def search(self, query, k=5):
        q = toks(query)
        if not q: return []
        bm = np.array([self.bm25(q, i) for i in range(self.N)])
        cos = (self.M @ self.vec.transform([query]).T).toarray().ravel()
        def ranks(sc): return {int(i): r for r, i in enumerate([i for i in np.argsort(-sc)[:20] if sc[i] > 0], 1)}
        rb, rv = ranks(bm), ranks(cos)
        tot = sum(self.idf(t) for t in set(q)); out = []
        for i in set(rb) | set(rv):
            rrf = sum(1 / (60 + r[i]) for r in (rb, rv) if i in r)
            hit = [t for t in set(q) if t in set(self.dt[i])]
            out.append({**self.chunks[i], 'rrf': round(rrf, 4), 'relevance': round(sum(self.idf(t) for t in hit) / tot, 3), 'matched': hit})
        return sorted(out, key=lambda x: -x['rrf'])[:k]

    def evidence(self, query, k=3):
        return [h for h in self.search(query, 5) if h['matched'] and h['relevance'] >= C.REL_MIN][:k]

_KB = None
def get_kb():
    global _KB
    if _KB is None: _KB = KB()
    return _KB
