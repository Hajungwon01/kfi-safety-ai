"""OpenAI 호환(Chat Completions + Embeddings) API 어댑터 (Node판 llmClient.js 포팅).
OPENAI_BASE_URL을 바꾸면 OpenAI 호환 엔드포인트를 제공하는 다른 프로바이더도 사용 가능."""
import os
import requests

BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
API_KEY = os.environ.get("OPENAI_API_KEY", "")
CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")
EMBED_MODEL = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-small")


def has_key() -> bool:
    return bool(API_KEY)


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.2) -> str:
    if not has_key():
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    res = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        json={"model": model or CHAT_MODEL, "messages": messages, "temperature": temperature},
        timeout=30,
    )
    if not res.ok:
        raise RuntimeError(f"LLM chat 호출 실패 ({res.status_code}): {res.text}")
    body = res.json()
    choices = body.get("choices") or []
    return choices[0]["message"]["content"] if choices else ""


def embed(texts: list[str]) -> list[list[float]]:
    if not has_key():
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다.")
    res = requests.post(
        f"{BASE_URL}/embeddings",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
        json={"model": EMBED_MODEL, "input": texts},
        timeout=30,
    )
    if not res.ok:
        raise RuntimeError(f"LLM embeddings 호출 실패 ({res.status_code}): {res.text}")
    body = res.json()
    return [d["embedding"] for d in body["data"]]
