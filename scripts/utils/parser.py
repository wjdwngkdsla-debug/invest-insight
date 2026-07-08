from __future__ import annotations

import re

TIERS = ["6개월 확약", "3개월 확약", "1개월 확약", "15일 확약", "미확약"]


def clean_int(value: object) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else None


def parse_lockup_from_pdf(pdf) -> tuple[dict | None, str]:
    """{구간: (수량, 비율문자열)}. 기관 의무보유확약 표 파싱."""
    full = "\n".join(p.extract_text() or "" for p in pdf.pages)
    if "수요예측" not in full and "의무보유확약" not in full:
        return None, "비공모(스팩합병·이전상장 등)"

    out: dict[str, tuple[int, str]] = {}
    for p in pdf.pages:
        text = p.extract_text() or ""
        if "확약" not in text:
            continue
        for tbl in p.extract_tables():
            for row in tbl:
                if not row or not row[0]:
                    continue
                key = str(row[0]).replace("\n", "").strip()
                if key in TIERS and key not in out:
                    cells = [c for c in row[1:] if c not in (None, "")]
                    if len(cells) >= 2:
                        qty = clean_int(cells[-2])
                        if qty:
                            out[key] = (qty, str(cells[-1]).strip())
    return (out, "") if out else (None, "확약표 미발견→수동확인")
