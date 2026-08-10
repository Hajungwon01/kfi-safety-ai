"""공문/안내문 사기 위험도 분석 (Node판 routes/approvals.js의 analyzeDocument 포팅)."""
import re

SCAM_PATTERNS = [
    {"re": re.compile(r"즉시\s*비치.{0,10}(않으면|아니면)"), "weight": 30, "label": "즉시비치 협박문구"},
    {"re": re.compile(r"과태료"), "weight": 20, "label": "과태료 언급"},
    {"re": re.compile(r"법(령)?\s*개정"), "weight": 15, "label": "법령개정 언급"},
    {"re": re.compile(r"오늘까지|즉시\s*결제|당일\s*입금"), "weight": 25, "label": "긴급성 압박"},
    {"re": re.compile(r"계좌.{0,5}입금"), "weight": 20, "label": "계좌 직접입금 요구"},
    {"re": re.compile(r"출동증명서?\s*없이|현금\s*결제만"), "weight": 15, "label": "비정상 결제방식"},
    {"re": re.compile(r"소방서|소방청|소방본부"), "weight": 5, "label": "소방기관 명칭 언급"},
]
OFFICIAL_NUM_RE = re.compile(r"제\s?\d{2,4}[-–]\d{2,4}[-–]?\d*\s?호|\d{4}-\d{1,2}-\d{2,4}")


def analyze_document(text: str) -> dict:
    matched = [p for p in SCAM_PATTERNS if p["re"].search(text)]
    score = sum(p["weight"] for p in matched)
    extra = []
    if matched and not OFFICIAL_NUM_RE.search(text):
        score += 10
        extra.append("공식 문서번호 형식 미확인")
    score = min(100, score)
    level = "저위험"
    if score >= 60:
        level = "고위험"
    elif score >= 30:
        level = "중위험"

    snippets = []
    for p in matched:
        for m in p["re"].finditer(text):
            snippets.append(m.group(0))

    return {"score": score, "level": level, "matched": [p["label"] for p in matched] + extra, "snippets": snippets}
