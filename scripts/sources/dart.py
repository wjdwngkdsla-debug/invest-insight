from __future__ import annotations

import io
import re
import requests
import pdfplumber

from scripts.config import USER_AGENT
from scripts.utils.parser import parse_lockup_from_pdf


def dart_find_report(corp_name: str, report_kw: str = "증권발행실적보고서", d0: str = "20250101", d1: str | None = None) -> str | None:
    from datetime import datetime

    d1 = d1 or datetime.today().strftime("%Y%m%d")
    session = requests.Session()
    session.headers.update({**USER_AGENT, "Referer": "https://dart.fss.or.kr/dsab007/main.do"})
    res = session.post(
        "https://dart.fss.or.kr/dsab007/detailSearch.ax",
        data={
            "currentPage": "1",
            "maxResults": "100",
            "textCrpNm": corp_name,
            "startDate": d0,
            "endDate": d1,
        },
        timeout=20,
    )
    for rcp, report_name in re.findall(r'rcpNo=(\d+)"[^>]*>\s*([^<]+?)\s*<', res.text):
        if report_kw in report_name:
            return rcp
    return None


def dart_pdf(rcp: str):
    session = requests.Session()
    session.headers.update(USER_AGENT)
    res = session.get(f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcp}", timeout=20)
    match = re.search(r'viewDoc\("' + rcp + r'",\s*"(\d+)"', res.text)
    if not match:
        return None
    pdf_res = session.get(
        "https://dart.fss.or.kr/pdf/download/pdf.do",
        params={"rcp_no": rcp, "dcm_no": match.group(1)},
        headers={**USER_AGENT, "Referer": "https://dart.fss.or.kr/pdf/download/main.do"},
        timeout=60,
    )
    content_type = pdf_res.headers.get("Content-Type") or ""
    if "pdf" not in content_type.lower():
        return None
    return pdfplumber.open(io.BytesIO(pdf_res.content))


def parse_ipo_lockup(corp_name: str) -> tuple[str | None, dict | None, str]:
    rcp = dart_find_report(corp_name)
    if not rcp:
        return None, None, "증권발행실적보고서 미발견→수동확인"
    pdf = dart_pdf(rcp)
    if not pdf:
        return rcp, None, "PDF 다운로드 실패→수동확인"
    parsed, note = parse_lockup_from_pdf(pdf)
    return rcp, parsed, note
