"""내용연수(10년)/정비이력/리콜 기반 안전등급 판정 로직 (Node판 lifecycle.js 포팅)."""
from datetime import date, datetime, timedelta


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        # 2/29처럼 존재하지 않는 날짜 보정
        return d.replace(month=2, day=28, year=d.year + n)


def evaluate_unit(unit: dict, recall: dict | None) -> dict:
    """unit: {firstApproved: 'YYYY-MM-DD', maintenance: [{date:'YYYY-MM-DD'}, ...]}
    recall: {item, company, cancelDate, reason} 또는 None
    반환: {tenYearMark, ageStatus, extensionExpiry, recall, grade}
    """
    first_approved = _parse_date(unit["firstApproved"])
    ten_year_mark = _add_years(first_approved, 10)
    today = date.today()
    records = unit.get("maintenance", [])

    extension_expiry = None
    if today < ten_year_mark:
        age_status = "정상(내용연수 이내)"
    else:
        window_start = ten_year_mark - timedelta(days=30)
        window_end = _add_years(ten_year_mark, 1)
        valid_record = next(
            (r for r in records if window_start <= _parse_date(r["date"]) <= window_end), None
        )
        if valid_record:
            extension_expiry = _add_years(ten_year_mark, 3)
            age_status = "연장유효" if today <= extension_expiry else "연장기간 만료 - 즉시교체 필요"
        else:
            age_status = "내용연수 경과 - 즉시교체 필요"

    grade = "안전"
    if recall:
        grade = "위험(리콜대상)"
    elif "즉시교체" in age_status:
        grade = "위험(교체시급)"
    elif age_status == "연장유효":
        grade = "주의"

    return {
        "tenYearMark": ten_year_mark.isoformat(),
        "ageStatus": age_status,
        "extensionExpiry": extension_expiry.isoformat() if extension_expiry else None,
        "recall": recall,
        "grade": grade,
    }
