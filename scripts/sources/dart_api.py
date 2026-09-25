from __future__ import annotations

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from typing import Any

import requests

from scripts.config import DART_API_KEY
from scripts.utils.parser import clean_int
from scripts.utils.table_grid import table_grid
from scripts.ipo_quality import quantity, security_type
from scripts.ipo_evidence import reviewed_document

DART_BASE = "https://opendart.fss.or.kr/api"
DART_VIEWER_BASE = "https://dart.fss.or.kr"
DART_VIEWER_HEADERS = {"User-Agent": "Mozilla/5.0"}


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


def _dart_error(text: str) -> tuple[str, str] | None:
    """OpenDART 오류 XML이면 (상태코드, 메시지)를 돌려준다."""
    status = re.search(r"<status>\s*([^<]+)\s*</status>", text, flags=re.I)
    if not status or status.group(1).strip() == "000":
        return None
    message = re.search(r"<message>\s*([^<]+)\s*</message>", text, flags=re.I)
    return status.group(1).strip(), _clean_text(message.group(1) if message else "")


def _viewer_root_nodes(index_html: str) -> list[dict[str, str]]:
    """DART 공개 뷰어 목차에서 중복되지 않는 최상위 문서 조각을 찾는다."""
    nodes: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for block in re.findall(
        r"var\s+node1\s*=\s*\{\};([\s\S]*?)treeData\.push\(node1\)",
        index_html,
        flags=re.I,
    ):
        values: dict[str, str] = {}
        for key in ("dcmNo", "eleId", "offset", "length", "dtd"):
            match = re.search(rf"node1\[['\"]{key}['\"]\]\s*=\s*['\"]([^'\"]*)['\"]", block)
            if match:
                values[key] = match.group(1)
        identity = (values.get("dcmNo", ""), values.get("offset", ""), values.get("length", ""))
        if not all(identity) or identity in seen:
            continue
        seen.add(identity)
        nodes.append(values)
    return nodes


def _download_viewer_document_text(rcept_no: str) -> str:
    """OpenDART 원문 API 장애·한도 초과 때 공개 DART 뷰어를 대체 경로로 쓴다."""
    index = requests.get(
        f"{DART_VIEWER_BASE}/dsaf001/main.do",
        params={"rcpNo": rcept_no},
        headers=DART_VIEWER_HEADERS,
        timeout=60,
    )
    index.raise_for_status()
    nodes = _viewer_root_nodes(index.text)
    texts: list[str] = []
    for node in nodes:
        response = requests.get(
            f"{DART_VIEWER_BASE}/report/viewer.do",
            params={
                "rcpNo": rcept_no,
                "dcmNo": node["dcmNo"],
                "eleId": node.get("eleId", ""),
                "offset": node["offset"],
                "length": node["length"],
                "dtd": node.get("dtd", "dart4.xsd"),
            },
            headers=DART_VIEWER_HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        if response.text.strip():
            texts.append(response.text)
    return "\n".join(texts)


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
        raise RuntimeError("DART API key is not configured")
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
    if data.get("status") == "013":
        return []
    if data.get("status") != "000":
        raise RuntimeError(f"DART disclosure list error: {data.get('status', 'unknown')}")
    if int(data.get("total_page") or 1) > 1:
        raise RuntimeError("DART disclosure list exceeds one page; narrow the filing window")
    return data.get("list", []) or []


def select_latest_investment_report(reports: list[dict[str, Any]]) -> dict[str, Any] | None:
    """동일 IPO 기간 내 신고서와 투자설명서를 접수 순서로 비교한다."""
    targets = []
    for report in reports:
        title = report.get("report_nm") or ""
        # Attachment corrections may contain only an underwriting contract.
        if any(k in title for k in ("철회", "간이투자설명서", "첨부정정")) or security_type(title) == "non_equity":
            continue
        if "투자설명서" in title or ("증권신고서" in title and any(k in title for k in ("지분증권", "증권예탁증권"))):
            targets.append(report)
    if not targets:
        return None
    targets.sort(key=lambda r: (r.get("rcept_dt") or "", r.get("rcept_no") or ""), reverse=True)
    return targets[0]


def download_document_text(rcept_no: str) -> str:
    api_error: tuple[str, str] | None = None
    api_failure = ""
    if DART_API_KEY:
        try:
            res = requests.get(
                f"{DART_BASE}/document.xml",
                params={"crtfc_key": DART_API_KEY, "rcept_no": rcept_no},
                timeout=60,
            )
            res.raise_for_status()
            raw = res.content
            if raw[:2] == b"PK":
                zf = zipfile.ZipFile(BytesIO(raw))
                return "\n".join(_decode_bytes(zf.read(name)) for name in zf.namelist())
            decoded = _decode_bytes(raw)
            api_error = _dart_error(decoded)
            # 정상 원문이 ZIP이 아닌 형태로 오는 예외도 보존한다.
            if decoded.strip() and not api_error:
                return decoded
        except (requests.RequestException, zipfile.BadZipFile) as exc:
            api_failure = str(exc)

    viewer_text = _download_viewer_document_text(rcept_no)
    if viewer_text.strip():
        if api_error:
            print(
                f"[DART API] 원문 오류 {api_error[0]} ({api_error[1]}) → 공개 뷰어 대체",
                file=sys.stderr,
            )
        elif api_failure:
            print(f"[DART API] 원문 요청 실패 ({api_failure}) → 공개 뷰어 대체", file=sys.stderr)
        elif not DART_API_KEY:
            print("[DART API] 원문 키 없음 → 공개 뷰어 대체", file=sys.stderr)
        return viewer_text

    detail = f"{api_error[0]} {api_error[1]}" if api_error else (api_failure or "공개 뷰어 본문 없음")
    raise RuntimeError(f"DART 원문을 가져오지 못했습니다: {detail}")


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
    fixed = re.match(r"\s*(20\d{2})[년.\-/]\s*(\d{1,2})[월.\-/]\s*(\d{1,2})일?", label)
    if fixed:
        try:
            return datetime(int(fixed[1]), int(fixed[2]), int(fixed[3])).strftime("%Y-%m-%d")
        except ValueError:
            return None
    label = re.sub(r"\s+", "", label).replace("상장일로부터", "상장후")
    # "상장 후 2년 6개월"을 2년으로 잘라 읽으면 실제 30개월 물량이
    # 24개월로 당겨진다. 복합 기간은 월 단위로 정규화한다.
    compound = re.search(r"상장(?:일)?(?:후)?(\d+)년(\d+)개월", label)
    if compound:
        months = int(compound.group(1)) * 12 + int(compound.group(2))
        return f"{months}개월"
    m = re.search(r"상장(?:일)?(?:후)?(\d+)(개월|년|일)", label)
    if not m:
        return "상장일" if any(k in label for k in ("상장일", "상장당일", "상장직후")) else None
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "년":
        return f"{n}년"
    if unit == "일":
        return f"{n}일"
    return f"{n}개월"


def extract_float_summary_tables(document_text: str, expected_shares: int | None = None) -> list[dict[str, Any]]:
    """'상장 후 유통가능 주식수 현황' 요약표만 추출한다.

    상세 주주별 표는 사용하지 않는다. 오탐을 줄이기 위해 헤더가
    '구분 | 주식수 | 유통가능 주식수 비율' 형태인 표만 후보로 본다.
    """
    tables = re.findall(r"<TABLE[\s\S]*?</TABLE>", document_text, flags=re.I)
    candidates: list[dict[str, Any]] = []
    for table_idx, table_xml in enumerate(tables, start=1):
        rows, _ = table_grid(table_xml)
        if len(rows) < 3:
            continue
        # DART 표는 공모 후 기준/스톡옵션 행사 시나리오 때문에 헤더가
        # 2~3행으로 합쳐지는 경우가 많다. 첫 행만 보면 정상 표도 누락된다.
        start = next((i for i, row in enumerate(rows) if any(_period_from_label(c) for c in row)), None)
        if start is None or start == 0:
            continue
        headers = [re.sub(r"\s+", "", " ".join(row[c] for row in rows[:start])) for c in range(len(rows[0]))]
        header_text = " ".join(headers)
        if not (
            "구분" in header_text
            and ("주식수" in header_text or "물량" in header_text)
            and ("유통가능" in header_text or "유통주식수" in header_text)
            and any(k in header_text for k in ("비율", "지분율", "비중"))
        ):
            continue
        qty_cols = [c for c, h in enumerate(headers) if any(k in h for k in ("주식수", "물량"))
                    and not any(k in h for k in ("비율", "지분율", "비중", "추가", "해제", "희석가능주식반영", "행사시"))]
        preferred = [c for c in qty_cols if "누적" in headers[c] or "유통" in headers[c]]
        if not (preferred or qty_cols):
            continue
        q = (preferred or qty_cols)[0]
        pct_cols = [c for c in range(q + 1, len(headers)) if any(k in headers[c] for k in ("비율", "지분율", "비중"))]
        if not pct_cols:
            continue
        pct_col = pct_cols[0]

        parsed_rows: list[dict[str, Any]] = []
        unparsed_rows: list[str] = []
        for row in rows[start:]:
            line = " ".join(row)
            compact_line = re.sub(r"\s+", "", line)
            if "희석가능주식반영" in compact_line and "희석가능주식미반영" not in compact_line:
                continue
            period = next((p for c in row[:q] if (p := _period_from_label(c))), None)
            if not period:
                if quantity(row[q]) is not None and not any(k in line for k in ("합계", "총계")):
                    unparsed_rows.append(line)
                continue
            # 첫 번째 비율이 속한 "공모 후 기준" 수량을 사용한다. max()를
            # 쓰면 딜리셔스처럼 오른쪽의 스톡옵션 행사 시 수량을 고르게 된다.
            cumulative = quantity(re.sub(r"\s*(?:주|DR)\s*$", "", row[q], flags=re.I))
            if cumulative is None:
                unparsed_rows.append(line)
                continue
            pct_match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%?\s*", row[pct_col])
            parsed_rows.append({
                "period": period,
                "row_text": line,
                "cumulative_float": cumulative,
                "float_pct": float(pct_match.group(1)) if pct_match else None,
                # 해외주식예탁증권 상장사는 표의 단위가 DR이다. 숫자를 보통주로
                # 환산하지 않고 공시 단위를 그대로 보존한다.
                "quantity_unit": "DR" if re.search(r"(?:^|\s)DR(?:\s|$)", line, flags=re.I) else "주",
            })

        periods = {r["period"] for r in parsed_rows}
        if "상장일" not in periods or len(parsed_rows) < 3:
            continue
        # Some schedules show each period's increment, not cumulative quantities.
        percentages = [r.get("float_pct") for r in parsed_rows]
        incremental = False
        if all(p is not None for p in percentages) and abs(sum(percentages) - 100) <= 0.05 and percentages[-1] < 99:
            total = sum(r["cumulative_float"] for r in parsed_rows)
            incremental = total > 0 and all(abs(r["cumulative_float"] / total * 100 - r["float_pct"]) <= 0.015 for r in parsed_rows)
            if incremental:
                running = 0
                for r in parsed_rows:
                    r["period_float"] = r["cumulative_float"]
                    running += r["period_float"]
                    r["cumulative_float"] = running
                    r["float_pct"] = running / total * 100
        last_qty = parsed_rows[-1]["cumulative_float"] if parsed_rows else None
        candidates.append({
            "table_index": table_idx,
            "rows": parsed_rows,
            "last_cumulative_float": last_qty,
            "matches_expected_shares": bool(expected_shares and last_qty == expected_shares),
            "summary_kind": "incremental" if incremental else "cumulative",
            "unparsed_rows": unparsed_rows,
        })
    return candidates


_HOLDER_PERIOD = re.compile(r"(\d+)\s*(개월|년|일)")


def _holder_period(cell: str) -> str | None:
    """'상장일로부터 6개월', '3년', '6개월' → '6개월'/'3년'. 기간이 아니면 None."""
    text = _clean_text(cell)
    if not text or "%" in text:
        return None
    # 날짜(2025.05.19)나 각주(주1)가 잘못 걸리지 않게 기간 표기만 인정한다
    if re.search(r"\d{4}[.\-/]\d{1,2}", text):
        return None
    compound = re.search(r"(\d+)\s*년\s*(\d+)\s*개월", text)
    if compound:
        months = int(compound.group(1)) * 12 + int(compound.group(2))
        return f"{months}개월" if 0 < months <= 60 else None
    m = _HOLDER_PERIOD.search(text)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    if unit == "일":
        return f"{n}일" if n in (15, 30) else None
    # "2024년"처럼 연도가 적힌 칸을 기간으로 읽으면 안 된다. 의무보유는 길어야 5년.
    if unit == "년" and n > 5:
        return None
    if unit == "개월" and n > 60:
        return None
    return f"{n}{unit}"


def _mapped_holder_table(table_xml: str, table_idx: int, expected_shares: int | None):
    rows, origins = table_grid(table_xml)
    if len(rows) < 4:
        return None
    # A merged header can have three levels. Keep their column identities intact.
    header_count = next((i for i, row in enumerate(rows) if any(_holder_period(c) for c in row)), 3)
    header_count = min(header_count, 4)
    headers = [re.sub(r"\s+", "", " ".join(r[c] for r in rows[:header_count])) for c in range(len(rows[0]))]
    if not any("주주명" in h or "성명" in h for h in headers):
        return None
    qty_cols = [i for i, h in enumerate(headers) if any(k in h for k in ("매각제한물량", "유통제한물량", "의무보유주식수")) and not any(k in h for k in ("지분율", "비율", "%"))]
    explicit_qty = [i for i in qty_cols if headers[i].endswith("주식수")]
    if explicit_qty:
        qty_cols = explicit_qty
    period_cols = [i for i, h in enumerate(headers) if any(k in h for k in ("매각제한기간", "의무보유기간", "보호예수기간"))]
    if len(qty_cols) != 1 or len(period_cols) != 1:
        return None
    q, p = qty_cols[0], period_cols[0]
    components = [i for i, h in enumerate(headers) if "매각제한물량" in h and any(k in h for k in ("의무보유물량", "자발적보유물량"))]
    parsed, totals, used, ambiguous, unresolved = [], [], set(), False, []
    for r, row in enumerate(rows[header_count:], start=header_count):
        value = quantity(row[q])
        # Some source rows leave the restricted subtotal blank but fill its components.
        if value is None and row[q].strip() in ("", "-") and len(components) == 2:
            parts = [0 if row[c].strip() == "-" else quantity(row[c]) for c in components]
            if all(part is not None for part in parts):
                value = sum(parts)
            elif (q + 1 < len(row) and any(re.fullmatch(r"0(?:\.0+)?%", row[c]) for c in components)
                  and quantity(row[q + 1]) is not None):
                # Malformed DART rows sometimes shift subtotal into the ratio cell.
                # Accept only an exact duplicate of the one numeric component;
                # the whole table must still reconcile to the reported total.
                numeric = [part for part in parts if part is not None and part > 0]
                if len(numeric) == 1 and numeric[0] == quantity(row[q + 1]):
                    value = numeric[0]
        label = re.sub(r"\s+", "", " ".join(row[:q]))
        if "합계" in label or "총계" in label:
            if value is not None:
                totals.append(value)
            continue
        if "소계" in label:
            continue
        splits = re.findall(r"(\d+)\s*(년|개월|일)\s*\(\s*([\d,]+)\s*주\s*\)", row[p])
        if value and len(splits) > 1:
            split_rows = [{"period": _holder_period(n + unit), "qty": int(qty.replace(",", ""))} for n, unit, qty in splits]
            if all(s["period"] for s in split_rows) and sum(s["qty"] for s in split_rows) == value:
                origin = origins.get((r, q))
                if origin in used:
                    ambiguous = True
                else:
                    parsed.extend(split_rows)
                    used.add(origin)
            else:
                unresolved.append({"label": label, "qty": value, "period_text": row[p]})
            continue
        period = _holder_period(row[p])
        if value in (None, 0):
            continue
        if not period:
            unresolved.append({"label": label, "qty": value, "period_text": row[p]})
            continue
        if "예탁일" in row[p]:
            unresolved.append({"label": label, "qty": value, "period_text": row[p]})
            continue
        origin = origins.get((r, q))
        if origin in used:
            # A single quantity spanning multiple periods is not an allocation breakdown.
            ambiguous = True
            continue
        used.add(origin)
        parsed.append({"period": period, "qty": value})
    total = sum(r["qty"] for r in parsed)
    if not parsed and not unresolved:
        return None
    verified = bool(totals and total == totals[-1] and not ambiguous and not unresolved and (not expected_shares or total <= expected_shares))
    scope = "ipo_distribution" if any("공모후" in h or "총주식수" in h for h in headers) and any("유통가능" in h for h in headers) else "shareholder_subset"
    return {"table_index": table_idx, "rows": parsed, "total": total, "verified": verified,
            "subtotals": totals, "method": "header_grid", "scope": scope, "unresolved": unresolved}


def extract_holder_lockup_tables(document_text: str, expected_shares: int | None = None) -> list[dict[str, Any]]:
    """주주별 세부내역 표에서 (의무보유 기간, 매각제한 물량)을 뽑는다.

    누적 요약표('상장 후 유통가능 주식수 현황')를 싣지 않는 투자설명서가 많다.
    그런 문서는 주주 단위 표에 매각제한 물량과 의무보유 기간을 적는데, 형식이
    세 가지쯤 된다(유통가능·매각제한 병렬 / 매각제한만 / 가능여부 컬럼).

    컬럼 위치가 제각각이라 위치 대신 규칙으로 읽는다.
      · 행에서 기간 표기를 찾는다 → 없으면 소계·합계·유통가능 행이므로 건너뛴다
      · 기간 앞쪽의 마지막 비율 아닌 숫자 = 그 주주의 매각제한 물량
    """
    tables = re.findall(r"<TABLE[\s\S]*?</TABLE>", document_text, flags=re.I)
    candidates: list[dict[str, Any]] = []
    for table_idx, table_xml in enumerate(tables, start=1):
        if any(k in table_xml for k in ("매각제한", "의무보유", "유통제한")):
            mapped = _mapped_holder_table(table_xml, table_idx, expected_shares)
            if mapped:
                candidates.append(mapped)
                continue
        rows = _parse_table_rows(table_xml)
        if len(rows) < 4:
            continue
        header = " ".join(cell for row in rows[:3] for cell in row)
        header_cells = [re.sub(r"\s+", "", cell) for row in rows[:3] for cell in row]
        if not any(re.fullmatch(r"(?:주주명|성명|주주|주주구분)(?:\([^)]*\))?", cell) for cell in header_cells):
            continue
        if not (
            ("주주명" in header or "성명" in header or "주주" in header)
            and ("의무보유" in header or "매각제한" in header or "유통제한" in header)
        ):
            continue

        if "유통가능물량" in re.sub(r"\s+", "", header) and "매각제한물량" in re.sub(r"\s+", "", header):
            # Ambiguous parallel columns must not fall back to the last numeric cell.
            continue

        parsed: list[dict[str, Any]] = []
        subtotals: list[int] = []
        for row in rows:
            line = " ".join(row)
            # 소계·합계는 개별 물량이 아니라 요약이다. 대신 검산에 쓸 수 있게 모아 둔다.
            if any(word in line for word in ("소계", "합계")):
                for cell in row:
                    text = _clean_text(cell)
                    if "%" in text:
                        continue
                    value = clean_int(text)
                    if value and value > 1000:
                        subtotals.append(value)
                continue
            period_at = next(
                (index for index, cell in enumerate(row) if _holder_period(cell)), None,
            )
            if period_at is None:
                continue
            qty = None
            for cell in row[:period_at]:
                text = _clean_text(cell)
                if "%" in text:
                    continue
                value = clean_int(text)
                if value:
                    qty = value
            if not qty:
                continue
            parsed.append({"period": _holder_period(row[period_at]), "qty": qty})

        if len(parsed) < 2:
            continue
        total = sum(item["qty"] for item in parsed)
        # 물량 합이 상장주식수를 넘으면 다른 표(공모 전 지분 등)를 잘못 잡은 것이다
        if expected_shares and total > expected_shares:
            continue
        # 표에 적힌 소계 중 우리 합계와 맞는 값이 있으면 읽기가 맞았다는 뜻이다.
        # 맞는 값이 하나도 없으면 rowspan 등으로 행이 빠졌을 수 있어 검토 대상이다.
        verified = any(abs(value - total) <= max(1, total // 1000) for value in subtotals)
        candidates.append({
            "table_index": table_idx, "rows": parsed, "total": total,
            "verified": verified, "subtotals": subtotals,
        })
    return candidates


def choose_holder_lockup_table(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    """뒤쪽 최종 표가 검산 실패하면 과거 표로 숨기지 않고 검토 대상으로 남긴다."""
    if not candidates:
        return None
    # Later director/major-shareholder tables are subsets, not newer IPO totals.
    full = [c for c in candidates if c.get("scope") == "ipo_distribution"]
    return max(full or candidates, key=lambda c: c["table_index"])


def float_summary_snapshot(doc: str, rcept_no: str) -> dict[str, Any] | None:
    """Validate the same cumulative schedule used by build_float_summary_events."""
    from scripts.utils.dates import calc_release_date

    chosen = choose_float_summary_table(extract_float_summary_tables(doc))
    if not chosen:
        return None
    rows = chosen["rows"]
    base = {"rcept_no": rcept_no, "basis": "float_summary", "table_index": chosen["table_index"],
            "cumulative_rows": rows, "date_basis": "listing_relative_or_explicit_date"}
    if chosen.get("unparsed_rows"):
        return {**base, "status": "review", "reason": "유통가능 요약표 미해석 행 확인 필요", "unparsed_rows": chosen["unparsed_rows"]}
    previous, previous_relative_date, previous_date = None, -1, ""
    releases = []
    for index, row in enumerate(rows):
        period, qty = row["period"], row["cumulative_float"]
        match = re.fullmatch(r"(\d+)(개월|년|일)", period)
        absolute = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", period))
        relative_date = 0 if period == "상장일" else (int(calc_release_date("2000-01-01", period)[0].replace("-", "")) if match else -1)
        invalid_order = (period <= previous_date if previous_date else False) if absolute else relative_date <= previous_relative_date
        if (index == 0 and period != "상장일") or invalid_order or qty < 0 or (previous is not None and qty < previous):
            return {**base, "status": "review", "reason": "유통가능 요약표 기간·누적물량 검산 실패"}
        if previous is not None and qty > previous:
            releases.append({"period": period, "qty": qty - previous})
        previous = qty
        if absolute:
            previous_date = period
        else:
            previous_relative_date = relative_date
    last_pct = rows[-1].get("float_pct")
    if last_pct is not None and not 0 < last_pct <= 100.01:
        return {**base, "status": "review", "reason": "유통가능 요약표 비율 범위 확인 필요"}
    if last_pct:
        denominator = rows[-1]["cumulative_float"] * 100 / last_pct
        mismatches = [{"period": r['period'], "qty": r['cumulative_float'], "reported_pct": r['float_pct'],
                       "calculated_pct": round(r['cumulative_float'] / denominator * 100, 2)}
                      for r in rows if denominator > 0 and r.get('float_pct') is not None
                      and abs(r['cumulative_float'] / denominator * 100 - r['float_pct']) > 0.12]
        if denominator <= 0 or mismatches:
            return {**base, "status": "review", "reason": "유통가능 요약표 수량·비율 불일치", "ratio_mismatches": mismatches}
    return {**base, "status": "verified", "total": rows[-1]["cumulative_float"] - rows[0]["cumulative_float"],
            "coverage": "full" if last_pct is not None and abs(last_pct - 100) <= 0.01 else "disclosed_periods_only",
            "rows": releases, "summary_kind": chosen.get("summary_kind", "cumulative"),
            "quantity_unit": rows[0].get("quantity_unit", "주")}


def holder_snapshot(doc: str, rcept_no: str) -> dict[str, Any]:
    complete = reviewed_document(rcept_no)
    if complete != rcept_no:
        snapshot = holder_snapshot(download_document_text(complete), complete)
        snapshot['reviewed_correction_receipt'] = rcept_no
        return snapshot
    summary = float_summary_snapshot(doc, rcept_no)
    if summary is not None:
        # Detailed deposit anchors do not block a verified listing-relative schedule.
        detail = _detail_holder_snapshot(doc, rcept_no)
        from scripts.ipo_evidence import reconcile_reviewed_detail
        reconciled = reconcile_reviewed_detail(summary, detail)
        if reconciled:
            return reconciled
        if detail.get("status") != "verified":
            summary["detail_advisory"] = detail
        return summary
    return _detail_holder_snapshot(doc, rcept_no)


def _detail_holder_snapshot(doc: str, rcept_no: str) -> dict[str, Any]:
    chosen = choose_holder_lockup_table(extract_holder_lockup_tables(doc))
    if not chosen:
        plain = _clean_text(doc)
        reference = re.search(r"위\s*정정사항\s*외에?[\s\S]{0,100}?(20\d{2})년\s*(\d{1,2})월\s*(\d{1,2})일[\s\S]{0,100}?동일", plain)
        if reference:
            original_date = f"{int(reference[1]):04d}-{int(reference[2]):02d}-{int(reference[3]):02d}"
            return {"status": "review", "rcept_no": rcept_no, "reason": "정정사항만 수록: 원본문 대조 필요", "referenced_filing_date": original_date}
        return {"status": "review", "rcept_no": rcept_no, "reason": "기존주주 표 미발견"}
    if not chosen.get("verified"):
        reason = "보유기간·기산일 확인 필요" if chosen.get("unresolved") else "매각제한 합계 검산 실패"
        return {"status": "review", "rcept_no": rcept_no, "reason": reason,
                "table_index": chosen["table_index"], "parsed_total": chosen["total"],
                "reported_totals": chosen.get("subtotals", []), "unresolved": chosen.get("unresolved", [])}
    by_period = {}
    for row in chosen["rows"]:
        by_period[row["period"]] = by_period.get(row["period"], 0) + row["qty"]
    return {"status": "verified", "rcept_no": rcept_no, "total": chosen["total"],
            "table_index": chosen["table_index"], "rows": [{"period": p, "qty": q} for p, q in by_period.items()]}


def merge_holder_snapshot(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    """Keep last verified quantities for inspection without marking a failed correction verified."""
    result = dict(current)
    previous = previous or {}
    if current.get("status") != "verified":
        verified = previous if previous.get("status") == "verified" else previous.get("last_verified")
        if verified:
            result["last_verified"] = {k: v for k, v in verified.items() if k != "last_verified"}
    return result


def parse_holder_lockups(
    company_name: str, expected_shares: int | None = None, year: int | None = None, stock_code: str = "",
) -> tuple[dict[str, int], str, str]:
    """주주별 표를 기간별 물량으로 합산해 돌려준다. 반환: ({기간: 물량}, 접수번호, note)"""
    corp = get_corp_code(company_name, stock_code=stock_code)
    if not corp:
        return {}, "", "DART corpCode 미발견"
    start = f"{year}0101" if year else "20250101"
    end = f"{year + 1}1231" if year else "20261231"
    selected = select_latest_investment_report(get_reports(corp["corp_code"], start_date=start, end_date=end))
    if not selected:
        return {}, "", "투자설명서/증권신고서 미발견"
    doc = download_document_text(selected["rcept_no"])
    chosen = choose_holder_lockup_table(extract_holder_lockup_tables(doc, expected_shares=expected_shares))
    if not chosen:
        return {}, "", "주주별 매각제한 표 미발견"
    by_period: dict[str, int] = {}
    for item in chosen["rows"]:
        by_period[item["period"]] = by_period.get(item["period"], 0) + item["qty"]
    note = "" if chosen.get("verified") else "표의 소계와 합계가 맞지 않음 — 수기 확인 필요"
    return by_period, str(selected.get("rcept_no") or ""), note


_FLOAT_SENTENCE = re.compile(
    r"상장예정주식수[^.]{0,40}?([\d,]{6,})\s*주[^.]{0,80}?([\d.]+)\s*%에\s*해당하는\s*([\d,]{5,})\s*주"
)


def parse_listing_float_sentence(
    company_name: str, year: int | None = None, stock_code: str = "",
) -> tuple[int, int, float, str]:
    """투자설명서 본문에서 상장 직후 유통가능물량 문장을 읽는다.

    "상장예정주식수 30,445,200주 중 약 20.45%에 해당하는 6,227,100주는 상장 직후
    유통가능물량입니다" — 표가 없어도 이 문장은 있는 경우가 있어 마지막 보루로 쓴다.
    다만 모든 문서에 있는 건 아니다(이뮨온시아·아스테라시스·클로봇에는 없다).

    반환: (상장예정주식수, 유통가능주식수, 비율, note)
    """
    corp = get_corp_code(company_name, stock_code=stock_code)
    if not corp:
        return 0, 0, 0.0, "DART corpCode 미발견"
    start = f"{year}0101" if year else "20250101"
    end = f"{year + 1}1231" if year else "20261231"
    selected = select_latest_investment_report(get_reports(corp["corp_code"], start_date=start, end_date=end))
    if not selected:
        return 0, 0, 0.0, "투자설명서/증권신고서 미발견"
    match = _FLOAT_SENTENCE.search(download_document_text(selected["rcept_no"]))
    if not match:
        return 0, 0, 0.0, "유통가능물량 문장 미발견"
    total = clean_int(match.group(1)) or 0
    free = clean_int(match.group(3)) or 0
    try:
        pct_value = float(match.group(2))
    except ValueError:
        pct_value = 0.0
    return total, free, pct_value, ""


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
    source_receipt = reviewed_document(selected_report["rcept_no"])
    doc = download_document_text(source_receipt)
    candidates = extract_float_summary_tables(doc, expected_shares=expected_shares)
    chosen = choose_float_summary_table(candidates, expected_shares=expected_shares)
    if not chosen:
        return None, candidates, "상장 후 유통가능 주식수 현황 표 미발견"
    chosen = {**chosen, "rcept_no": source_receipt, "report_nm": selected_report.get("report_nm"), "rcept_dt": selected_report.get("rcept_dt")}
    note = "" if chosen.get("matches_expected_shares") else "마지막 누적 유통가능 주식수가 KRX 상장주식수와 불일치"
    return chosen, candidates, note
