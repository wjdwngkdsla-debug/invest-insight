from __future__ import annotations

import json
import re
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any

import requests

from scripts.config import DART_API_KEY
from scripts.utils.parser import clean_int

DART_BASE = "https://opendart.fss.or.kr/api"


def _clean_text(x: object) -> str:
    text = str(x or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ")
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text).strip()


def _decode_bytes(raw: bytes) -> str:
    for enc in ["utf-8", "euc-kr", "cp949"]:
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


_CORP_LIST: list[dict[str, str]] | None = None


def _load_corp_list() -> list[dict[str, str]]:
    """DART 전체 기업코드 목록 — 수십 MB ZIP이라 배치당 한 번만 내려받아 재사용한다.

    이전에는 종목마다 매번 내려받아서 대량 편입이 종목당 수 분씩 걸렸다(5시간 배치의 주범).
    """
    global _CORP_LIST
    if _CORP_LIST is not None:
        return _CORP_LIST
    if not DART_API_KEY:
        _CORP_LIST = []
        return _CORP_LIST
    res = requests.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": DART_API_KEY}, timeout=60)
    res.raise_for_status()
    if res.content[:2] != b"PK":
        _CORP_LIST = []
        return _CORP_LIST
    zf = zipfile.ZipFile(BytesIO(res.content))
    root = ET.fromstring(zf.read(zf.namelist()[0]))
    _CORP_LIST = [
        {
            "corp_name": item.findtext("corp_name") or "",
            "corp_code": item.findtext("corp_code") or "",
            "stock_code": item.findtext("stock_code") or "",
        }
        for item in root.findall("list")
    ]
    print(f"[DART API] 기업코드 목록 로드: {len(_CORP_LIST)}개 (배치당 1회)", file=__import__('sys').stderr)
    return _CORP_LIST


def get_corp_code(company_name: str, stock_code: str = "") -> dict[str, str] | None:
    """DART 기업 식별 — 종목코드 우선, 이름은 보조.

    이름만 쓰면 사명 변경(위너스→위너스일렉)이나 동명 비상장사(DART의
    다른 '위너스')에 걸려 엉뚱한 회사를 잡는다. 종목코드는 유일하므로
    코드가 있으면 무조건 코드로 찾는다.
    """
    stock_code = (stock_code or "").strip()
    exact: list[dict[str, str]] = []
    contains: list[dict[str, str]] = []
    for row in _load_corp_list():
        if stock_code and row["stock_code"].strip() == stock_code:
            return row
        if row["corp_name"] == company_name:
            exact.append(row)
        elif company_name in row["corp_name"]:
            contains.append(row)
    matches = exact or contains
    return matches[0] if matches else None


def get_reports(corp_code: str, start_date: str = "20250101", end_date: str = "20261231") -> list[dict[str, Any]]:
    if not DART_API_KEY:
        return []
    res = requests.get(
        f"{DART_BASE}/list.json",
        params={
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bgn_de": start_date,
            "end_de": end_date,
            "page_no": 1,
            "page_count": 100,
            # 발행공시만 조회 — 대기업은 잡공시가 100건을 넘어 투자설명서가 밀려난다 (LG씨엔에스)
            "pblntf_ty": "C",
        },
        timeout=30,
    )
    res.raise_for_status()
    data = res.json()
    if data.get("status") != "000":
        return []
    return data.get("list", []) or []


def select_latest_investment_report(reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    """투자설명서 우선, 없으면 증권신고서. DART list는 최신순에 가깝지만 날짜/접수번호로 한 번 더 정렬."""
    targets = [r for r in reports if "투자설명서" in (r.get("report_nm") or "")]
    if not targets:
        targets = [r for r in reports if "증권신고서" in (r.get("report_nm") or "") and "지분증권" in (r.get("report_nm") or "")]
    if not targets:
        return None
    targets.sort(key=lambda r: (r.get("rcept_dt") or "", r.get("rcept_no") or ""), reverse=True)
    return targets[0]


def download_document_text(rcept_no: str) -> str:
    if not DART_API_KEY:
        return ""
    res = requests.get(f"{DART_BASE}/document.xml", params={"crtfc_key": DART_API_KEY, "rcept_no": rcept_no}, timeout=60)
    res.raise_for_status()
    raw = res.content
    if raw[:2] != b"PK":
        return _decode_bytes(raw)
    zf = zipfile.ZipFile(BytesIO(raw))
    texts: list[str] = []
    for name in zf.namelist():
        texts.append(_decode_bytes(zf.read(name)))
    return "\n".join(texts)


def _parse_table_rows(table_xml: str) -> list[list[str]]:
    rows = re.findall(r"<TR[\s\S]*?</TR>", table_xml, flags=re.I)
    parsed: list[list[str]] = []
    for tr in rows:
        cells = re.findall(r"<T[DH][^>]*>([\s\S]*?)</T[DH]>", tr, flags=re.I)
        cleaned = [_clean_text(c) for c in cells]
        cleaned = [c for c in cleaned if c]
        if cleaned:
            parsed.append(cleaned)
    return parsed


def _period_from_label(label: str) -> str | None:
    if "상장일" in label:
        return "상장일"
    m = re.search(r"상장\s*후\s*(\d+)\s*(개월|년)", label)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "년":
        return f"{n}년"
    return f"{n}개월"


def extract_float_summary_tables(document_text: str, expected_shares: int | None = None) -> list[dict[str, Any]]:
    """'상장 후 유통가능 주식수 현황' 요약표만 추출한다.

    상세 주주별 표는 사용하지 않는다. 오탐을 줄이기 위해 헤더가
    '구분 | 주식수 | 유통가능 주식수 비율' 형태인 표만 후보로 본다.
    """
    tables = re.findall(r"<TABLE[\s\S]*?</TABLE>", document_text, flags=re.I)
    candidates: list[dict[str, Any]] = []
    for table_idx, table_xml in enumerate(tables, start=1):
        rows = _parse_table_rows(table_xml)
        if len(rows) < 3:
            continue
        header_text = " ".join(rows[0])
        if not ("구분" in header_text and "주식수" in header_text and "유통가능" in header_text and "비율" in header_text):
            continue

        parsed_rows: list[dict[str, Any]] = []
        for row in rows[1:]:
            line = " ".join(row)
            if "유통가능" not in line:
                continue
            period = _period_from_label(line)
            if not period:
                continue
            nums = [clean_int(c) for c in row]
            nums = [n for n in nums if n is not None]
            if not nums:
                continue
            cumulative = max(nums)
            pct_match = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
            parsed_rows.append({
                "period": period,
                "row_text": line,
                "cumulative_float": cumulative,
                "float_pct": float(pct_match.group(1)) if pct_match else None,
            })

        periods = {r["period"] for r in parsed_rows}
        if "상장일" not in periods or len(parsed_rows) < 3:
            continue
        last_qty = parsed_rows[-1]["cumulative_float"] if parsed_rows else None
        candidates.append({
            "table_index": table_idx,
            "rows": parsed_rows,
            "last_cumulative_float": last_qty,
            "matches_expected_shares": bool(expected_shares and last_qty == expected_shares),
        })
    return candidates


def choose_float_summary_table(candidates: list[dict[str, Any]], expected_shares: int | None = None) -> dict[str, Any] | None:
    if not candidates:
        return None
    matched = [c for c in candidates if expected_shares and c.get("last_cumulative_float") == expected_shares]
    if matched:
        # 동일 후보가 여러 개면 문서 뒤쪽 표를 최종본으로 본다.
        return sorted(matched, key=lambda c: c["table_index"])[-1]
    # 상장주식수와 맞는 표가 없으면 뒤쪽 표를 쓰되 검토 플래그를 세울 수 있도록 반환한다.
    return sorted(candidates, key=lambda c: c["table_index"])[-1]


def parse_float_summary_lockups(company_name: str, expected_shares: int | None = None, year: int | None = None, stock_code: str = "") -> tuple[dict[str, Any] | None, list[dict[str, Any]], str]:
    """최신 투자설명서/증권신고서에서 유통가능 요약표를 파싱한다.

    반환: (선택 표, 전체 후보, note)
    선택 표의 rows는 누적 유통가능 주식수이며, build 단계에서 직전행 대비 증가분을 락업 해제 물량으로 계산한다.
    """
    corp = get_corp_code(company_name, stock_code=stock_code)
    if not corp:
        return None, [], "DART corpCode 미발견"
    start = f"{year}0101" if year else "20250101"
    end = f"{year + 1}1231" if year else "20261231"
    reports = get_reports(corp["corp_code"], start_date=start, end_date=end)
    selected_report = select_latest_investment_report(reports)
    if not selected_report:
        return None, [], "투자설명서/증권신고서 미발견"
    doc = download_document_text(selected_report["rcept_no"])
    candidates = extract_float_summary_tables(doc, expected_shares=expected_shares)
    chosen = choose_float_summary_table(candidates, expected_shares=expected_shares)
    if not chosen:
        return None, candidates, "상장 후 유통가능 주식수 현황 표 미발견"
    chosen = {**chosen, "rcept_no": selected_report.get("rcept_no"), "report_nm": selected_report.get("report_nm"), "rcept_dt": selected_report.get("rcept_dt")}
    note = "" if chosen.get("matches_expected_shares") else "마지막 누적 유통가능 주식수가 KRX 상장주식수와 불일치"
    return chosen, candidates, note
