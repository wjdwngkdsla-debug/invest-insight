from __future__ import annotations

import re

TIERS = ["6개월 확약", "3개월 확약", "1개월 확약", "15일 확약", "미확약"]
# PDF 텍스트 추출 시 공백이 사라지는 보고서가 있어(예: "6개월확약")
# 공백을 제거한 형태로도 매칭한다
_TIER_BY_COMPACT = {tier.replace(" ", ""): tier for tier in TIERS}
# '확약기간' 컬럼에 "15일"처럼 기간만 적는 표(LG씨엔에스 등)도 있다.
# 아무 표에서나 "1개월"을 잡으면 오탐이 나므로, 표 헤더에 '확약'이 있을 때만 허용한다.
_BARE_TIER = {"6개월": "6개월 확약", "3개월": "3개월 확약", "1개월": "1개월 확약", "15일": "15일 확약"}


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
            header_compact = re.sub(r"\s+", "", "".join(str(c) for c in (tbl[0] or []) if c))
            allow_bare = "확약" in header_compact
            for row in tbl:
                if not row or not row[0]:
                    continue
                key_compact = re.sub(r"\s+", "", str(row[0]).replace("\n", ""))
                tier = _TIER_BY_COMPACT.get(key_compact) or (allow_bare and _BARE_TIER.get(key_compact) or None)
                if tier and tier not in out:
                    cells = [c for c in row[1:] if c not in (None, "")]
                    if len(cells) >= 2:
                        qty = clean_int(cells[-2])
                        if qty:
                            out[tier] = (qty, str(cells[-1]).strip())
    return (out, "") if out else (None, "확약표 미발견→수동확인")
