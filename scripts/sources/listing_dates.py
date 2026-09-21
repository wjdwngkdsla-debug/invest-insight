"""Listing-date candidates, with explicit provenance and conservative acceptance."""
import re
from datetime import date


def dart_listing_candidates(plain, receipt):
    result = []
    pattern = r"상장\s*(?:예정)?\s*일(?:자)?\s*[:：]?\s*(20\d{2})\s*[년./-]\s*(\d{1,2})\s*[월./-]\s*(\d{1,2})\s*일?"
    for m in re.finditer(pattern, plain):
        try:
            value = date(*map(int, m.groups())).isoformat()
        except ValueError:
            continue
        if value not in {r["date"] for r in result}:
            result.append({"date": value, "source": "dart", "receipt": receipt,
                           "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt}",
                           "evidence": m.group(0), "status": "candidate"})
    return result


def reconcile_listing_date(item, candidates):
    # A date in a prospectus can refer to a peer listing. Candidates alone never overwrite dates.
    dates = {c["date"] for c in candidates}
    current = item.get("listing_date")
    return {"status": "conflict" if len(dates) > 1 or (current and dates and dates != {current}) else "candidate" if dates else "missing",
            "current": current, "candidates": candidates}
