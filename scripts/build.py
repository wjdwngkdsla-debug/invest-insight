from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.config import require_env
from scripts.sources.krx import find_stock_by_name
from scripts.sources.dart import parse_ipo_lockup
from scripts.sources.dart_api import parse_float_summary_lockups
from scripts.sources.ipo_universe import load_or_build_ipo_universe
from scripts.sources.public_lockup_api import fetch_public_lockup_returns, normalize_public_return_item
from scripts.utils.dates import calc_release_date, parse_date, release_display

PERIOD_KEY_MAP = {
    "15일 확약": "15일",
    "1개월 확약": "1개월",
    "3개월 확약": "3개월",
    "6개월 확약": "6개월",
}

ADMIN_COLUMNS = [
    "event_id", "code", "name", "market", "listing_date", "shares", "close_price",
    "category", "type", "period",
    "planned_date", "planned_tradable_date", "planned_date_display", "planned_qty", "planned_pct",
    "dart_rcp", "dart_source", "parse_note",
    "api_return_date", "api_return_qty", "api_reason",
    "manual_date", "manual_qty", "manual_lock",
    "final_date", "final_tradable_date", "final_date_display", "final_qty", "final_pct",
    "status", "review_needed", "memo", "updated_at",
]

REVIEW_COLUMNS = [
    "detected_at", "event_id", "code", "name", "category", "period", "issue",
    "planned_date", "planned_qty", "api_return_date", "api_return_qty", "manual_date", "manual_qty", "memo",
]

LOG_COLUMNS = [
    "time", "event_id", "code", "name", "field", "old_value", "new_value", "reason",
]

CATEGORY_IPO = "IPO기관"
CATEGORY_FLOAT = "구주·보호예수"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IPO 락업 캘린더 데이터 생성/업데이트")
    parser.add_argument("--year", type=int, default=datetime.today().year, help="신규상장 IPO 탐색 연도")
    parser.add_argument("--end-date", type=str, default=None, help="KRX 탐색 종료일 YYYY-MM-DD")
    parser.add_argument("--no-refresh-universe", action="store_true", help="기존 ipo_universe_YEAR.json 사용")
    parser.add_argument("--manual-targets", action="store_true", help="테스트용 data/manual_targets.json만 사용")
    parser.add_argument("--reparse-existing", action="store_true", help="이미 편입된 종목도 DART 재파싱")
    return parser.parse_args()


def _now() -> str:
    return datetime.today().strftime("%Y-%m-%d %H:%M:%S")


def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(str(value).replace(",", ""))
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return 0.0


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _read_csv(path: Path, columns: list[str]) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({col: row.get(col, "") for col in columns})
        return rows


def _append_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def normalize_period_for_id(period: str) -> str:
    return period.replace("개월", "M").replace("년", "Y").replace("일", "D").replace(" ", "")


def build_event_id(code: str, category: str, period: str, date: str) -> str:
    safe_category = category.replace("·", "").replace(" ", "")
    return f"{code}-{safe_category}-{normalize_period_for_id(period)}-{date}"


def pct(qty: int, shares: int) -> float:
    return round(qty / shares * 100, 2) if shares else 0.0


def load_manual_targets() -> list[dict]:
    path = ROOT_DIR / "data" / "manual_targets.json"
    if not path.exists():
        raise FileNotFoundError("data/manual_targets.json 파일이 없습니다.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_listing_review_decisions() -> list[dict]:
    path = ROOT_DIR / "data" / "listing_review_decisions.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def load_targets(args: argparse.Namespace) -> list[dict]:
    if args.manual_targets:
        print("[TARGET] manual_targets.json 사용", file=sys.stderr)
        return load_manual_targets()
    print(f"[TARGET] {args.year}년 KRX 신규상장 IPO universe 생성/갱신", file=sys.stderr)
    targets = load_or_build_ipo_universe(
        args.year, refresh=not args.no_refresh_universe, end_date=args.end_date
    )
    decisions = {row.get("code", ""): row for row in load_listing_review_decisions() if row.get("code")}
    targets = [
        target for target in targets
        if decisions.get(target.get("code", ""), {}).get("review_decision") != "비IPO"
    ]
    by_code = {target.get("code", ""): target for target in targets if target.get("code")}
    for code, decision in decisions.items():
        if decision.get("review_decision") != "IPO":
            continue
        if code in by_code:
            by_code[code]["operator_forced_ipo"] = True
            by_code[code]["review_memo"] = decision.get("review_memo", "")
            continue
        target = {**decision, "operator_forced_ipo": True}
        targets.append(target)
        by_code[code] = target
    return targets


def get_stock_meta(target: dict) -> tuple[str | None, dict | None, str | None]:
    if target.get("code"):
        meta = {
            "name": target.get("name"),
            "market": target.get("market"),
            "shrs": int(target.get("shares") or 0),
            "close_price": int(target.get("close_price") or 0),
        }
        return target.get("code"), meta, target.get("detected_bas_dd")
    return find_stock_by_name(target["name"])


def build_ipo_events(target: dict, code: str, meta: dict, listing_date: str, shares: int) -> list[dict]:
    name = target["name"]
    rcp = target.get("rcp")
    parsed = target.get("parsed_ipo_lockups")
    note = ""
    if not parsed:
        rcp, parsed, note = parse_ipo_lockup(name)
    if not parsed:
        print(f"  [DART] IPO기관 파싱 실패: {note}", file=sys.stderr)
        return []

    rows: list[dict] = []
    for raw_key, period in PERIOD_KEY_MAP.items():
        entry = parsed.get(raw_key)
        if not entry:
            continue
        qty = int(entry[0])
        date, date_display, tradable_date = calc_release_date(listing_date, period)
        event_id = build_event_id(code, CATEGORY_IPO, period, tradable_date)
        rows.append({
            "event_id": event_id,
            "code": code,
            "name": name,
            "market": meta.get("market"),
            "listing_date": listing_date,
            "shares": shares,
            "close_price": int(meta.get("close_price") or 0),
            "category": CATEGORY_IPO,
            "type": "IPO확약",
            "period": period,
            "planned_date": date,
            "planned_tradable_date": tradable_date,
            "planned_date_display": date_display,
            "planned_qty": qty,
            "planned_pct": pct(qty, shares),
            "dart_rcp": rcp or "",
            "dart_source": "증권발행실적보고서",
            "parse_note": note,
            "api_return_date": "",
            "api_return_qty": "",
            "api_reason": "",
            "manual_date": "",
            "manual_qty": "",
            "manual_lock": "N",
            "memo": "",
        })
    print(f"  [DART] IPO기관 이벤트 {len(rows)}건", file=sys.stderr)
    return rows


def build_float_summary_events(target: dict, code: str, meta: dict, listing_date: str, shares: int, year: int) -> tuple[list[dict], list[dict]]:
    name = target["name"]
    chosen, candidates, note = parse_float_summary_lockups(name, expected_shares=shares, year=year)
    reviews: list[dict] = []
    if not chosen:
        print(f"  [DART API] 유통가능 요약표 실패: {note}", file=sys.stderr)
        reviews.append({
            "detected_at": _now(), "event_id": "", "code": code, "name": name, "category": CATEGORY_FLOAT, "period": "",
            "issue": note or "유통가능 요약표 파싱 실패", "memo": f"candidate_tables={len(candidates)}",
        })
        return [], reviews

    rows = chosen["rows"]
    out: list[dict] = []
    prev = None
    for row in rows:
        cumulative = int(row["cumulative_float"])
        period = row["period"]
        if prev is None:
            prev = cumulative
            continue
        inc = cumulative - prev
        prev = cumulative
        if inc <= 0:
            continue
        date, date_display, tradable_date = calc_release_date(listing_date, period)
        event_id = build_event_id(code, CATEGORY_FLOAT, period, tradable_date)
        out.append({
            "event_id": event_id,
            "code": code,
            "name": name,
            "market": meta.get("market"),
            "listing_date": listing_date,
            "shares": shares,
            "close_price": int(meta.get("close_price") or 0),
            "category": CATEGORY_FLOAT,
            "type": "보호예수",
            "period": period,
            "planned_date": date,
            "planned_tradable_date": tradable_date,
            "planned_date_display": date_display,
            "planned_qty": inc,
            "planned_pct": pct(inc, shares),
            "dart_rcp": chosen.get("rcept_no") or "",
            "dart_source": "투자설명서 유통가능 요약표",
            "parse_note": note,
            "api_return_date": "",
            "api_return_qty": "",
            "api_reason": "",
            "manual_date": "",
            "manual_qty": "",
            "manual_lock": "N",
            "memo": "",
        })
    if note:
        reviews.append({
            "detected_at": _now(), "event_id": "", "code": code, "name": name, "category": CATEGORY_FLOAT, "period": "",
            "issue": note, "planned_qty": chosen.get("last_cumulative_float"), "memo": f"selected_table={chosen.get('table_index')}",
        })
    print(f"  [DART API] 구주·보호예수 요약 이벤트 {len(out)}건 / table={chosen.get('table_index')} / note={note or '-'}", file=sys.stderr)
    return out, reviews


def carry_manual_fields(new_row: dict, old: dict | None) -> dict:
    if not old:
        return new_row
    for key in ["manual_date", "manual_qty", "manual_lock", "memo"]:
        if old.get(key) not in (None, ""):
            new_row[key] = old.get(key)
    return new_row


def rows_for_stock(existing_rows: list[dict], code: str) -> list[dict]:
    return [r for r in existing_rows if r.get("code") == code]


def match_api_to_row(api_item: dict, rows: list[dict]) -> dict | None:
    rd = api_item.get("return_date")
    rq = int(api_item.get("return_qty") or 0)
    if not rd or not rq:
        return None
    same_date = [r for r in rows if rd in {r.get("planned_date"), r.get("planned_tradable_date"), r.get("final_date"), r.get("final_tradable_date")}]
    if not same_date:
        return None
    exact = [r for r in same_date if _to_int(r.get("planned_qty")) == rq]
    if exact:
        return exact[0]
    # 날짜가 같으면 구주·보호예수 우선. API 수량으로 최종값이 바뀌며 로그에 남긴다.
    float_rows = [r for r in same_date if r.get("category") == CATEGORY_FLOAT]
    if float_rows:
        return float_rows[0]
    return same_date[0]


def create_api_only_row(api_item: dict, target: dict, code: str, meta: dict, listing_date: str, shares: int) -> dict | None:
    rd = api_item.get("return_date")
    rq = int(api_item.get("return_qty") or 0)
    if not rd or not rq:
        return None
    try:
        date_display, tradable = release_display(parse_date(rd))
        tradable_date = tradable.strftime("%Y-%m-%d")
    except Exception:
        date_display = rd
        tradable_date = rd
    period = "보호예수"
    event_id = build_event_id(code, CATEGORY_FLOAT, period, tradable_date)
    return {
        "event_id": event_id,
        "code": code,
        "name": target["name"],
        "market": meta.get("market"),
        "listing_date": listing_date,
        "shares": shares,
        "close_price": int(meta.get("close_price") or 0),
        "category": CATEGORY_FLOAT,
        "type": "보호예수",
        "period": period,
        "planned_date": rd,
        "planned_tradable_date": tradable_date,
        "planned_date_display": date_display,
        "planned_qty": rq,
        "planned_pct": pct(rq, shares),
        "dart_rcp": "",
        "dart_source": "공공데이터 API 단독",
        "parse_note": "DART 예정 이벤트와 매칭되지 않은 API 반환정보",
        "api_return_date": rd,
        "api_return_qty": rq,
        "api_reason": api_item.get("reason") or "",
        "manual_date": "",
        "manual_qty": "",
        "manual_lock": "N",
        "memo": "",
    }


def apply_api_updates(target: dict, code: str, meta: dict, listing_date: str, shares: int, rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    raw_items = fetch_public_lockup_returns(target["name"])
    api_items = [normalize_public_return_item(x) for x in raw_items]
    logs: list[dict] = []
    reviews: list[dict] = []
    print(f"  [API] 금융위 반환정보 {len(api_items)}건", file=sys.stderr)

    used_event_ids: set[str] = set()
    row_map = {r["event_id"]: r for r in rows}
    for api in api_items:
        if not api.get("return_date") or not api.get("return_qty"):
            continue
        row = match_api_to_row(api, rows)
        if row is None:
            new_row = create_api_only_row(api, target, code, meta, listing_date, shares)
            if new_row:
                rows.append(new_row)
                logs.append(log_change(new_row, "event", "", "API 단독 이벤트 추가", "금융위 API 반환정보 신규 반영"))
            continue
        used_event_ids.add(row["event_id"])
        old_api_date, old_api_qty = row.get("api_return_date", ""), row.get("api_return_qty", "")
        row["api_return_date"] = api.get("return_date") or ""
        row["api_return_qty"] = api.get("return_qty") or ""
        row["api_reason"] = api.get("reason") or ""
        if str(old_api_date) != str(row["api_return_date"]):
            logs.append(log_change(row, "api_return_date", old_api_date, row["api_return_date"], "금융위 API 반환정보 확인"))
        if str(old_api_qty) != str(row["api_return_qty"]):
            logs.append(log_change(row, "api_return_qty", old_api_qty, row["api_return_qty"], "금융위 API 반환정보 확인"))

    return rows, reviews, logs


def log_change(row: dict, field: str, old: Any, new: Any, reason: str) -> dict:
    return {
        "time": _now(),
        "event_id": row.get("event_id", ""),
        "code": row.get("code", ""),
        "name": row.get("name", ""),
        "field": field,
        "old_value": old,
        "new_value": new,
        "reason": reason,
    }


def finalize_row(row: dict) -> tuple[dict, list[dict], list[dict]]:
    logs: list[dict] = []
    reviews: list[dict] = []
    shares = _to_int(row.get("shares"))
    manual_lock = str(row.get("manual_lock") or "N").upper() == "Y"
    manual_qty = _to_int(row.get("manual_qty"))
    manual_date = row.get("manual_date") or ""
    api_qty = _to_int(row.get("api_return_qty"))
    api_date = row.get("api_return_date") or ""
    planned_qty = _to_int(row.get("planned_qty"))
    # 원본 예정일 우선 — 주말/휴장일 보정을 하지 않기로 해서(2026-07-09)
    # 과거에 저장된 보정일(planned_tradable_date)보다 원래 해제일을 쓴다.
    planned_date = row.get("planned_date") or row.get("planned_tradable_date") or ""

    old_final_qty = row.get("final_qty", "")
    old_final_date = row.get("final_date", "")

    if manual_lock and (manual_qty or manual_date):
        final_qty = manual_qty or planned_qty
        final_date = manual_date or planned_date
        status = "수동확인"
        if api_qty and api_qty != final_qty:
            row["review_needed"] = "Y"
            status = "수동/API불일치"
            reviews.append({
                "detected_at": _now(), "event_id": row.get("event_id"), "code": row.get("code"), "name": row.get("name"),
                "category": row.get("category"), "period": row.get("period"), "issue": "수동고정값과 금융위 API 반환수량 불일치",
                "planned_date": row.get("planned_date"), "planned_qty": row.get("planned_qty"),
                "api_return_date": api_date, "api_return_qty": api_qty, "manual_date": manual_date, "manual_qty": manual_qty,
                "memo": row.get("memo"),
            })
        else:
            row["review_needed"] = "N"
    elif api_qty:
        final_qty = api_qty
        final_date = api_date or planned_date
        if planned_qty and api_qty != planned_qty:
            status = "반환확인_API수정"
            row["review_needed"] = "N"  # 운영자가 볼 필요는 없고 로그에만 남긴다.
        else:
            status = "반환확인"
            row["review_needed"] = "N"
    else:
        final_qty = planned_qty
        final_date = planned_date
        status = "예정" if final_date >= datetime.today().strftime("%Y-%m-%d") else "확정(경과)"
        row["review_needed"] = row.get("review_needed") or "N"

    try:
        date_display, tradable = release_display(parse_date(final_date))
        tradable_date = tradable.strftime("%Y-%m-%d")
    except Exception:
        date_display = row.get("planned_date_display") or final_date
        tradable_date = final_date

    row["final_date"] = final_date
    row["final_tradable_date"] = tradable_date
    row["final_date_display"] = date_display
    row["final_qty"] = final_qty
    row["final_pct"] = pct(final_qty, shares)
    row["status"] = status
    row["updated_at"] = _now()

    if str(old_final_qty) not in ("", str(final_qty)):
        logs.append(log_change(row, "final_qty", old_final_qty, final_qty, "최종표시수량 재계산"))
    if str(old_final_date) not in ("", str(final_date)):
        logs.append(log_change(row, "final_date", old_final_date, final_date, "최종표시일 재계산"))
    return row, reviews, logs


def rows_to_site_data(rows: list[dict]) -> dict:
    stocks_map: dict[str, dict] = {}
    for r in rows:
        final_qty = _to_int(r.get("final_qty"))
        final_date = r.get("final_date") or r.get("planned_date")
        final_tradable = r.get("final_tradable_date") or r.get("planned_tradable_date") or final_date
        if not final_qty or not final_date:
            continue
        code = r["code"]
        stock = stocks_map.setdefault(code, {
            "code": code,
            "name": r.get("name"),
            "market": r.get("market"),
            "listing_date": r.get("listing_date"),
            "shares": _to_int(r.get("shares")),
            "close_price": _to_int(r.get("close_price")),
            "events": [],
            "holders": [],
        })
        stock["events"].append({
            "period": r.get("period"),
            "date": final_date,
            "date_display": r.get("final_date_display") or r.get("planned_date_display") or final_date,
            "tradable_date": final_tradable,
            "qty": final_qty,
            "pct": _to_float(r.get("final_pct")),
            "type": "IPO확약" if r.get("category") == CATEGORY_IPO else "보호예수",
            "category": r.get("category"),
            "status": r.get("status") or "예정",
            "source": "DART" if r.get("category") == CATEGORY_IPO else "투자설명서",
            "source_label": r.get("dart_source"),
            "rcp": r.get("dart_rcp"),
            "api_checked": bool(r.get("api_return_date")),
            "api_return_date": r.get("api_return_date") or None,
            "api_return_qty": _to_int(r.get("api_return_qty")) or None,
            "api_source": "공공데이터포털 getLockUpRetuInfo_V3",
            "holder_name": r.get("api_reason") or None,
            "reason": r.get("api_reason") or r.get("parse_note") or None,
        })
    for stock in stocks_map.values():
        stock["events"] = sorted(stock["events"], key=lambda e: e["tradable_date"])
    return {"updated": datetime.today().strftime("%Y-%m-%d"), "stocks": list(stocks_map.values())}


def main() -> None:
    require_env()
    args = parse_args()
    data_dir = ROOT_DIR / "data"
    admin_path = data_dir / "lockup_admin.csv"
    review_path = data_dir / "review_needed.csv"
    log_path = data_dir / "lockup_log.csv"

    existing_rows = _read_csv(admin_path, ADMIN_COLUMNS)
    existing_by_id = {r["event_id"]: r for r in existing_rows if r.get("event_id")}
    targets = load_targets(args)
    all_rows_by_id: dict[str, dict] = {r["event_id"]: r for r in existing_rows if r.get("event_id")}
    all_reviews: list[dict] = []
    all_logs: list[dict] = []

    print(f"[BUILD] 대상 IPO 종목 {len(targets)}개", file=sys.stderr)
    for idx, target in enumerate(targets, start=1):
        name = target["name"]
        listing_date = target["listing_date"]
        print(f"[BUILD] {idx}/{len(targets)} {name}", file=sys.stderr)
        code, meta, bas_dd = get_stock_meta(target)
        if not code or not meta:
            print(f"  [KRX] 종목 검색 실패: {name}", file=sys.stderr)
            continue
        shares = int(meta.get("shrs") or target.get("shares") or 0)
        existing_stock_rows = rows_for_stock(existing_rows, code)

        has_ipo_rows = any(row.get("category") == CATEGORY_IPO for row in existing_stock_rows)
        if existing_stock_rows and not args.reparse_existing and (
            not target.get("operator_forced_ipo") or has_ipo_rows
        ):
            print(f"  [DART] 기존 편입 종목 → DART 재파싱 생략, API 검증만 수행", file=sys.stderr)
            stock_rows = [dict(r) for r in existing_stock_rows]
        else:
            stock_rows = []
            stock_rows.extend(build_ipo_events(target, code, meta, listing_date, shares))
            float_rows, float_reviews = build_float_summary_events(target, code, meta, listing_date, shares, args.year)
            stock_rows.extend(float_rows)
            all_reviews.extend(float_reviews)
            if target.get("operator_forced_ipo") and not any(
                row.get("category") == CATEGORY_IPO for row in stock_rows
            ):
                all_reviews.append({
                    "detected_at": _now(),
                    "event_id": "",
                    "code": code,
                    "name": name,
                    "category": CATEGORY_IPO,
                    "period": "",
                    "issue": "운영자 IPO 선택 종목의 IPO기관 락업 파싱 결과 없음",
                    "planned_date": "",
                    "planned_qty": "",
                    "api_return_date": "",
                    "api_return_qty": "",
                    "manual_date": "",
                    "manual_qty": "",
                    "memo": target.get("review_memo", ""),
                })
            stock_rows = [carry_manual_fields(row, existing_by_id.get(row["event_id"])) for row in stock_rows]

        stock_rows, api_reviews, api_logs = apply_api_updates(target, code, meta, listing_date, shares, stock_rows)
        all_reviews.extend(api_reviews)
        all_logs.extend(api_logs)

        for row in stock_rows:
            finalized, reviews, logs = finalize_row(row)
            all_reviews.extend(reviews)
            all_logs.extend(logs)
            all_rows_by_id[finalized["event_id"]] = finalized

    all_rows = sorted(all_rows_by_id.values(), key=lambda r: (r.get("final_tradable_date") or r.get("planned_tradable_date") or "9999-99-99", r.get("code") or ""))
    _write_csv(admin_path, all_rows, ADMIN_COLUMNS)
    _write_csv(review_path, all_reviews, REVIEW_COLUMNS)
    _append_csv(log_path, all_logs, LOG_COLUMNS)

    site_data = rows_to_site_data(all_rows)
    out_path = data_dir / "site_data.json"
    out_path.write_text(json.dumps(site_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SAVE] admin={admin_path}", file=sys.stderr)
    print(f"[SAVE] review={review_path}", file=sys.stderr)
    print(f"[SAVE] site_data={out_path}", file=sys.stderr)
    print("[FINISH] 전체 배치 완료", file=sys.stderr)


if __name__ == "__main__":
    main()
