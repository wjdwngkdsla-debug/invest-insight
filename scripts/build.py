from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.config import require_env
from scripts.sources.krx import find_stock_by_name, krx_snapshot
from scripts.sources.dart import parse_ipo_lockup
from scripts.sources.dart_api import parse_float_summary_lockups
from scripts.sources.ipo_universe import load_or_build_ipo_universe
from scripts.sources.public_lockup_api import fetch_public_lockup_returns, normalize_public_return_item
from scripts.utils.dates import calc_release_date, next_trading_day, parse_date, release_display

PERIOD_KEY_MAP = {
    "15일 확약": "15일",
    "1개월 확약": "1개월",
    "3개월 확약": "3개월",
    "6개월 확약": "6개월",
}

ADMIN_COLUMNS = [
    "event_id", "code", "name", "market", "listing_date", "shares", "close_price", "ipo_price",
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
    ipo_price = _to_int(target.get("ipo_price"))
    note = ""
    if not parsed:
        rcp, parsed, note, ipo_price = parse_ipo_lockup(name)
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
            "ipo_price": ipo_price,
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


def row_match_dates(row: dict) -> set[str]:
    """API 반환일과 대조할 행의 날짜 후보. 저장된 값이 옛 정책(무보정)일 수 있어
    원본 예정일의 거래가능일(주말·휴장일 반영)을 즉석에서 다시 계산해 포함한다."""
    dates = {
        row.get("planned_date"),
        row.get("planned_tradable_date"),
        row.get("final_date"),
        row.get("final_tradable_date"),
    }
    try:
        # 예탁원 반환은 해제일 당일 또는 그 다음 1~2 영업일에 처리되는 경우가 있어
        # (예: 리센스메디컬 04-30 해제 → 05-04 반환) 그 범위까지 후보에 넣는다
        adjusted = release_display(parse_date(row.get("planned_date") or ""))[1]
        dates.add(adjusted.strftime("%Y-%m-%d"))
        following = next_trading_day(adjusted + timedelta(days=1))
        dates.add(following.strftime("%Y-%m-%d"))
        dates.add(next_trading_day(following + timedelta(days=1)).strftime("%Y-%m-%d"))
    except Exception:
        pass
    dates.discard(None)
    dates.discard("")
    return dates


def match_api_group_to_row(rd: str, total_qty: int, rows: list[dict]) -> dict | None:
    same_date = [r for r in rows if rd in row_match_dates(r)]
    if not same_date:
        return None
    exact = [r for r in same_date if _to_int(r.get("planned_qty")) == total_qty]
    if exact:
        return exact[0]
    # 날짜가 같으면 구주·보호예수 우선. API 수량으로 최종값이 바뀌며 로그에 남는다.
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


def apply_api_updates(
    target: dict, code: str, meta: dict, listing_date: str, shares: int, rows: list[dict]
) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    """금융위 반환정보를 행에 반영한다.

    같은 반환일의 여러 사유(벤처금융/기관투자가/기타 등)는 하나의 해제 건이므로
    합산해서 처리한다 — 예: 리센스메디컬 05-04는 3건 합계 2,251,518주가
    구주 1개월 예정물량과 정확히 일치. 과거에 만들어진 'API 단독' 행은 매 실행
    새로 생성하므로 먼저 걷어내고, 그 event_id 목록을 호출부에 돌려줘 정리시킨다.
    """
    raw_items = fetch_public_lockup_returns(target["name"])
    api_items = [normalize_public_return_item(x) for x in raw_items]
    logs: list[dict] = []
    reviews: list[dict] = []
    print(f"  [API] 금융위 반환정보 {len(api_items)}건", file=sys.stderr)

    removed_ids = [r["event_id"] for r in rows if r.get("dart_source") == "공공데이터 API 단독"]
    rows = [r for r in rows if r.get("dart_source") != "공공데이터 API 단독"]

    # 반환일 기준 합산
    groups: dict[str, dict] = {}
    for api in api_items:
        rd = api.get("return_date")
        rq = int(api.get("return_qty") or 0)
        if not rd or not rq:
            continue
        group = groups.setdefault(rd, {"qty": 0, "reasons": []})
        group["qty"] += rq
        reason = (api.get("reason") or "").strip()
        if reason and reason not in group["reasons"]:
            group["reasons"].append(reason)

    for rd in sorted(groups):
        total = groups[rd]["qty"]
        reason = " + ".join(groups[rd]["reasons"])
        row = match_api_group_to_row(rd, total, rows)
        if row is None:
            new_row = create_api_only_row(
                {"return_date": rd, "return_qty": total, "reason": reason},
                target, code, meta, listing_date, shares,
            )
            if new_row:
                rows.append(new_row)
                logs.append(log_change(new_row, "event", "", "API 단독 이벤트 추가", "금융위 API 반환정보 신규 반영"))
            continue
        old_api_date, old_api_qty = row.get("api_return_date", ""), row.get("api_return_qty", "")
        row["api_return_date"] = rd
        row["api_return_qty"] = total
        row["api_reason"] = reason
        if str(old_api_date) != str(rd):
            logs.append(log_change(row, "api_return_date", old_api_date, rd, "금융위 API 반환정보 확인"))
        if str(old_api_qty) != str(total):
            logs.append(log_change(row, "api_return_qty", old_api_qty, total, "금융위 API 반환정보 확인(동일 반환일 합산)"))

    return rows, reviews, logs, removed_ids


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


_SNAPSHOT_CACHE: tuple[str | None, dict] | None = None


def latest_krx_snapshot() -> tuple[str | None, dict]:
    """최근 거래일의 KRX 전 종목 스냅샷. 한 배치에서 한 번만 조회해 재사용한다."""
    global _SNAPSHOT_CACHE
    if _SNAPSHOT_CACHE is not None:
        return _SNAPSHOT_CACHE
    today = datetime.today()
    for back in range(0, 10):
        bas_dd = (today - timedelta(days=back)).strftime("%Y%m%d")
        snap = krx_snapshot(bas_dd)
        if snap:
            close_date = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}"
            _SNAPSHOT_CACHE = (close_date, snap)
            return _SNAPSHOT_CACHE
    _SNAPSHOT_CACHE = (None, {})
    return _SNAPSHOT_CACHE


def refresh_close_prices(rows: list[dict]) -> str | None:
    """편입된 전 종목의 종가를 최근 거래일 KRX 스냅샷으로 갱신한다.

    신규 감지 대상(올해 universe)에 없는 과거 연도 종목도 포함해 전부 갱신.
    반환값은 종가 기준일(YYYY-MM-DD), 최근 10일 내 거래일이 없으면 None.
    """
    close_date, snap = latest_krx_snapshot()
    if not close_date:
        print("[KRX] 최근 10일 내 거래일 스냅샷을 찾지 못해 종가 갱신을 건너뜁니다.", file=sys.stderr)
        return None
    updated = 0
    for row in rows:
        meta = snap.get(str(row.get("code") or ""))
        if meta and meta.get("close_price"):
            row["close_price"] = meta["close_price"]
            updated += 1
    print(f"[KRX] 종가 갱신: {updated}개 행 / 기준일 {close_date}", file=sys.stderr)
    return close_date


def align_final_dates_with_api(all_rows_by_id: dict[str, dict]) -> list[dict]:
    """같은 종목·같은 원본 예정일 그룹에서 금융위 API 반환일이 확인되면
    아직 API 확인이 없는 행(예: IPO기관 확약분)도 그 실제 반환일로 정렬한다.

    예정일은 보정 없이 원본 그대로 두지만, 예탁원이 실제로 반환한 날짜가
    확인된 경우 그것이 ground truth이므로 같은 해제 건의 날짜가 둘로
    갈라지지 않게 맞춘다. 수동고정(manual_lock=Y) 행은 건드리지 않는다.
    """
    groups: dict[tuple, list[dict]] = {}
    for row in all_rows_by_id.values():
        key = (row.get("code"), row.get("planned_date"))
        if key[0] and key[1]:
            groups.setdefault(key, []).append(row)

    logs: list[dict] = []
    for rows in groups.values():
        api_dates = {row.get("api_return_date") for row in rows if row.get("api_return_date")}
        if len(api_dates) != 1:
            continue  # API 확인이 없거나 서로 다른 날짜면 판단하지 않고 그대로 둔다
        api_date = next(iter(api_dates))
        for row in rows:
            if row.get("api_return_date"):
                continue
            if str(row.get("manual_lock") or "N").upper() == "Y":
                continue
            if row.get("final_date") == api_date:
                continue
            old = row.get("final_date")
            row["final_date"] = api_date
            row["final_tradable_date"] = api_date
            row["final_date_display"] = api_date
            logs.append(log_change(row, "final_date", old, api_date, "같은 예정일의 API 실제 반환일로 정렬"))
    return logs


MANUAL_CATEGORY_MAP = {
    "IPO기관": CATEGORY_IPO,
    "기존주주": CATEGORY_FLOAT,
    "구주·보호예수": CATEGORY_FLOAT,
}


def load_manual_events() -> list[dict]:
    path = ROOT_DIR / "data" / "manual_events.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def apply_manual_events(
    entries: list[dict],
    existing_rows: list[dict],
    existing_by_id: dict[str, dict],
    all_rows_by_id: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """시트 수기입력 탭의 필수값(종목코드/구분/기간/해제일/물량)으로 이벤트를 편입한다.

    종목명·시장·상장주식수·종가는 KRX에서 자동 보강. 같은 입력은 event_id가
    동일해 재실행 시 중복 없이 갱신되고, 운영_락업일정의 수동 컬럼 수정도 유지된다.
    """
    import re

    reviews: list[dict] = []
    logs: list[dict] = []

    def review(entry: dict, issue: str) -> None:
        reviews.append({
            "detected_at": _now(), "event_id": "", "code": entry.get("code", ""), "name": entry.get("code", ""),
            "category": entry.get("category", ""), "period": entry.get("period", ""),
            "issue": f"수기입력 오류: {issue}",
            "planned_date": entry.get("date", ""), "planned_qty": entry.get("qty", ""), "memo": "수기입력 탭 확인 필요",
        })

    listing_by_code = {
        str(r.get("code") or ""): r.get("listing_date") or ""
        for r in existing_rows
        if r.get("code") and r.get("listing_date")
    }

    for entry in entries:
        code = str(entry.get("code") or "").strip()
        category = MANUAL_CATEGORY_MAP.get(str(entry.get("category") or "").strip())
        period = str(entry.get("period") or "").strip()
        date = str(entry.get("date") or "").strip()
        qty = _to_int(entry.get("qty"))

        if not code:
            review(entry, "종목코드가 비어 있음")
            continue
        if not category:
            review(entry, "구분은 IPO기관 또는 기존주주여야 함")
            continue
        if not period:
            review(entry, "락업기간이 비어 있음")
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            review(entry, "해제일은 YYYY-MM-DD 형식이어야 함")
            continue
        if qty <= 0:
            review(entry, "물량은 0보다 큰 숫자여야 함")
            continue

        _, snap = latest_krx_snapshot()
        meta = snap.get(code)
        if not meta:
            review(entry, "KRX에서 종목코드를 찾지 못함 (코드 확인)")
            continue

        shares = _to_int(meta.get("shrs"))
        event_id = build_event_id(code, category, period, date)
        row = {
            "event_id": event_id,
            "code": code,
            "name": meta.get("name"),
            "market": meta.get("market"),
            "listing_date": listing_by_code.get(code, ""),
            "shares": shares,
            "close_price": _to_int(meta.get("close_price")),
            "category": category,
            "type": "IPO확약" if category == CATEGORY_IPO else "보호예수",
            "period": period,
            "planned_date": date,
            "planned_tradable_date": date,
            "planned_date_display": date,
            "planned_qty": qty,
            "planned_pct": pct(qty, shares),
            "dart_rcp": "",
            "dart_source": "수기입력",
            "parse_note": "시트 수기입력 탭에서 편입",
            "api_return_date": "",
            "api_return_qty": "",
            "api_reason": "",
            "manual_date": "",
            "manual_qty": "",
            "manual_lock": "N",
            "memo": "",
        }
        # 재실행 시 기존 행의 API 확인값·수동 수정값을 유지한다
        previous = existing_by_id.get(event_id)
        if previous:
            for key in ("api_return_date", "api_return_qty", "api_reason"):
                if previous.get(key) not in (None, ""):
                    row[key] = previous[key]
        row = carry_manual_fields(row, previous)

        finalized, f_reviews, f_logs = finalize_row(row)
        reviews.extend(f_reviews)
        logs.extend(f_logs)
        if event_id not in existing_by_id:
            logs.append(log_change(finalized, "event", "", "수기입력 이벤트 추가", "시트 수기입력 탭 반영"))
        all_rows_by_id[event_id] = finalized
        print(f"  [수기입력] {meta.get('name')}({code}) {period} {date} {qty:,}주 편입", file=sys.stderr)

    return reviews, logs


def rows_to_site_data(rows: list[dict], price_date: str | None = None) -> dict:
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
            "ipo_price": 0,
            "events": [],
            "holders": [],
        })
        if not stock["ipo_price"] and _to_int(r.get("ipo_price")):
            stock["ipo_price"] = _to_int(r.get("ipo_price"))
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
    # updated = 종가 기준일 (시가총액 표기의 기준). 종가 갱신 실패 시에만 실행일로 대체.
    return {"updated": price_date or datetime.today().strftime("%Y-%m-%d"), "stocks": list(stocks_map.values())}


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
    processed_codes: set[str] = set()
    for idx, target in enumerate(targets, start=1):
        name = target["name"]
        listing_date = target["listing_date"]
        print(f"[BUILD] {idx}/{len(targets)} {name}", file=sys.stderr)
        code, meta, bas_dd = get_stock_meta(target)
        if not code or not meta:
            print(f"  [KRX] 종목 검색 실패: {name}", file=sys.stderr)
            continue
        processed_codes.add(code)
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

        stock_rows, api_reviews, api_logs, removed_ids = apply_api_updates(target, code, meta, listing_date, shares, stock_rows)
        for removed_id in removed_ids:
            all_rows_by_id.pop(removed_id, None)
        all_reviews.extend(api_reviews)
        all_logs.extend(api_logs)

        for row in stock_rows:
            finalized, reviews, logs = finalize_row(row)
            all_reviews.extend(reviews)
            all_logs.extend(logs)
            all_rows_by_id[finalized["event_id"]] = finalized

    # 올해 스캔 대상이 아닌 기존 편입 종목도, 반환 미확인 이벤트가 남아 있으면 금융위 API 검증을 계속한다
    leftover_by_code: dict[str, list[dict]] = {}
    for row in existing_rows:
        code = str(row.get("code") or "")
        if code and code not in processed_codes:
            leftover_by_code.setdefault(code, []).append(row)

    for code, rows_for_code in leftover_by_code.items():
        if all(_to_int(r.get("api_return_qty")) for r in rows_for_code):
            continue  # 모든 이벤트가 이미 반환확인 완료 → 더 확인할 것 없음
        first = rows_for_code[0]
        name = first.get("name") or ""
        target = {"name": name}
        meta = {
            "name": name,
            "market": first.get("market"),
            "shrs": _to_int(first.get("shares")),
            "close_price": _to_int(first.get("close_price")),
        }
        listing_date = first.get("listing_date") or ""
        shares = _to_int(first.get("shares"))
        stock_rows = [dict(r) for r in rows_for_code]
        print(f"[BUILD] (스캔 연도 외 기존 종목) {name} → API 반환확인 갱신", file=sys.stderr)
        stock_rows, api_reviews, api_logs, removed_ids = apply_api_updates(target, code, meta, listing_date, shares, stock_rows)
        for removed_id in removed_ids:
            all_rows_by_id.pop(removed_id, None)
        all_reviews.extend(api_reviews)
        all_logs.extend(api_logs)
        for row in stock_rows:
            finalized, reviews, logs = finalize_row(row)
            all_reviews.extend(reviews)
            all_logs.extend(logs)
            all_rows_by_id[finalized["event_id"]] = finalized

    # 시트 수기입력 탭에서 내려받은 이벤트 편입 (스팩합병 등 자동 파싱이 안 되는 종목용)
    manual_entries = load_manual_events()
    if manual_entries:
        print(f"[BUILD] 수기입력 이벤트 {len(manual_entries)}건 처리", file=sys.stderr)
        manual_reviews, manual_logs = apply_manual_events(manual_entries, existing_rows, existing_by_id, all_rows_by_id)
        all_reviews.extend(manual_reviews)
        all_logs.extend(manual_logs)

    # 같은 해제 건인데 API 확인 여부에 따라 날짜가 갈라지는 것 방지
    all_logs.extend(align_final_dates_with_api(all_rows_by_id))

    all_rows = sorted(all_rows_by_id.values(), key=lambda r: (r.get("final_tradable_date") or r.get("planned_tradable_date") or "9999-99-99", r.get("code") or ""))

    # 편입된 전 종목(연도 무관)의 종가를 최근 거래일 기준으로 갱신 — 시가총액 최신화
    close_date = refresh_close_prices(all_rows)

    _write_csv(admin_path, all_rows, ADMIN_COLUMNS)
    _write_csv(review_path, all_reviews, REVIEW_COLUMNS)
    _append_csv(log_path, all_logs, LOG_COLUMNS)

    site_data = rows_to_site_data(all_rows, close_date)
    out_path = data_dir / "site_data.json"
    out_path.write_text(json.dumps(site_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SAVE] admin={admin_path}", file=sys.stderr)
    print(f"[SAVE] review={review_path}", file=sys.stderr)
    print(f"[SAVE] site_data={out_path}", file=sys.stderr)
    print("[FINISH] 전체 배치 완료", file=sys.stderr)


if __name__ == "__main__":
    main()
