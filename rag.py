"""초경량 로컬 RAG 검색 엔진 (Node판 rag.js 포팅).
- data/kb/*.md 를 "## 소제목" 단위 청크로 분해
- TF-IDF 유사 스코어링으로 질의어와 가장 관련 있는 청크를 검색
- OPENAI_API_KEY가 있으면 임베딩 기반 검색으로 자동 업그레이드, 실패 시 로컬 키워드 검색으로 폴백
"""
import math
import re
from pathlib import Path

import llm_client as llm

KB_DIR = Path(__file__).parent / "data" / "kb"
_NON_WORD_RE = re.compile(r"[^\w]", re.UNICODE)


def char_bigrams(segment: str) -> list[str]:
    clean = re.sub(r"[^\w]", "", segment, flags=re.UNICODE)
    if len(clean) == 0:
        return []
    if len(clean) == 1:
        return [clean]
    return [clean[i:i + 2] for i in range(len(clean) - 1)]


def tokenize(text: str) -> list[str]:
    segments = [s for s in (text or "").lower().split() if s]
    grams = []
    for seg in segments:
        grams.extend(char_bigrams(seg))
    return grams


def load_chunks() -> list[dict]:
    chunks = []
    for path in sorted(KB_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        doc_title_match = re.search(r"^#\s+(.+)$", raw, re.MULTILINE)
        doc_title = doc_title_match.group(1) if doc_title_match else path.name
        sections = re.split(r"\n(?=##\s)", raw)
        for sec in sections:
            title_match = re.search(r"^##\s+(.+)$", sec, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else doc_title
            text = re.sub(r"^#.*$", "", sec, count=1, flags=re.MULTILINE).strip()
            if not text:
                continue
            chunks.append({
                "id": f"{path.name}#{title}",
                "source": path.name,
                "docTitle": doc_title,
                "title": title,
                "text": text,
                "tokens": tokenize(title + " " + text),
            })
    return chunks


CHUNKS = load_chunks()


def build_idf(chunks: list[dict]) -> dict:
    df: dict[str, int] = {}
    for c in chunks:
        for t in set(c["tokens"]):
            df[t] = df.get(t, 0) + 1
    n = len(chunks)
    return {t: math.log((n + 1) / (d + 0.5)) + 1 for t, d in df.items()}


IDF = build_idf(CHUNKS)
TOTAL_CHUNKS = len(CHUNKS)


def is_informative(token: str) -> bool:
    idf = IDF.get(token)
    if idf is None:
        return False
    threshold = math.log((TOTAL_CHUNKS + 1) / (TOTAL_CHUNKS * 0.5 + 0.5)) + 1
    return idf > threshold


def score_chunk(query_tokens: list[str], chunk: dict) -> float:
    tf: dict[str, int] = {}
    for t in chunk["tokens"]:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    n_tokens = len(chunk["tokens"]) or 1
    for qt in query_tokens:
        if not is_informative(qt):
            continue
        if qt in tf:
            score += (tf[qt] / n_tokens) * IDF.get(qt, 1)
    return score


def lexical_search(query: str, k: int = 3) -> list[dict]:
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    scored = [{**c, "score": score_chunk(query_tokens, c)} for c in CHUNKS]
    scored = [c for c in scored if c["score"] > 0]
    scored.sort(key=lambda c: c["score"], reverse=True)
    return [{k2: v for k2, v in c.items() if k2 != "tokens"} for c in scored[:k]]


# ===================== 임베딩 기반 검색 (OPENAI_API_KEY 있을 때) =====================
_embedding_cache = None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb or 1)


def _ensure_embeddings():
    global _embedding_cache
    if _embedding_cache is not None:
        return _embedding_cache
    texts = [f"{c['title']}\n{c['text']}" for c in CHUNKS]
    vectors = llm.embed(texts)
    _embedding_cache = {"vectors": vectors}
    return _embedding_cache


def search(query: str, k: int = 3) -> list[dict]:
    """통합 검색: 키가 있으면 임베딩 기반(고품질), 실패/미설정 시 로컬 키워드 기반으로 자동 폴백."""
    if llm.has_key():
        try:
            cache = _ensure_embeddings()
            q_vec = llm.embed([query])[0]
            scored = [{**c, "score": _cosine(q_vec, cache["vectors"][i])} for i, c in enumerate(CHUNKS)]
            scored.sort(key=lambda c: c["score"], reverse=True)
            return [{k2: v for k2, v in c.items() if k2 != "tokens"} for c in scored[:k]]
        except Exception:
            return lexical_search(query, k)
    return lexical_search(query, k)
