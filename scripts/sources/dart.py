from __future__ import annotations

import io
import re
import requests
import pdfplumber
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from scripts.config import USER_AGENT
from scripts.utils.parser import parse_lockup_from_pdf


def _dart_session() -> requests.Session:
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST"}),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def dart_find_report(corp_name: str, report_kw: str = "증권발행실적보고서", d0: str = "20250101", d1: str | None = None) -> str | None:
    from datetime import datetime

    d1 = d1 or datetime.today().strftime("%Y%m%d")
    session = _dart_session()
    session.headers.update({**USER_AGENT, "Referer": "https://dart.fss.or.kr/dsab007/main.do"})
    # 대기업은 공시가 많아 1페이지(100건)에 실적보고서가 밀려날 수 있어 여러 페이지를 훑는다
    # (LG씨엔에스 케이스 — 이름이 정확해도 최근 공시 100건 안에 없어서 미발견 처리됐었음)
    for page in range(1, 6):
        try:
            res = session.post(
                "https://dart.fss.or.kr/dsab007/detailSearch.ax",
                data={
                    "currentPage": str(page),
                    "maxResults": "100",
                    "textCrpNm": corp_name,
                    "startDate": d0,
                    "endDate": d1,
                },
                timeout=20,
            )
        except requests.RequestException:
            return None
        matches = re.findall(r'rcpNo=(\d+)"[^>]*>\s*([^<]+?)\s*<', res.text)
        for rcp, report_name in matches:
            if report_kw in report_name:
                return rcp
        if len(matches) < 100:  # 마지막 페이지
            break
    return None


def dart_pdf(rcp: str):
    session = _dart_session()
    session.headers.update(USER_AGENT)
    try:
        res = session.get(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp}", timeout=20)
    except requests.RequestException:
        return None
    match = re.search(r'viewDoc\("' + rcp + r'",\s*"(\d+)"', res.text)
    if not match:
        return None
    try:
        pdf_res = session.get(
            "https://dart.fss.or.kr/pdf/download/pdf.do",
            params={"rcp_no": rcp, "dcm_no": match.group(1)},
            headers={**USER_AGENT, "Referer": "https://dart.fss.or.kr/pdf/download/main.do"},
            timeout=60,
        )
    except requests.RequestException:
        return None
    content_type = pdf_res.headers.get("Content-Type") or ""
    if "pdf" not in content_type.lower():
        return None
    return pdfplumber.open(io.BytesIO(pdf_res.content))


def extract_ipo_price(pdf) -> int:
    """증권발행실적보고서에서 1주당 확정 공모가(원)를 유도한다. 못 찾으면 0.

    보고서에 '공모가'라는 단어가 직접 없어서, 인수기관/배정 표의
    (수량, 금액) 쌍 중 금액이 수량으로 정확히 나눠떨어지는 것들을 모아
    가장 많이 나온 단가를 공모가로 본다 (모든 행이 같은 단가라 매우 견고).
    유상증자 등 이후 이벤트는 반영하지 않는 상장 시점 값.
    """
    from collections import Counter

    text = "\n".join(page.extract_text() or "" for page in pdf.pages[:8])
    candidates: Counter[int] = Counter()
    for qty_str, amount_str in re.findall(r"([\d,]{5,15})\s+([\d,]{7,20})", text):
        qty = int(qty_str.replace(",", ""))
        amount = int(amount_str.replace(",", ""))
        if qty < 1_000 or amount < 1_000_000:
            continue
        price, remainder = divmod(amount, qty)
        if remainder == 0 and 1_000 <= price <= 10_000_000:  # 공모가 현실 범위 (원)
            candidates[price] += 1
    if not candidates:
        return 0
    price, count = candidates.most_common(1)[0]
    return price if count >= 2 else 0  # 우연한 일치 방지: 최소 2개 행에서 확인


def parse_ipo_lockup(corp_name: str, d0: str | None = None) -> tuple[str | None, dict | None, str, int]:
    rcp = dart_find_report(corp_name, d0=d0 or "20250101")
    if not rcp:
        return None, None, "증권발행실적보고서 미발견→수동확인", 0
    pdf = dart_pdf(rcp)
    if not pdf:
        return rcp, None, "PDF 다운로드 실패→수동확인", 0
    parsed, note = parse_lockup_from_pdf(pdf)
    ipo_price = extract_ipo_price(pdf)
    return rcp, parsed, note, ipo_price
