from __future__ import annotations
































import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
































ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
































from scripts.config import require_env
from scripts.sources.krx import find_stock_by_name, krx_snapshot, latest_base_info
from scripts.sources.dart import parse_ipo_lockup
from scripts.sources.dart_api import (
    get_corp_code,
    parse_float_summary_lockups,
    parse_holder_lockups,
    parse_listing_float_sentence,
)
from scripts.sources.public_lockup_api import fetch_public_lockup_returns, normalize_public_return_item
from scripts.utils.dates import calc_release_date, next_trading_day, parse_date, release_display
from scripts.utils.redaction import redact_sensitive_text
from scripts.management import is_spac_name
































PERIOD_KEY_MAP = {
    "15일 확약": "15일",
    "1개월 확약": "1개월",
    "3개월 확약": "3개월",
    "6개월 확약": "6개월",
}
































ADMIN_COLUMNS = [
    "event_id", "code", "name", "market", "listing_date", "shares", "current_shares", "shares_date",
    "close_price", "ipo_price",
    "category", "type", "period",
    "planned_date", "planned_tradable_date", "planned_date_display", "planned_qty", "planned_pct",
    "dart_rcp", "dart_source", "parse_note",
    "api_return_date", "api_return_qty", "api_reason", "api_reason_breakdown",
    "manual_date", "manual_qty", "manual_lock", "manual_mode", "sheet_visible",
    "final_date", "final_tradable_date", "final_date_display", "final_qty", "final_pct",
    "status", "review_needed", "memo", "updated_at",
]
































REVIEW_COLUMNS = [
    "review_id", "status", "name", "code", "review_type", "target", "issue", "comparison",
    "first_detected", "last_detected", "resolved_at", "operator_memo", "event_id",
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
    parser.add_argument(
        "--reparse-incomplete",
        action="store_true",
        help="종목관리/IPO기관/기존주주(락업) 중 빈값이 있는 종목만 DART 재파싱 (IPO일정 탭은 별도 백필)",
    )
    parser.add_argument(
        "--max-new", type=int, default=50,
        help="한 실행에서 새로 편입할 최대 종목 수 (초과분은 다음 배치에서 이어서, 0=무제한)",
    )
    parser.add_argument(
        "--backfill-all", action="store_true",
        help="IPO일정 백필(과거 종목 신고서·실적보고서)을 배치당 상한 없이 전량 처리",
    )
    return parser.parse_args()
































































def _now() -> str:
    return datetime.today().strftime("%Y-%m-%d %H:%M:%S")
































































def _to_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    schedule_pre_refreshed = False
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
































































def normalize_stock_code(code: Any) -> str:
    code = str(code or "").strip()
    return code.zfill(6) if code.isdigit() and len(code) < 6 else code
































































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


def discard_id_drifted_duplicates(all_rows_by_id: dict[str, dict]) -> list[dict]:
    """거래가능일이 바뀌어 ID가 갈라진 같은 이벤트의 옛 행을 지운다.

    이벤트ID는 거래가능일로 만든다. 운영자가 휴장일 탭에 공휴일을 추가하면
    보정 결과가 바뀌어(마키나락스 3년: 2029-05-21 → 05-22, 석가탄신일 대체휴일
    추가) 같은 해제 건이 새 ID로 하나 더 생기고 옛 행이 그대로 남는다.
    화면에서는 같은 물량이 두 번 잡히므로 배치가 스스로 정리한다.

    같은 종목·구분·기간·물량·거래가능일인데 ID만 다른 경우만 대상으로 하고,
    ID 접미사가 현재 거래가능일과 일치하는 행(=보정 후)을 남긴다.
    수동고정(manual_lock=Y) 행은 운영자 입력이므로 건드리지 않는다.
    """
    groups: dict[tuple, list[tuple[str, dict]]] = {}
    for event_id, row in all_rows_by_id.items():
        tradable = row.get("final_tradable_date") or row.get("planned_tradable_date") or ""
        key = (
            row.get("code"), row.get("category"),
            normalize_period_for_id(str(row.get("period") or "")),
            _to_int(row.get("final_qty")), tradable,
        )
        if key[0] and key[4] and key[3]:
            groups.setdefault(key, []).append((event_id, row))

    logs: list[dict] = []
    for key, entries in groups.items():
        if len(entries) < 2:
            continue
        tradable = key[4]
        keep = next(
            (pair for pair in entries if str(pair[0]).endswith(f"-{tradable}")),
            max(entries, key=lambda pair: str(pair[1].get("updated_at") or "")),
        )
        for event_id, row in entries:
            if event_id == keep[0] or str(row.get("manual_lock") or "N").upper() == "Y":
                continue
            all_rows_by_id.pop(event_id, None)
            logs.append({
                "event_id": event_id, "code": row.get("code", ""), "name": row.get("name", ""),
                "field": "중복 이벤트 제거", "old_value": event_id, "new_value": keep[0],
                "reason": "휴장일 반영으로 거래가능일이 바뀌어 ID가 갈라진 같은 해제 건",
                "updated_at": _now(),
            })
            print(
                f"[BUILD] 중복 이벤트 제거: {row.get('name')} {row.get('period')} "
                f"{event_id} → {keep[0]}",
                file=sys.stderr,
            )
    return logs
































































def pct(qty: int, shares: int) -> float:
    return round(qty / shares * 100, 2) if shares else 0.0
















GENERIC_PERIOD_LABELS = {"", "보호예수", "기존주주", "구주", "구주·보호예수", "기타"}
LOCKUP_PERIOD_CANDIDATES = [
    "15일", "1개월", "2개월", "3개월", "6개월", "12개월", "18개월", "24개월", "30개월", "36개월",
]












def infer_lockup_period(listing_date: str, release_date: str, fallback: str = "") -> str:
    fallback = str(fallback or "").strip()
    try:
        listed = parse_date(listing_date)
        released = parse_date(release_date)
    except Exception:
        return fallback




    for period in LOCKUP_PERIOD_CANDIDATES:
        try:
            planned, _, tradable = calc_release_date(listing_date, period)
        except Exception:
            continue
        # calc_release_date의 세 번째 반환값은 이미 YYYY-MM-DD 문자열이다.
        if release_date in {planned, tradable}:
            return period




    days = (released - listed).days
    approx = [
        ("15일", 15, 3),
        ("1개월", 30, 5),
        ("2개월", 60, 7),
        ("3개월", 91, 10),
        ("6개월", 183, 14),
        ("12개월", 365, 21),
        ("18개월", 548, 28),
        ("24개월", 730, 35),
        ("30개월", 913, 42),
        ("36개월", 1095, 45),
    ]
    for period, target_days, tolerance in approx:
        if abs(days - target_days) <= tolerance:
            return period
    return fallback






def normalize_row_period(row: dict) -> dict:
    period = str(row.get("period") or "").strip()
    if row.get("category") != CATEGORY_FLOAT or period not in GENERIC_PERIOD_LABELS:
        return row
    release_date = (
        row.get("planned_date")
        or row.get("planned_tradable_date")
        or row.get("api_return_date")
        or row.get("final_date")
        or ""
    )
    inferred = infer_lockup_period(row.get("listing_date") or "", release_date, "기타")
    if inferred:
        row["period"] = inferred
        old_event_id = row.get("event_id") or ""
        if old_event_id:
            row["event_id"] = build_event_id(row.get("code", ""), row.get("category", ""), inferred, row.get("planned_tradable_date") or row.get("final_tradable_date") or release_date)
        note = row.get("parse_note") or ""
        if "기간 자동보정" not in note:
            row["parse_note"] = (note + " / " if note else "") + f"기간 자동보정: {period or '빈값'}→{inferred}" 
    return row
































































def load_manual_targets() -> list[dict]:
    path = ROOT_DIR / "data" / "manual_targets.json"
    if not path.exists():
        raise FileNotFoundError("data/manual_targets.json 파일이 없습니다.")
    return json.loads(path.read_text(encoding="utf-8"))


def _without_spac_targets(targets: list[dict], source_label: str) -> list[dict]:
    spac_targets = [target for target in targets if is_spac_name(target.get("name"))]
    kept = [target for target in targets if not is_spac_name(target.get("name"))]
    print(
        f"[TARGET] {source_label} 기준 {len(kept)}개 종목"
        + (f" / 스팩 자동 제외 {len(spac_targets)}개" if spac_targets else ""),
        file=sys.stderr,
    )
    return kept
































































def load_targets(args: argparse.Namespace) -> list[dict]:
    """대상 IPO 종목 목록 — 시트 'IPO종목' 탭이 유일한 원천.

    KRX 1년치 스냅샷 스캔 방식은 느리고 실패가 잦아 폐기했다(2026-07-10).
    새 종목은 운영자가 IPO종목 탭에 한 줄 추가하면 다음 배치에서 편입된다.
    """
    if args.manual_targets:
        return _without_spac_targets(load_manual_targets(), "manual_targets.json")
































    path = ROOT_DIR / "data" / "ipo_targets.json"
    if not path.exists():
        raise FileNotFoundError(
            "data/ipo_targets.json이 없습니다. 먼저 `python -m scripts.sheets_sync pull-admin`으로 "
            "시트 IPO종목 탭을 내려받으세요."
        )
    targets = json.loads(path.read_text(encoding="utf-8"))
    if not targets:
        raise ValueError("시트 IPO종목 탭이 비어 있습니다.")
    return _without_spac_targets(targets, "시트 IPO종목 탭")


def _compact_code(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(6) if digits and len(digits) <= 6 else digits


def _compact_name(value: Any) -> str:
    return "".join(str(value or "").split()).lower()


def _load_schedule_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = data.get("items") or []
    past_items = data.get("past_items") or []
    return [item for item in [*items, *past_items] if isinstance(item, dict)]


def _schedule_item_for_target(
    target: dict[str, Any],
    code: str,
    schedule_items: list[dict[str, Any]],
) -> dict[str, Any] | None:
    corp_code = str(target.get("corp_code") or "").strip()
    stock_code = _compact_code(code or target.get("code") or target.get("stock_code"))
    name_key = _compact_name(target.get("name"))
    for item in schedule_items:
        if corp_code and str(item.get("corp_code") or "").strip() == corp_code:
            return item
    for item in schedule_items:
        if stock_code and _compact_code(item.get("stock_code")) == stock_code:
            return item
    for item in schedule_items:
        if name_key and _compact_name(item.get("name")) == name_key:
            return item
    return None


def _schedule_item_has_gap(item: dict[str, Any] | None) -> bool:
    if not item:
        return True
    if item.get("withdrawn") or item.get("fixed_excluded"):
        return False
    if item.get("management_hidden") or item.get("review_pending"):
        return False
    required_fields = (
        "band_low", "band_high", "final_price",
        "forecast_start", "forecast_end", "sub_start", "sub_end",
        "underwriter", "market", "offer_shares", "demand_ratio",
    )
    if any(not item.get(field) for field in required_fields):
        return True
    if not any((row or {}).get("qty") for row in (item.get("commit_apply") or [])):
        return True
    return False


def _has_complete_admin_rows(rows: list[dict[str, Any]], category: str) -> bool:
    category_rows = [row for row in rows if row.get("category") == category]
    if not category_rows:
        return False
    for row in category_rows:
        has_date = bool(row.get("planned_date") or row.get("api_return_date") or row.get("final_date"))
        has_qty = bool(_to_int(row.get("planned_qty")) or _to_int(row.get("api_return_qty")) or _to_int(row.get("final_qty")))
        if has_date and has_qty:
            return True
    return False


def _incomplete_reparse_reasons(
    target: dict[str, Any],
    code: str,
    listing_date: str,
    existing_stock_rows: list[dict[str, Any]],
    schedule_items: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    has_ipo_price = bool(_to_int(target.get("manual_ipo_price")) or any(_to_int(row.get("ipo_price")) for row in existing_stock_rows))
    if not (target.get("name") and target.get("market") and (code or target.get("code")) and (listing_date or target.get("listing_date")) and has_ipo_price):
        reasons.append("종목관리")
    # 주의: IPO일정 탭의 빈칸은 여기서 트리거하지 않는다.
    # IPO일정 데이터는 ipo_schedule.py(refresh_ipo_schedule)가 자체 상한(MAX_BACKFILL_PER_RUN)을
    # 두고 별도 백필한다. 반면 여기서 도는 재파싱은 락업(build_ipo_events + build_float_summary_events)
    # 전용이라 IPO일정 빈칸을 절대 못 채운다. 과거엔 IPO일정 gap으로 락업을 매 배치 재파싱해
    # (미래 종목의 수요예측 미도래 등 정상 빈칸까지) 148중 92종목이 헛돌며 배치가 3시간 걸렸다.
    if not _has_complete_admin_rows(existing_stock_rows, CATEGORY_IPO):
        # 실적보고서 자체가 DART에 없다고 판정된 종목(IPO일정 파이프라인의 result_report_missing)은
        # 락업 재파싱도 허탕 확정 — 재시도하지 않는다. 수기(검토필요·수기입력)가 유일한 통로.
        schedule_item = _schedule_item_for_target(target, code, schedule_items) or {}
        report_missing = schedule_item.get("result_report_missing") and not schedule_item.get("report_rcp")
        # 확약 배정이 확인된 0(전 구간 0, 미확약 100%)인 종목은 락업 행 0개가 정상 —
        # 재파싱해도 만들 행이 없다 (데이원컴퍼니·미트박스·엠앤씨솔루션 케이스)
        alloc_tiers = [t for t in schedule_item.get("commit_alloc") or [] if isinstance(t, dict)]
        confirmed_zero_lockup = bool(alloc_tiers) and not any(
            _to_int(t.get("qty")) for t in alloc_tiers if str(t.get("period")) != "미확약"
        )
        if not report_missing and not confirmed_zero_lockup:
            reasons.append("IPO기관")
    if not _has_complete_admin_rows(existing_stock_rows, CATEGORY_FLOAT):
        reasons.append("기존주주")
    return reasons
































































def get_stock_meta(target: dict) -> tuple[str | None, dict | None, str | None]:
    """종목코드로 최근 KRX 스냅샷에서 상장주식수·종가·시장을 채운다."""
    code = normalize_stock_code(target.get("code"))
    if code:
        _, snap = latest_krx_snapshot()
        meta = snap.get(code)
        if meta:
            return code, {
                "name": target.get("name") or meta.get("name"),
                "market": target.get("market") or meta.get("market"),
                "shrs": int(meta.get("shrs") or target.get("shares") or 0),
                "close_price": int(meta.get("close_price") or target.get("close_price") or 0),
            }, None
        # 스냅샷에 코드가 없으면(거래정지 등) 저장된 값이라도 사용
        if target.get("shares"):
            return code, {
                "name": target.get("name"),
                "market": target.get("market"),
                "shrs": int(target.get("shares") or 0),
                "close_price": int(target.get("close_price") or 0),
            }, None
    return find_stock_by_name(target["name"])
































































def build_ipo_events(target: dict, code: str, meta: dict, listing_date: str, shares: int) -> list[dict]:
    name = target["name"]
    rcp = target.get("rcp")
    parsed = target.get("parsed_ipo_lockups")
    manual_ipo_price = _to_int(target.get("manual_ipo_price"))
    manual_ipo_price_locked = str(target.get("manual_ipo_price_locked") or "N").upper() == "Y"
    ipo_price = _to_int(target.get("ipo_price"))
    note = ""
    if not parsed:
        # DART 정식 사명으로 검색 — 사명 변경·동명 비상장사 문제를 종목코드 식별로 회피
        corp = get_corp_code(name, stock_code=code)
        dart_name = (corp or {}).get("corp_name") or name
        if dart_name != name:
            print(f"  [DART] 사명 보정: {name} → {dart_name}", file=sys.stderr)
        # DART 검색 시작일은 상장 전년도부터 (연말 상장 준비 공시 대비)
        search_from = f"{int(listing_date[:4]) - 1}0101" if listing_date[:4].isdigit() else None
        rcp, parsed, note, parsed_ipo_price = parse_ipo_lockup(dart_name, d0=search_from)
        ipo_price = manual_ipo_price if manual_ipo_price_locked else (parsed_ipo_price or manual_ipo_price)
    elif manual_ipo_price_locked and manual_ipo_price:
        ipo_price = manual_ipo_price
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


def build_ipo_events_from_schedule_alloc(
    target: dict,
    code: str,
    meta: dict,
    listing_date: str,
    shares: int,
    schedule_item: dict,
) -> list[dict]:
    """일정 파서가 확보한 확약 배정량으로 누락된 IPO기관 이벤트를 복구한다.

    증권발행실적보고서 표를 두 파서가 별도로 읽기 때문에 일정의 commit_alloc은
    있는데 락업 행만 없을 수 있다. 미확약은 해제 이벤트가 아니므로 제외한다.
    """
    ipo_price = _to_int(target.get("manual_ipo_price")) or _to_int(schedule_item.get("final_price"))
    rows: list[dict] = []
    for tier in schedule_item.get("commit_alloc") or []:
        if not isinstance(tier, dict):
            continue
        period = str(tier.get("period") or "").strip()
        qty = _to_int(tier.get("qty"))
        if period not in {"15일", "1개월", "3개월", "6개월"} or qty <= 0:
            continue
        date, date_display, tradable_date = calc_release_date(listing_date, period)
        rows.append({
            "event_id": build_event_id(code, CATEGORY_IPO, period, tradable_date),
            "code": code,
            "name": target.get("name") or schedule_item.get("name") or meta.get("name"),
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
            "dart_rcp": schedule_item.get("report_rcp") or "",
            "dart_source": "증권발행실적보고서(IPO일정 확약배정)",
            "parse_note": "IPO일정 확약배정값으로 누락 이벤트 자동 복구",
            "api_return_date": "",
            "api_return_qty": "",
            "api_reason": "",
            "manual_date": "",
            "manual_qty": "",
            "manual_lock": "N",
            "memo": "",
        })
    if rows:
        print(f"  [DART] IPO일정 확약배정값으로 IPO기관 이벤트 {len(rows)}건 복구", file=sys.stderr)
    return rows
































































def build_holder_lockup_events(
    target: dict, code: str, meta: dict, listing_date: str, shares: int, year: int,
) -> tuple[list[dict], list[dict]]:
    """주주별 매각제한 표에서 기간별 보호예수 이벤트를 만든다.

    누적 요약표가 없는 투자설명서용 대체 경로다. 표의 소계와 합계가 맞지 않으면
    행이 빠졌을 수 있으므로 검토필요로 올려 운영자가 확인하게 한다.
    """
    name = target["name"]
    by_period, rcept_no, note = parse_holder_lockups(
        name, expected_shares=shares, year=year, stock_code=code,
    )
    if not by_period:
        return [], []

    total = sum(by_period.values())
    # 표의 소계와 검산이 안 맞으면 부분표를 잡았을 수 있다. 그대로 쓰면 이미 있는
    # 금융위 API 데이터보다 나빠진다(유라클 48,730주 = 유통 98.9%). 물량이 상장주식수의
    # 5% 미만인 경우도 같은 증상이라 함께 막고, 검토필요로만 올린다.
    if note or (shares and total < shares * 0.05):
        reason = note or f"매각제한 합계 {total:,}주가 상장주식수의 5% 미만"
        print(f"  [DART API] 주주별 매각제한 표 신뢰 불가 — 반영 안 함 ({reason})", file=sys.stderr)
        return [], [{
            "detected_at": _now(), "event_id": "", "code": code, "name": name,
            "category": CATEGORY_FLOAT, "period": "",
            "issue": f"주주별 매각제한 표를 믿을 수 없어 반영하지 않음 — {reason}",
            "memo": "검토필요 탭의 상장일유통가능물량에 투자설명서 숫자를 적으면 해결됩니다",
        }]

    rows: list[dict] = []
    reviews: list[dict] = []
    for period, qty in sorted(by_period.items(), key=lambda kv: kv[1], reverse=True):
        try:
            date, date_display, tradable_date = calc_release_date(listing_date, period)
        except ValueError:
            reviews.append({
                "detected_at": _now(), "event_id": "", "code": code, "name": name,
                "category": CATEGORY_FLOAT, "period": period,
                "issue": f"주주별 표의 의무보유 기간 '{period}'을 해석하지 못함",
                "memo": "",
            })
            continue
        rows.append({
            "event_id": build_event_id(code, CATEGORY_FLOAT, period, tradable_date),
            "code": code, "name": name, "market": meta.get("market", ""),
            "listing_date": listing_date, "shares": shares,
            "close_price": meta.get("close_price", ""), "ipo_price": "",
            "category": CATEGORY_FLOAT, "type": "보호예수", "period": period,
            "planned_date": date,
            "planned_tradable_date": tradable_date,
            "planned_date_display": date_display,
            "planned_qty": qty,
            "planned_pct": pct(qty, shares),
            "quantity_unit": "주",
            "dart_rcp": rcept_no,
            "dart_source": "투자설명서 주주별 매각제한 내역",
            "parse_note": note,
            "api_return_date": "", "api_return_qty": "", "api_reason": "",
            "manual_date": "", "manual_qty": "", "manual_lock": "N", "memo": "",
        })
    print(
        f"  [DART API] 주주별 매각제한 이벤트 {len(rows)}건 / 합계 {total:,}주",
        file=sys.stderr,
    )
    return rows, reviews


def build_float_summary_events(target: dict, code: str, meta: dict, listing_date: str, shares: int, year: int) -> tuple[list[dict], list[dict]]:
    name = target["name"]
    chosen, candidates, note = parse_float_summary_lockups(name, expected_shares=shares, year=year, stock_code=code)
    reviews: list[dict] = []
    if not chosen:
        # 누적 요약표가 없는 투자설명서가 141종목 중 34건이다. 그런 문서는 주주별
        # 세부내역 표에 매각제한 물량과 의무보유 기간을 적으므로 그쪽에서 읽는다.
        holder_rows, holder_reviews = build_holder_lockup_events(
            target, code, meta, listing_date, shares, year,
        )
        if holder_rows:
            return holder_rows, holder_reviews
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
        period = str(row["period"] or "").strip()
        # "상장일" 행은 해제 이벤트가 아니라 유통물량의 기준선 — 위치와 무관하게 기준으로만 쓴다
        if prev is None or period in ("상장일", "상장당일", "상장 당일"):
            prev = cumulative
            continue
        inc = cumulative - prev
        prev = cumulative
        if inc <= 0:
            continue
        try:
            date, date_display, tradable_date = calc_release_date(listing_date, period)
        except ValueError as exc:
            # 표에 예상 밖 기간 표기가 나와도 배치를 죽이지 않고 검토필요로 넘긴다
            reviews.append({
                "detected_at": _now(), "event_id": "", "code": code, "name": name,
                "category": CATEGORY_FLOAT, "period": period,
                "issue": f"기간 해석 실패: {exc}", "planned_qty": inc, "memo": "유통가능 요약표 행 확인 필요",
            })
            continue
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
            "quantity_unit": row.get("quantity_unit") or "주",
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
    # 투자설명서 누적치 ≠ KRX 상장주식수는 유증·스톡옵션 등 정상 자본 변동이 대부분이라
    # 검토필요에 올리지 않는다 (각 행의 parse_note에 이미 기록되어 참고 가능)
    print(f"  [DART API] 구주·보호예수 요약 이벤트 {len(out)}건 / table={chosen.get('table_index')} / note={note or '-'}", file=sys.stderr)
    return out, reviews
































































def carry_manual_fields(new_row: dict, old: dict | None) -> dict:
    if not old:
        return new_row
    for key in ["manual_date", "manual_qty", "manual_lock", "manual_mode", "sheet_visible", "memo"]:
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
































































def sync_commit_alloc_from_lockup(schedule_path: Path, rows: list[dict]) -> None:
    """IPO기관 락업 물량을 IPO일정 확약배정(commit_alloc)이 빈 종목에 복사한다.

    두 파서가 같은 증권발행실적보고서를 따로 읽는 구조라, 락업 쪽만 성공하고
    일정 쪽 배정표 파싱이 실패하면 검토필요에 '확약배정 부족'으로 남는다.
    이미 확보된 값의 복사라 API 비용이 없고, 이후 공식 파싱이 성공하면 덮인다.
    락업 행에는 미확약 물량이 없으므로 확약 구간만 채워진다.
    """
    try:
        data = json.loads(schedule_path.read_text(encoding="utf-8"))
    except Exception:
        return
    by_code: dict[str, dict[str, int]] = {}
    for row in rows:
        if row.get("category") != CATEGORY_IPO:
            continue
        code = normalize_stock_code(row.get("code"))
        qty = _to_int(row.get("final_qty")) or _to_int(row.get("api_return_qty")) or _to_int(row.get("planned_qty"))
        period = str(row.get("period") or "").strip()
        if code and period and qty:
            merged = by_code.setdefault(code, {})
            merged[period] = merged.get(period, 0) + qty
    if not by_code:
        return
    order = {p: i for i, p in enumerate(["미확약", "15일", "1개월", "3개월", "6개월"])}
    synced: list[str] = []
    for item in [*(data.get("items") or []), *(data.get("past_items") or [])]:
        if not isinstance(item, dict):
            continue
        if any(_to_int(t.get("qty")) for t in item.get("commit_alloc") or [] if isinstance(t, dict)):
            continue
        tiers = by_code.get(normalize_stock_code(item.get("stock_code")))
        if not tiers:
            continue
        total = sum(tiers.values())
        item["commit_alloc"] = [
            {"period": p, "qty": q, "pct": round(q / total * 100, 2) if total else 0, "source": "IPO기관 락업"}
            for p, q in sorted(tiers.items(), key=lambda kv: order.get(kv[0], 99))
        ]
        synced.append(item.get("name") or "?")
    if synced:
        schedule_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[IPO일정] IPO기관 락업값 → 확약배정 복사: {len(synced)}종목 ({', '.join(synced[:10])})", file=sys.stderr)


def match_api_group_to_row(rd: str, total_qty: int, rows: list[dict]) -> dict | None:
    # 금융위 API 반환정보는 기존주주/보호예수 해제 확인용이다.
    # 증권발행실적보고서의 IPO기관 확약 물량과 주체가 달라서 같은 날짜여도 합치지 않는다.
    same_date = [r for r in rows if r.get("category") == CATEGORY_FLOAT and rd in row_match_dates(r)]
    if not same_date:
        return None
    exact = [r for r in same_date if _to_int(r.get("planned_qty")) == total_qty]
    if exact:
        return exact[0]
    # 날짜가 같으면 구주·보호예수 행만 API 수량으로 최종값을 보정한다.
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
    period = infer_lockup_period(listing_date, rd, "기타")
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
        "api_reason_breakdown": api_item.get("breakdown") or "",
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
    normalized_items = [normalize_public_return_item(x) for x in raw_items]
    target_code = normalize_stock_code(code)
    api_items = [
        item
        for item in normalized_items
        if not item.get("stock_code")
        or normalize_stock_code(item.get("stock_code")) == target_code
    ]
    logs: list[dict] = []
    reviews: list[dict] = []
    dropped = len(normalized_items) - len(api_items)
    if dropped:
        print(f"  [API] 종목코드 불일치 응답 {dropped}건 제외", file=sys.stderr)
    print(f"  [API] 금융위 반환정보 {len(api_items)}건", file=sys.stderr)
































    removed_ids = [r["event_id"] for r in rows if r.get("dart_source") == "공공데이터 API 단독"]
    rows = [r for r in rows if r.get("dart_source") != "공공데이터 API 단독"]

    for row in rows:
        if row.get("category") != CATEGORY_IPO:
            continue
        old_api_date = row.get("api_return_date") or ""
        old_api_qty = row.get("api_return_qty") or ""
        old_api_reason = row.get("api_reason") or ""
        if old_api_date or old_api_qty or old_api_reason:
            row["api_return_date"] = ""
            row["api_return_qty"] = ""
            row["api_reason"] = ""
            logs.append(log_change(row, "api_return_qty", old_api_qty, "", "IPO기관은 금융위 API 검증 대상 제외"))
































    # 금융위 API의 상장주식수(lblProtTsumIssuStckCnt)는 보호예수 등록 시점 값이라
    # 최신 KRX 값과 다른 게 정상 — 비교 기록을 만들면 노이즈만 쌓여서 사용하지 않는다.
    # 비율·시가총액의 분모는 항상 최근 거래일 KRX(current_shares)로 통일한다.
































    # 반환일 기준 합산
    groups: dict[str, dict] = {}
    for api in api_items:
        rd = api.get("return_date")
        rq = int(api.get("return_qty") or 0)
        if not rd or not rq:
            continue
        group = groups.setdefault(rd, {"qty": 0, "reasons": [], "by_reason": {}})
        group["qty"] += rq
        reason = (api.get("reason") or "").strip()
        if reason and reason not in group["reasons"]:
            group["reasons"].append(reason)
        # 같은 날 반환분을 한 행으로 합치면 "최대주주 + 벤처금융 + ..." 문자열만 남아
        # 주체별 물량이 사라진다. 종목 상세에서 펼쳐 보여주려고 내역을 따로 모은다.
        group["by_reason"][reason or "구분없음"] = group["by_reason"].get(reason or "구분없음", 0) + rq
































    for rd in sorted(groups):
        # 상장일 이전 반환은 상장 전(장외 시절) 보호예수 기록 — 락업 캘린더와 무관하므로 버린다
        if listing_date and rd < listing_date:
            continue
        total = groups[rd]["qty"]
        reason = " + ".join(groups[rd]["reasons"])
        breakdown = json.dumps(
            [{"reason": name, "qty": qty}
             for name, qty in sorted(groups[rd]["by_reason"].items(), key=lambda kv: -kv[1])],
            ensure_ascii=False,
        )
        row = match_api_group_to_row(rd, total, rows)
        if row is None:
            new_row = create_api_only_row(
                {"return_date": rd, "return_qty": total, "reason": reason, "breakdown": breakdown},
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
        row["api_reason_breakdown"] = breakdown
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
































































def _review_type(issue: str) -> str:
    if "공모가" in issue:
        return "공모가 파싱 실패"
    if "상장주식수" in issue:
        return "상장주식수 차이"
    if "수량" in issue or "물량" in issue:
        return "물량 불일치"
    if "날짜" in issue or "해제일" in issue:
        return "날짜 확인"
    if "파싱" in issue:
        return "DART 파싱 확인"
    return "데이터 확인"
































































def _review_id(row: dict) -> str:
    if row.get("review_id"):
        return str(row["review_id"])
    code = str(row.get("code") or "미상")
    issue_type = _review_type(str(row.get("issue") or row.get("review_type") or "데이터 확인"))
    event_id = str(row.get("event_id") or "")
    return f"{code}-{event_id or issue_type.replace(' ', '')}"
































































def _comparison(row: dict) -> str:
    parts: list[str] = []
    if row.get("planned_date"):
        parts.append(f"예정일 {row['planned_date']}")
    if row.get("api_return_date"):
        parts.append(f"API일 {row['api_return_date']}")
    if row.get("manual_date"):
        parts.append(f"수동일 {row['manual_date']}")
    if row.get("planned_qty") not in (None, ""):
        parts.append(f"예정 {row['planned_qty']}")
    if row.get("api_return_qty") not in (None, ""):
        parts.append(f"API {row['api_return_qty']}")
    if row.get("manual_qty") not in (None, ""):
        parts.append(f"수동 {row['manual_qty']}")
    return " / ".join(parts) or str(row.get("comparison") or "")
































































def merge_review_history(path: Path, detections: list[dict], resolved_ids: set[str] | None = None) -> list[dict]:
    """현재 문제와 과거 이력을 합친다. 해결 행도 삭제하지 않고 아래에 보존한다."""
    existing_raw: list[dict] = []
    if path.exists():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            existing_raw = [dict(row) for row in csv.DictReader(handle)]
































    history: dict[str, dict] = {}
    for old in existing_raw:
        rid = _review_id(old)
        detected = old.get("first_detected") or old.get("detected_at") or _now()
        history[rid] = {
            "review_id": rid,
            "status": old.get("status") if old.get("status") in {"미해결", "해결"} else "미해결",
            "name": old.get("name", ""), "code": old.get("code", ""),
            "review_type": old.get("review_type") or _review_type(old.get("issue", "")),
            "target": old.get("target") or " · ".join(x for x in [old.get("category", ""), old.get("period", "")] if x),
            "issue": old.get("issue", ""), "comparison": old.get("comparison") or _comparison(old),
            "first_detected": detected, "last_detected": old.get("last_detected") or detected,
            "resolved_at": old.get("resolved_at", ""),
            "operator_memo": old.get("operator_memo") or old.get("memo", ""),
            "event_id": old.get("event_id", ""),
        }
































    active_ids: set[str] = set()
    for detected in detections:
        rid = _review_id(detected)
        active_ids.add(rid)
        old = history.get(rid, {})
        detected_at = detected.get("detected_at") or _now()
        history[rid] = {
            "review_id": rid, "status": "미해결",
            "name": detected.get("name", ""), "code": detected.get("code", ""),
            "review_type": _review_type(str(detected.get("issue") or "")),
            "target": " · ".join(x for x in [detected.get("category", ""), detected.get("period", "")] if x) or "종목정보",
            "issue": detected.get("issue", ""), "comparison": _comparison(detected),
            "first_detected": old.get("first_detected") or detected_at,
            "last_detected": detected_at, "resolved_at": "",
            "operator_memo": old.get("operator_memo") or detected.get("memo", ""),
            "event_id": detected.get("event_id", ""),
        }
































    for rid, old in history.items():
        if rid not in active_ids and rid in (resolved_ids or set()) and old.get("status") == "미해결":
            old["status"] = "해결"
            old["resolved_at"] = _now()
































    return sorted(
        history.values(),
        key=lambda row: (0 if row.get("status") == "미해결" else 1, -(int(str(row.get("last_detected") or "0").replace("-", "").replace(":", "").replace(" ", "") or 0))),
    )
































































def finalize_row(row: dict) -> tuple[dict, list[dict], list[dict]]:
    logs: list[dict] = []
    reviews: list[dict] = []
    shares = _to_int(row.get("shares"))
    manual_lock = str(row.get("manual_lock") or "N").upper() == "Y"
    manual_mode = str(row.get("manual_mode") or "")
    manual_qty = _to_int(row.get("manual_qty"))
    manual_date = row.get("manual_date") or ""
    api_qty = _to_int(row.get("api_return_qty"))
    api_date = row.get("api_return_date") or ""
    if row.get("category") == CATEGORY_IPO:
        api_qty = 0
        api_date = ""
    planned_qty = _to_int(row.get("planned_qty"))
    # final_date에는 계산 원본을 넣는다. 보정된 거래가능일은 아래에서
    # release_display로 따로 구해 final_tradable_date에 저장하므로, 여기서
    # planned_tradable_date를 쓰면 원본 칸에 보정일이 들어가 두 값이 섞인다.
    # (화면의 "해제일"은 전부 final_tradable_date 쪽을 쓴다)
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
        final_date = api_date or planned_date or (manual_date if manual_mode == "임시" else "")
        if planned_qty and api_qty != planned_qty:
            status = "반환확인_API수정"
            row["review_needed"] = "N"  # 운영자가 볼 필요는 없고 로그에만 남긴다.
        else:
            status = "반환확인"
            row["review_needed"] = "N"
    elif planned_qty or planned_date or (manual_mode == "임시" and (manual_qty or manual_date)):
        used_manual = manual_mode == "임시" and (
            (not planned_qty and manual_qty) or (not planned_date and manual_date)
        )
        final_qty = planned_qty or (manual_qty if manual_mode == "임시" else 0)
        final_date = planned_date or (manual_date if manual_mode == "임시" else "")
        if used_manual:
            status = "수기임시"
            row["review_needed"] = "Y"
        else:
            status = "예정" if final_date >= datetime.today().strftime("%Y-%m-%d") else "확정(경과)"
            row["review_needed"] = row.get("review_needed") or "N"
    else:
        final_qty = planned_qty
        final_date = planned_date
        status = "확인필요"
        row["review_needed"] = "Y"
































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
    # GitHub Actions 러너는 UTC다. KRX 기준일 탐색은 한국 날짜로 시작해야
    # 자정 직후 실행에서도 전일 거래 데이터를 놓치지 않는다.
    today = datetime.now(ZoneInfo("Asia/Seoul"))
    for back in range(0, 10):
        bas_dd = (today - timedelta(days=back)).strftime("%Y%m%d")
        snap = krx_snapshot(bas_dd)
        if snap:
            close_date = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}"
            _SNAPSHOT_CACHE = (close_date, snap)
            return _SNAPSHOT_CACHE
    _SNAPSHOT_CACHE = (None, {})
    return _SNAPSHOT_CACHE
































































def refresh_market_data(rows: list[dict]) -> tuple[str | None, list[dict]]:
    """편입된 전 종목의 최근 상장주식수·종가·비율을 한 스냅샷으로 갱신한다.

    신규 감지 대상(올해 universe)에 없는 과거 연도 종목도 포함해 전부 갱신.
    반환값은 종가 기준일(YYYY-MM-DD), 최근 10일 내 거래일이 없으면 None.
    """
    close_date, snap = latest_krx_snapshot()
    if not close_date:
        print("[KRX] 최근 10일 내 거래일 스냅샷을 찾지 못해 종가 갱신을 건너뜁니다.", file=sys.stderr)
        return None, []
    # 기본정보에는 있는데 당일 시세에서 빠진 종목은 거래정지로 본다.
    # 한 시장 API가 통째로 실패한 경우에는 오탐 방지를 위해 판정하지 않는다.
    _, base_info = latest_base_info()
    previous_by_code: dict[str, dict] = {}
    previous_site_path = ROOT_DIR / "data" / "site_data.json"
    if previous_site_path.exists():
        try:
            previous_site = json.loads(previous_site_path.read_text(encoding="utf-8"))
            previous_by_code = {
                str(stock.get("code") or ""): stock
                for stock in previous_site.get("stocks", [])
                if stock.get("code")
            }
        except Exception:
            previous_by_code = {}

    def market_key(value: object) -> str:
        text = str(value or "").upper()
        if "코스닥" in text or "KOSDAQ" in text:
            return "KOSDAQ"
        if "코스피" in text or "KOSPI" in text:
            return "KOSPI"
        return text

    received_markets = {market_key(meta.get("market")) for meta in snap.values() if meta.get("market")}
    updated = 0
    logs: list[dict] = []
    for row in rows:
        code = str(row.get("code") or "")
        meta = snap.get(code)
        if not meta:
            base = base_info.get(code) or {}
            row_market = market_key(row.get("market") or base.get("market"))
            previous = previous_by_code.get(code) or {}
            # 해당 시장 시세가 정상 수신됐을 때만 '종목 누락=거래정지'로 판정한다.
            # 시장 API 전체가 실패한 날은 직전 상태를 유지해 오탐 해제를 막는다.
            if base and row_market in received_markets:
                suspended = True
            elif base and row_market not in received_markets:
                suspended = previous.get("trading_suspended") is True
            else:
                suspended = False
            row["trading_suspended"] = suspended
            if suspended:
                row["trading_suspended_since"] = previous.get("trading_suspended_since") or close_date
            else:
                row["trading_suspended_since"] = ""
            continue
        previous = previous_by_code.get(code) or {}
        # KRX 일별시세에는 거래정지 종목도 직전 종가로 남을 수 있다.
        # 당일 누적거래량 0을 함께 확인해야 오래된 종가를 현재 수익률로 오인하지 않는다.
        volume = meta.get("volume")
        suspended = (
            _to_int(volume) == 0
            if volume is not None
            else previous.get("trading_suspended") is True
        )
        row["trading_suspended"] = suspended
        row["trading_suspended_since"] = (
            previous.get("trading_suspended_since") or close_date
            if suspended
            else ""
        )
        current_shares = _to_int(meta.get("shrs"))
        if current_shares:
            old_shares = _to_int(row.get("current_shares")) or _to_int(row.get("shares"))
            if old_shares != current_shares:
                logs.append(log_change(row, "current_shares", old_shares, current_shares, f"KRX 최근 상장주식수 갱신 ({close_date})"))
            row["current_shares"] = current_shares
            row["shares_date"] = close_date
            row["planned_pct"] = pct(_to_int(row.get("planned_qty")), current_shares)
            row["final_pct"] = pct(_to_int(row.get("final_qty")), current_shares)
        if meta.get("close_price"):
            row["close_price"] = meta["close_price"]
        if meta.get("market_cap"):
            row["market_cap"] = meta["market_cap"]
        updated += 1
    print(f"[KRX] 상장주식수·종가·비율 갱신: {updated}개 행 / 기준일 {close_date}", file=sys.stderr)
    return close_date, logs
































































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
        normalize_stock_code(r.get("code")): r.get("listing_date") or ""
        for r in existing_rows
        if r.get("code") and r.get("listing_date")
    }
    target_by_code: dict[str, dict] = {}
    meta_by_code: dict[str, dict] = {}
    for existing in existing_rows:
        existing_code = normalize_stock_code(existing.get("code"))
        if not existing_code or existing_code in meta_by_code:
            continue
        meta_by_code[existing_code] = {
            "name": existing.get("name") or "",
            "market": existing.get("market") or "",
            "shrs": _to_int(existing.get("current_shares") or existing.get("shares")),
            "close_price": _to_int(existing.get("close_price")),
        }
    target_path = ROOT_DIR / "data" / "ipo_targets.json"
    if target_path.exists():
        for target in json.loads(target_path.read_text(encoding="utf-8")):
            target_code = normalize_stock_code(target.get("code"))
            if target_code:
                target_by_code[target_code] = target
                if target.get("listing_date"):
                    listing_by_code.setdefault(target_code, target.get("listing_date") or "")
































    for entry in entries:
        code = normalize_stock_code(entry.get("code"))
        category = MANUAL_CATEGORY_MAP.get(str(entry.get("category") or "").strip())
        period = str(entry.get("period") or "").strip()
        date = str(entry.get("date") or "").strip()
        qty = _to_int(entry.get("qty"))
































        # 종목코드 발급 전 캡처값은 시트 보존용이다. 공식 DART 파싱이 가능한
        # 시점까지 오류로 반복 알림하지 않는다.
        if not code and entry.get("pending_only"):
            continue
        if not code:
            review(entry, "종목코드가 비어 있음")
            continue
        if not category:
            review(entry, "구분은 IPO기관 또는 기존주주여야 함")
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            review(entry, "해제일은 YYYY-MM-DD 형식이어야 함")
            continue
        if period in GENERIC_PERIOD_LABELS:
            period = infer_lockup_period(listing_by_code.get(code, ""), date, period)
        if not period or period in GENERIC_PERIOD_LABELS:
            review(entry, "락업기간을 상장일과 해제일로 계산하지 못함")
            continue
        if qty <= 0:
            review(entry, "물량은 0보다 큰 숫자여야 함")
            continue
































        meta = meta_by_code.get(code)
        if not meta:
            _, snap = latest_krx_snapshot()
            meta = snap.get(code)
        if not meta:
            target = target_by_code.get(code, {})
            target_name = target.get("name") or ""
            if target_name:
                found_code, found_meta, _ = find_stock_by_name(target_name)
                if found_code and found_meta:
                    code = normalize_stock_code(found_code)
                    meta = found_meta
                    if target.get("listing_date"):
                        listing_by_code.setdefault(code, target.get("listing_date") or "")
        if not meta:
            review(entry, "KRX에서 종목코드를 찾지 못함 (코드/종목명 확인)")
            continue
































        shares = _to_int(meta.get("shrs"))
        stock_snapshot = next(
            (existing for existing in existing_rows if normalize_stock_code(existing.get("code")) == code),
            {},
        )
        planned_date = date
        tradable_date = date
        listing_date = listing_by_code.get(code, "")
        if listing_date and period:
            try:
                calculated_date, _display_date, calculated_tradable = calc_release_date(listing_date, period)
                # 수기 탭은 종전부터 거래가능일을 입력값으로 사용해 왔다. 계산값과
                # 일치하면 원래 해제일과 거래가능일을 분리해 시트에 정확히 표시한다.
                if date == calculated_tradable:
                    planned_date = calculated_date
                    tradable_date = calculated_tradable
            except (TypeError, ValueError):
                pass
        event_id = build_event_id(code, category, period, date)
        row = {
            "event_id": event_id,
            "code": code,
            "name": meta.get("name"),
            "market": meta.get("market"),
            "listing_date": listing_date,
            "shares": shares,
            "current_shares": _to_int(stock_snapshot.get("current_shares")) or shares,
            "shares_date": stock_snapshot.get("shares_date") or "",
            "close_price": _to_int(meta.get("close_price")),
            "ipo_price": _to_int(stock_snapshot.get("ipo_price")),
            "category": category,
            "type": "IPO확약" if category == CATEGORY_IPO else "보호예수",
            "period": period,
            "planned_date": planned_date,
            "planned_tradable_date": tradable_date,
            "planned_date_display": tradable_date,
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
            "manual_lock": str(entry.get("manual_lock") or "N"),
            "manual_mode": "고정" if str(entry.get("manual_lock") or "N").upper() == "Y" else "임시",
            "sheet_visible": str(entry.get("sheet_visible") or "Y"),
            "memo": "",
        }
        # 재실행 시 기존 행의 API 확인값·수동 수정값을 유지한다
        previous = existing_by_id.get(event_id)
        if previous:
            for key in ("api_return_date", "api_return_qty", "api_reason"):
                if previous.get(key) not in (None, ""):
                    row[key] = previous[key]
        row = carry_manual_fields(row, previous)
































        row = normalize_row_period(row)
        finalized, f_reviews, f_logs = finalize_row(row)
        reviews.extend(f_reviews)
        logs.extend(f_logs)
        if event_id not in existing_by_id:
            logs.append(log_change(finalized, "event", "", "수기입력 이벤트 추가", "시트 수기입력 탭 반영"))
        all_rows_by_id[event_id] = finalized
        print(f"  [수기입력] {meta.get('name')}({code}) {period} {date} {qty:,}주 편입", file=sys.stderr)
































    return reviews, logs
































































LISTING_DAY_PATH = ROOT_DIR / "data" / "listing_day.json"


def refresh_listing_day_snapshot(rows: list[dict]) -> dict[str, dict]:
    """상장일 당일의 KRX 시세를 종목별로 캐시한다.

    site_data의 shares(최초 편입 시점 주식수)는 배치가 그 종목을 처음 담은 날의 값이라
    상장일과 다를 수 있다. 랭킹의 "공모가 대비 상장일 종가" 계산과 정확한 상장일
    주식수를 위해 상장일 스냅샷을 직접 받아 둔다.

    같은 상장일 종목은 한 번만 호출하고, 한 번 받은 종목은 캐시에서 재사용한다.
    """
    cache: dict[str, dict] = {}
    if LISTING_DAY_PATH.exists():
        try:
            cache = json.loads(LISTING_DAY_PATH.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    wanted: dict[str, set[str]] = {}
    for row in rows:
        code = normalize_stock_code(row.get("code"))
        listing = str(row.get("listing_date") or "").strip()
        if not code or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", listing):
            continue
        cached = cache.get(code)
        if cached and cached.get("listing_date") == listing:
            continue  # 이미 받은 종목 — 상장일이 바뀐 경우에만 다시 받는다
        wanted.setdefault(listing.replace("-", ""), set()).add(code)

    if not wanted:
        return cache

    print(f"[KRX] 상장일 시세 조회: {len(wanted)}일 / {sum(len(v) for v in wanted.values())}종목", file=sys.stderr)
    filled = 0
    for bas_dd in sorted(wanted):
        try:
            snapshot = krx_snapshot(bas_dd)
        except Exception as exc:
            print(f"  [KRX] {bas_dd} 조회 실패(무시): {redact_sensitive_text(exc)}", file=sys.stderr)
            continue
        if not snapshot:
            continue
        listing = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
        for code in wanted[bas_dd]:
            meta = snapshot.get(code)
            if not meta:
                continue  # 상장 당일 시세에 없으면(신규 코드 반영 지연 등) 다음 배치에서 재시도
            cache[code] = {
                "listing_date": listing,
                "close_price": _to_int(meta.get("close_price")),
                "shares": _to_int(meta.get("shrs")),
            }
            filled += 1
    if filled:
        LISTING_DAY_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[KRX] 상장일 시세 저장: {filled}종목 (누적 {len(cache)})", file=sys.stderr)
    return cache


PRICE_ADJUST_PATH = ROOT_DIR / "data" / "price_adjustments.json"
LISTING_FLOAT_PATH = ROOT_DIR / "data" / "listing_float.json"


def refresh_listing_float(rows: list[dict]) -> dict[str, dict]:
    """투자설명서 본문이 직접 밝힌 상장 직후 유통가능물량을 캐시한다.

    "상장예정주식수 N주 중 약 X%에 해당하는 M주는 상장 직후 유통가능물량입니다"라는
    문장이다. 표를 못 읽은 종목도 이 문장은 있는 경우가 있어 마지막 보루로 쓴다.
    한 번 찾으면 다시 조회하지 않는다(상장 시점 값이라 바뀌지 않는다).
    """
    cache: dict[str, dict] = {}
    if LISTING_FLOAT_PATH.exists():
        try:
            cache = json.loads(LISTING_FLOAT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}

    seen: set[str] = set()
    filled = 0
    for row in rows:
        code = normalize_stock_code(row.get("code"))
        listing = str(row.get("listing_date") or "")
        if not code or code in seen or code in cache or not listing:
            continue
        seen.add(code)
        try:
            total, free, ratio, note = parse_listing_float_sentence(
                row.get("name") or "", year=int(listing[:4]), stock_code=code,
            )
        except Exception as exc:
            print(f"  [DART] {row.get('name')} 유통가능 문장 조회 실패: {redact_sensitive_text(exc)}", file=sys.stderr)
            continue
        if not (total and free):
            continue
        cache[code] = {"total_shares": total, "float_shares": free, "float_pct": ratio}
        filled += 1
    if filled:
        LISTING_FLOAT_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[DART] 상장 직후 유통가능물량 저장: {filled}종목 (누적 {len(cache)})", file=sys.stderr)
    return cache


RELEASE_DAY_PATH = ROOT_DIR / "data" / "release_day.json"
MAX_RELEASE_DAYS_PER_RUN = 80


def refresh_release_day_prices(rows: list[dict]) -> dict[str, dict]:
    """확약 해제일 당일의 종가·등락률을 캐시한다 (락업 랭킹용).

    등락률은 우리가 종가끼리 나누지 않고 거래소가 준 FLUC_RT를 그대로 쓴다.
    권리락이 낀 날은 전일 종가가 아니라 기준가 대비로 계산돼야 맞는데,
    그 판단은 거래소 값이 이미 하고 있다.

    같은 날짜는 한 번만 호출하고 받은 종목은 재사용한다. 최초 채움이 260일
    가까이 되므로 한 배치에서 처리할 날짜 수에 상한을 둬 배치가 길어지지 않게 한다.
    """
    cache: dict[str, dict] = {}
    if RELEASE_DAY_PATH.exists():
        try:
            cache = json.loads(RELEASE_DAY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}

    today = datetime.today().strftime("%Y-%m-%d")
    wanted: dict[str, set[str]] = {}
    for row in rows:
        if row.get("category") != CATEGORY_IPO:
            continue
        code = normalize_stock_code(row.get("code"))
        released = str(row.get("final_tradable_date") or row.get("planned_tradable_date") or "").strip()
        if not code or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", released) or released > today:
            continue
        if (cache.get(code) or {}).get(released) is not None:
            continue
        wanted.setdefault(released.replace("-", ""), set()).add(code)

    if not wanted:
        return cache

    targets = sorted(wanted, reverse=True)[:MAX_RELEASE_DAYS_PER_RUN]
    skipped = len(wanted) - len(targets)
    print(
        f"[KRX] 해제일 시세 조회: {len(targets)}일 / {sum(len(wanted[d]) for d in targets)}건"
        + (f" (남은 {skipped}일은 다음 배치)" if skipped else ""),
        file=sys.stderr,
    )
    filled = 0
    for bas_dd in targets:
        released = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
        # 해제일이 휴장일로 굳어 있으면(휴장일 탭에 그 해가 없던 시절 계산된 값)
        # 그 날짜 스냅샷이 통째로 비어 영영 못 채운다. 다음 거래일까지 밀어 가며 찾는다.
        snapshot = None
        probe = bas_dd
        for _ in range(7):
            try:
                snapshot = krx_snapshot(probe)
            except Exception as exc:
                print(f"  [KRX] {probe} 조회 실패(무시): {redact_sensitive_text(exc)}", file=sys.stderr)
                snapshot = None
            if snapshot:
                break
            probe = (datetime.strptime(probe, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
        if not snapshot:
            continue
        if probe != bas_dd:
            print(f"  [KRX] {released}는 휴장일 — {probe[:4]}-{probe[4:6]}-{probe[6:]} 시세로 대체", file=sys.stderr)
        for code in wanted[bas_dd]:
            meta = snapshot.get(code)
            if not meta:
                continue
            cache.setdefault(code, {})[released] = {
                "close": _to_int(meta.get("close_price")),
                "fluc_rt": _to_float(meta.get("fluc_rt")),
                "prev_diff": _to_int(meta.get("prev_diff")),
            }
            filled += 1
    if filled:
        RELEASE_DAY_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[KRX] 해제일 시세 저장: {filled}건 (누적 {sum(len(v) for v in cache.values())})", file=sys.stderr)
    return cache


def _parse_reason_breakdown(value: object) -> list[dict]:
    """CSV에 JSON 문자열로 저장된 사유별 물량 내역을 되살린다.

    운영자가 시트에서 실수로 건드려 깨질 수 있으므로 파싱 실패는 조용히 무시한다.
    """
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        {"reason": str(item.get("reason") or ""), "qty": _to_int(item.get("qty"))}
        for item in parsed
        if isinstance(item, dict) and _to_int(item.get("qty"))
    ]


def rows_to_site_data(
    rows: list[dict],
    price_date: str | None = None,
    management_rows: list[dict] | None = None,
) -> dict:
    def managed_name(value: object) -> str:
        return re.sub(r"[\s㈜()\[\]]|주식회사", "", str(value or ""))

    listing_day: dict[str, dict] = {}
    if LISTING_DAY_PATH.exists():
        try:
            listing_day = json.loads(LISTING_DAY_PATH.read_text(encoding="utf-8"))
        except Exception:
            listing_day = {}

    release_day: dict[str, dict] = {}
    if RELEASE_DAY_PATH.exists():
        try:
            release_day = json.loads(RELEASE_DAY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            release_day = {}

    listing_float: dict[str, dict] = {}
    if LISTING_FLOAT_PATH.exists():
        try:
            listing_float = json.loads(LISTING_FLOAT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            listing_float = {}

    # KRX 등락률로 역산한 권리락 조정계수. 토스 수정주가와 18종목 전부 일치했고
    # 허용 IP 등록이 필요 없어 Actions에서도 돈다.
    price_adjust: dict[str, dict] = {}
    if PRICE_ADJUST_PATH.exists():
        try:
            price_adjust = json.loads(PRICE_ADJUST_PATH.read_text(encoding="utf-8")).get("stocks") or {}
        except (OSError, json.JSONDecodeError):
            price_adjust = {}

    hidden_codes: set[str] = set()
    hidden_names: set[str] = set()
    # 종목별 분석 콘텐츠 링크 — 종목관리 탭의 콘텐츠링크 열(운영자 입력)
    content_by_code: dict[str, str] = {}
    content_by_name: dict[str, str] = {}
    adjustment_by_code: dict[str, dict] = {}
    adjustment_by_name: dict[str, dict] = {}
    management_path = ROOT_DIR / "data" / "stock_management.json"
    if management_rows is not None or management_path.exists():
        try:
            commands = management_rows if management_rows is not None else json.loads(management_path.read_text(encoding="utf-8"))
            for command in commands:
                adjustment = {
                    "adjusted_ipo_price": _to_float(command.get("adjusted_ipo_price")),
                    "ipo_adjustment_factor": _to_float(command.get("ipo_adjustment_factor")),
                    "ipo_adjustment_checked_at": str(command.get("ipo_adjustment_checked_at") or ""),
                }
                if adjustment["adjusted_ipo_price"] > 0:
                    if command.get("stock_code"):
                        adjustment_by_code[normalize_stock_code(command.get("stock_code"))] = adjustment
                    if command.get("name"):
                        adjustment_by_name[managed_name(command.get("name"))] = adjustment
                url = str(command.get("content_url") or "").strip()
                if url:
                    if command.get("stock_code"):
                        content_by_code[normalize_stock_code(command.get("stock_code"))] = url
                    if command.get("name"):
                        content_by_name[managed_name(command.get("name"))] = url
                if command.get("visibility") != "비공개":
                    continue
                if command.get("stock_code"):
                    hidden_codes.add(normalize_stock_code(command.get("stock_code")))
                if command.get("name"):
                    hidden_names.add(managed_name(command.get("name")))
        except Exception:
            pass
    stocks_map: dict[str, dict] = {}
    for r in rows:
        if str(r.get("sheet_visible") or "Y").upper() == "N":
            continue
        if normalize_stock_code(r.get("code")) in hidden_codes or managed_name(r.get("name")) in hidden_names:
            continue
        final_qty = _to_int(r.get("final_qty"))
        final_date = r.get("final_date") or r.get("planned_date")
        final_tradable = r.get("final_tradable_date") or r.get("planned_tradable_date") or final_date
        if not final_qty or not final_date:
            continue
        code = r["code"]
        adjustment = adjustment_by_code.get(normalize_stock_code(code)) or adjustment_by_name.get(managed_name(r.get("name"))) or {}
        stock = stocks_map.setdefault(code, {
            "code": code,
            "name": r.get("name"),
            "market": r.get("market"),
            "listing_date": r.get("listing_date"),
            # 홈페이지의 비율·시가총액은 최근 KRX 상장주식수를 기준으로 통일한다.
            "shares": _to_int(r.get("current_shares")) or _to_int(r.get("shares")),
            # 공모가 기준 시가총액 산출용 — 상장 시점 주식수(증자 반영 전).
            # 상장일 스냅샷이 있으면 그 값이 정확하므로 우선 사용한다.
            "initial_shares": _to_int((listing_day.get(code) or {}).get("shares")) or _to_int(r.get("shares")),
            # 상장일 종가 — 공모가 대비 상장일 수익률(시초 성과) 계산용
            "listing_close": _to_int((listing_day.get(code) or {}).get("close_price")),
            # 투자설명서 본문이 직접 밝힌 상장 직후 유통가능물량 (기관 확약 포함 기준)
            "listing_float_shares": _to_int((listing_float.get(code) or {}).get("float_shares")),
            "close_price": _to_int(r.get("close_price")),
            "trading_suspended": r.get("trading_suspended") is True,
            "trading_suspended_since": str(r.get("trading_suspended_since") or ""),
            # KRX 일별매매정보의 MKTCAP을 우선 사용하고, 미제공 시에만 계산한다.
            "market_cap": _to_int(r.get("market_cap")) or (
                (_to_int(r.get("current_shares")) or _to_int(r.get("shares"))) * _to_int(r.get("close_price"))
            ),
            "ipo_price": 0,
            "adjusted_ipo_price": adjustment.get("adjusted_ipo_price") or 0,
            "ipo_adjustment_factor": adjustment.get("ipo_adjustment_factor") or 0,
            "ipo_adjustment_checked_at": adjustment.get("ipo_adjustment_checked_at") or "",
            "content_url": content_by_code.get(normalize_stock_code(code))
            or content_by_name.get(managed_name(r.get("name")))
            or "",
            "events": [],
            "holders": [],
        })
        if not stock["ipo_price"] and _to_int(r.get("ipo_price")):
            stock["ipo_price"] = _to_int(r.get("ipo_price"))
        release_price = (release_day.get(normalize_stock_code(code)) or {}).get(final_tradable) or {}
        stock["events"].append({
            "period": r.get("period"),
            "date": final_date,
            "date_display": r.get("final_date_display") or r.get("planned_date_display") or final_date,
            "tradable_date": final_tradable,
            "qty": final_qty,
            "unit": r.get("quantity_unit") or "주",
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
            # 같은 날 해제분의 주체별 물량 (최대주주·벤처금융·스톡옵션 등)
            "reason_breakdown": _parse_reason_breakdown(r.get("api_reason_breakdown")),
            # 해제일 당일 종가·등락률 (거래소 FLUC_RT — 락업 랭킹용)
            **(
                {
                    "release_close": _to_int(release_price.get("close")),
                    "release_fluc_rt": _to_float(release_price.get("fluc_rt")),
                }
                if release_price
                else {}
            ),
        })
    for stock in stocks_map.values():
        stock["events"] = sorted(stock["events"], key=lambda e: e["tradable_date"])
        # 조정계수는 KRX 역산값을 우선한다. 시트(토스) 값은 갱신이 수동이라 뒤처진다.
        entry = price_adjust.get(normalize_stock_code(stock["code"])) or {}
        factor = _to_float(entry.get("factor"))
        if factor and abs(factor - 1) > 1e-6:
            stock["ipo_adjustment_factor"] = factor
            if stock.get("ipo_price"):
                stock["adjusted_ipo_price"] = round(stock["ipo_price"] * factor, 4)
            events = entry.get("events") or []
            stock["adjustment_events"] = [
                {"date": str(e.get("date") or ""), "factor": _to_float(e.get("factor"))}
                for e in events
                if isinstance(e, dict)
            ]
            if events:
                stock["ipo_adjustment_checked_at"] = str(events[-1].get("date") or "")
    # updated = 종가 기준일 (시가총액 표기의 기준). 종가 갱신 실패 시에만 실행일로 대체.
    return {
        "updated": price_date or datetime.today().strftime("%Y-%m-%d"),
        "shares_updated": price_date or datetime.today().strftime("%Y-%m-%d"),
        "stocks": list(stocks_map.values()),
    }
































































def build_dart_rows_or_preserve(
    target: dict,
    code: str,
    meta: dict,
    listing_date: str,
    shares: int,
    existing_stock_rows: list[dict],
    existing_by_id: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """DART 재파싱 실패 시 기존 행을 보존해 호출부가 API 보강을 계속할 수 있게 한다."""
    name = target["name"]
    reviews: list[dict] = []
    try:
        stock_rows = build_ipo_events(target, code, meta, listing_date, shares)
        float_rows, float_reviews = build_float_summary_events(
            target, code, meta, listing_date, shares, int(listing_date[:4])
        )
        stock_rows.extend(float_rows)
        reviews.extend(float_reviews)
        if target.get("operator_forced_ipo") and not any(
            row.get("category") == CATEGORY_IPO for row in stock_rows
        ):
            reviews.append({
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
        return [
            carry_manual_fields(row, existing_by_id.get(row["event_id"]))
            for row in stock_rows
        ], reviews
    except Exception as dart_exc:
        # DART 장애가 금융위 API 보강까지 막지 않도록 기존 행을 보존하고 계속한다.
        # 기존 행이 없는 신규 종목도 빈 행 목록으로 API 단독 이벤트 생성을 시도한다.
        print(
            f"  [DART ERROR] {name} 파싱 실패 → 기존값 유지, API 조회 계속: {dart_exc}",
            file=sys.stderr,
        )
        reviews.append({
            "detected_at": _now(),
            "event_id": "",
            "code": code,
            "name": name,
            "category": "DART처리오류",
            "period": "",
            "issue": f"DART 파싱 실패 — 기존값 유지 후 금융위 API 보강 계속: {dart_exc}",
            "planned_date": "",
            "planned_qty": "",
            "api_return_date": "",
            "api_return_qty": "",
            "manual_date": "",
            "manual_qty": "",
            "memo": "다음 배치에서 DART 자동 재시도됨",
        })
        return [dict(row) for row in existing_stock_rows], reviews


def discard_stale_listing_date_rows(
    rows: list[dict], targets: list[dict]
) -> tuple[list[dict], dict[str, dict[str, object]]]:
    """Remove automatic events created with an obsolete listing date.

    Event IDs include the calculated release date.  Before listing dates became
    authoritative in the management sheet, correcting a listing date therefore
    created a second set of events while the old set survived under different
    IDs.  Those rows must not participate in the KRX listing-day snapshot: one
    stock with two listing dates otherwise makes the cache flip between them.

    Rows whose source is the manual-entry sheet are preserved so an operator
    decision is never deleted silently.
    """
    listing_by_code = {
        normalize_stock_code(target.get("code")): str(target.get("listing_date") or "").strip()
        for target in targets
        if normalize_stock_code(target.get("code"))
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(target.get("listing_date") or "").strip())
    }
    listing_by_name = {
        _compact_name(target.get("name")): str(target.get("listing_date") or "").strip()
        for target in targets
        if _compact_name(target.get("name"))
        and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(target.get("listing_date") or "").strip())
    }

    kept: list[dict] = []
    removed: dict[str, dict[str, object]] = {}
    for row in rows:
        canonical = listing_by_code.get(normalize_stock_code(row.get("code")))
        if not canonical:
            canonical = listing_by_name.get(_compact_name(row.get("name")))
        current = str(row.get("listing_date") or "").strip()
        # IPO기관/기존주주 탭의 고정은 물량·날짜 보존용이다. 자동 DART 행이
        # 잘못된 상장일로 생성된 사실까지 고정하는 뜻은 아니므로, 실제 수기입력
        # 출처만 예외로 둔다.
        operator_owned = str(row.get("dart_source") or "").strip() == "수기입력"
        if canonical and current and current != canonical and not operator_owned:
            key = normalize_stock_code(row.get("code")) or _compact_name(row.get("name"))
            stat = removed.setdefault(
                key,
                {"name": row.get("name") or "", "canonical": canonical, "dates": set(), "count": 0},
            )
            stat["dates"].add(current)
            stat["count"] += 1
            continue
        kept.append(row)
    return kept, removed


def main() -> None:
    require_env()
    args = parse_args()
    data_dir = ROOT_DIR / "data"
    admin_path = data_dir / "lockup_admin.csv"
    review_path = data_dir / "review_needed.csv"
    log_path = data_dir / "lockup_log.csv"
































    # IPO일정의 실적보고서 배정표를 먼저 갱신해야 같은 실행에서 IPO기관 이벤트와
    # 홈페이지까지 이어진다. 예전 순서는 사이트 저장 뒤 일정 갱신이라 최소 두 번의
    # 배치가 필요했고, 당일 상장 종목은 첫 배치에서 빈 상태로 보였다.
    try:
        from scripts.sources.ipo_schedule import refresh_ipo_schedule

        schedule_snap_date, schedule_snap = latest_krx_snapshot()
        schedule_base_date, schedule_base = latest_base_info()
        refresh_ipo_schedule(
            krx_snapshot=schedule_snap,
            krx_trading_date=schedule_snap_date or schedule_base_date,
            krx_base_info=schedule_base,
            backfill_all=bool(getattr(args, "backfill_all", False)),
        )
        schedule_pre_refreshed = True
    except Exception as exc:
        print(
            f"[IPO일정] 선행 갱신 실패(기존 스냅샷으로 계속): {redact_sensitive_text(exc)}",
            file=sys.stderr,
        )

    existing_rows = _read_csv(admin_path, ADMIN_COLUMNS)
    targets = load_targets(args)
    existing_rows, stale_listing_rows = discard_stale_listing_date_rows(existing_rows, targets)
    existing_by_id = {r["event_id"]: r for r in existing_rows if r.get("event_id")}
    schedule_items = _load_schedule_items(data_dir / "ipo_schedule.json")
    all_rows_by_id: dict[str, dict] = {r["event_id"]: r for r in existing_rows if r.get("event_id")}
    all_reviews: list[dict] = []
    all_logs: list[dict] = []

    for key, info in stale_listing_rows.items():
        old_dates = ", ".join(sorted(info["dates"]))
        all_logs.append({
            "event_id": "", "code": key if len(key) == 6 else "", "name": info["name"],
            "field": "상장일 정정 중복 제거", "old_value": old_dates,
            "new_value": info["canonical"],
            "reason": f"관리 상장일과 다른 자동 이벤트 {info['count']}건 제거",
            "updated_at": _now(),
        })
        print(
            f"[BUILD] 상장일 정정 중복 제거: {info['name']} "
            f"{old_dates} → {info['canonical']} ({info['count']}건)",
            file=sys.stderr,
        )

    # IPO종목 탭에서 삭제된 종목의 락업 이벤트를 정리한다.
    # 규칙: 기존 lockup_admin.csv에 이벤트가 있는데 targets에 없으면 → 그 종목의 모든 이벤트 제거.
    # 사용자가 IPO종목 탭에서 행을 지우면 락업 캘린더에서도 자연 정리되도록 하는 유일한 창구.
    target_codes = {str(t.get("code") or "").strip() for t in targets if (t.get("code") or "").strip()}
    target_names = {(t.get("name") or "").strip() for t in targets if (t.get("name") or "").strip()}
    removed_codes: dict[str, dict[str, int]] = {}
    for event_id, row in list(all_rows_by_id.items()):
        row_code = str(row.get("code") or "").strip()
        row_name = (row.get("name") or "").strip()
        # 코드로 우선 매칭, 그도 없으면 이름 fallback (구코드 종목 방어)
        in_targets = (row_code and row_code in target_codes) or (not row_code and row_name in target_names)
        if in_targets:
            continue
        stat = removed_codes.setdefault(row_code or row_name, {"name": row_name, "count": 0})
        stat["count"] += 1
        all_rows_by_id.pop(event_id, None)

    if removed_codes:
        # 변경로그 + IPO일정 정정이력에도 크로스 기록해 운영자가 한 곳에서 확인 가능하게 한다.
        from datetime import date as _date

        today_iso = _date.today().isoformat()
        for key, info in removed_codes.items():
            all_logs.append({
                "event_id": "", "code": key if key.isdigit() else "",
                "name": info["name"], "field": "IPO종목 삭제",
                "old_value": f"{info['count']}건 이벤트", "new_value": "",
                "reason": "IPO종목 탭에서 삭제 감지 — 관련 락업 이벤트 전면 제거",
                "updated_at": today_iso,
            })
            print(f"[BUILD] IPO종목 삭제 감지: {info['name']} — 락업 이벤트 {info['count']}건 제거", file=sys.stderr)

        # IPO일정 정정이력 탭에도 반영 (운영자가 락업·IPO일정 한 곳에서 확인 가능하도록)
        try:
            schedule_path = ROOT_DIR / "data" / "ipo_schedule.json"
            if schedule_path.exists():
                schedule_data = json.loads(schedule_path.read_text(encoding="utf-8"))
                schedule_data.setdefault("history", [])
                for info in removed_codes.values():
                    schedule_data["history"].append({
                        "date": today_iso, "name": info["name"], "type": "IPO종목 삭제",
                        "field": "락업 이벤트",
                        "old": f"{info['count']}건 게시 중", "new": "전면 제거",
                    })
                schedule_path.write_text(json.dumps(schedule_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(
                f"[BUILD] IPO일정 정정이력 크로스 기록 실패(무시): {redact_sensitive_text(exc)}",
                file=sys.stderr,
            )
































    print(f"[BUILD] 대상 IPO 종목 {len(targets)}개", file=sys.stderr)
    processed_codes: set[str] = set()
    new_ingested = 0
    skipped_new = 0
    # 배치가 느려졌을 때 어느 종목·어느 단계가 먹었는지 로그만 보고 알 수 있게 시간을 잰다.
    phase_seconds: dict[str, float] = {}
    stock_seconds: list[tuple[float, str]] = []
    loop_started = time.perf_counter()
    for idx, target in enumerate(targets, start=1):
        name = target["name"]
        listing_date = target["listing_date"]
        stock_started = time.perf_counter()
        print(f"[BUILD] {idx}/{len(targets)} {name}", file=sys.stderr)
        code = str(target.get("code") or "")
        # 종목코드와 상장일이 모두 없는 예비 IPO는 아직 KRX에 존재하지 않는다.
        # 최근 거래일을 반복 검색해도 찾을 수 없으므로 락업 단계에서는 건너뛴다.
        if not code.strip() and not str(listing_date or "").strip():
            print(f"  [KRX] 상장 전 예비 IPO → 락업 검색 생략: {name}", file=sys.stderr)
            continue
        # 종목 하나에서 어떤 예외가 나도 배치 전체가 죽지 않게 격리한다.
        # (#11 실패 원인: 와이제이링크 요약표의 '상장일' 행이 예외를 던져 137종목 배치가 통째로 중단)
        try:
            code, meta, bas_dd = get_stock_meta(target)
            if not code or not meta:
                print(f"  [KRX] 종목 검색 실패: {name}", file=sys.stderr)
                continue
            shares = int(meta.get("shrs") or target.get("shares") or 0)
            existing_stock_rows = rows_for_stock(existing_rows, code)
































            # 실행당 신규 편입 상한 — 한 번에 너무 많이 물면 타임아웃으로 통째로 날아가므로
            # 상한을 넘는 신규 종목은 건드리지 않고 다음 배치가 이어서 처리한다
            if not existing_stock_rows and args.max_new and new_ingested >= args.max_new:
                skipped_new += 1
                continue
            if not existing_stock_rows:
                new_ingested += 1
            processed_codes.add(code)
































            # IPO종목 탭에 있다 = 공모주라는 운영자 판정 → 실적보고서가 반드시 존재하므로
            # IPO기관 행이 아직 없는 종목(일시적 DART 실패 등)은 찾을 때까지 매 배치 재시도한다
            has_ipo_rows = any(row.get("category") == CATEGORY_IPO for row in existing_stock_rows)
            incomplete_reasons = (
                _incomplete_reparse_reasons(target, code, listing_date, existing_stock_rows, schedule_items)
                if args.reparse_incomplete
                else []
            )
            if existing_stock_rows and not args.reparse_existing and has_ipo_rows and not incomplete_reasons:
                print(f"  [DART] 기존 편입 종목 → DART 재파싱 생략, API 검증만 수행", file=sys.stderr)
                stock_rows = [dict(r) for r in existing_stock_rows]
            else:
                if incomplete_reasons and not args.reparse_existing:
                    print(f"  [DART] 미완성 영역 재파싱: {', '.join(incomplete_reasons)}", file=sys.stderr)
                stock_rows, dart_reviews = build_dart_rows_or_preserve(
                    target,
                    code,
                    meta,
                    listing_date,
                    shares,
                    existing_stock_rows,
                    existing_by_id,
                )
                all_reviews.extend(dart_reviews)

            # 일정 파서는 확약 배정량을 확보했는데 락업 파서가 전부 또는 일부 기간을
            # 못 만든 경우(엑셀세라퓨틱스 등), 같은 공식 보고서의 값을 기간별로 복구한다.
            # 예전에는 IPO기관 행이 하나도 없을 때만 복구해 15일만 있고 1·3·6개월이
            # 빠진 종목은 영구 누락될 수 있었다.
            schedule_item = _schedule_item_for_target(target, code, schedule_items) or {}
            recovered = build_ipo_events_from_schedule_alloc(
                target, code, meta, listing_date, shares, schedule_item
            )
            existing_ipo_periods = {
                str(row.get("period") or "")
                for row in stock_rows
                if row.get("category") == CATEGORY_IPO
                and (_to_int(row.get("final_qty")) or _to_int(row.get("planned_qty")))
                and (row.get("final_date") or row.get("planned_date"))
            }
            missing_period_rows = [
                carry_manual_fields(row, existing_by_id.get(row["event_id"]))
                for row in recovered
                if str(row.get("period") or "") not in existing_ipo_periods
            ]
            if missing_period_rows:
                stock_rows.extend(missing_period_rows)
                all_reviews = [
                    review for review in all_reviews
                    if not (
                        str(review.get("code") or "") == str(code)
                        and review.get("category") == CATEGORY_IPO
                        and "파싱 결과 없음" in str(review.get("issue") or "")
                    )
                ]
































            # IPO종목 탭의 수동공모가는 선택적 보정값이다. 빈칸이면 기존값/DART값을 보존한다.
            manual_ipo_price = _to_int(target.get("manual_ipo_price"))
            existing_ipo_price = next((_to_int(r.get("ipo_price")) for r in existing_stock_rows if _to_int(r.get("ipo_price"))), 0)
            parsed_or_existing_ipo_price = next(
                (_to_int(r.get("ipo_price")) for r in stock_rows if _to_int(r.get("ipo_price"))),
                existing_ipo_price,
            )
            effective_ipo_price = (
                manual_ipo_price
                if str(target.get("manual_ipo_price_locked") or "N").upper() == "Y" and manual_ipo_price
                else (parsed_or_existing_ipo_price or manual_ipo_price)
            )
            if effective_ipo_price:
                for row in stock_rows:
                    row["ipo_price"] = effective_ipo_price
            else:
                all_reviews.append({
                    "detected_at": _now(), "event_id": "", "code": code, "name": name,
                    "category": "종목정보", "period": "", "issue": "DART 공모가 파싱 실패 — IPO종목 탭의 수동공모가 입력 필요",
                    "memo": "",
                })
































            stock_rows, api_reviews, api_logs, removed_ids = apply_api_updates(target, code, meta, listing_date, shares, stock_rows)
            for removed_id in removed_ids:
                all_rows_by_id.pop(removed_id, None)
            all_reviews.extend(api_reviews)
            all_logs.extend(api_logs)
































            for row in stock_rows:
                row = normalize_row_period(row)
                finalized, reviews, logs = finalize_row(row)
                all_reviews.extend(reviews)
                all_logs.extend(logs)
                all_rows_by_id[finalized["event_id"]] = finalized
            stock_seconds.append((time.perf_counter() - stock_started, name))
        except Exception as exc:
            stock_seconds.append((time.perf_counter() - stock_started, f"{name}(실패)"))
            safe_error = redact_sensitive_text(exc)
            print(f"  [ERROR] {name} 처리 실패 → 건너뛰고 계속: {safe_error}", file=sys.stderr)
            all_reviews.append({
                "detected_at": _now(), "event_id": "", "code": code, "name": name,
                "category": "처리오류", "period": "",
                "issue": f"종목 처리 중 오류로 건너뜀: {safe_error}",
                "memo": "다음 배치에서 자동 재시도됨",
            })
            continue
































        # 대량 편입 중 타임아웃 대비 중간 저장 — 끊겨도 여기까지는 커밋되어 다음 실행이 이어간다
        if idx % 15 == 0:
            interim = sorted(
                all_rows_by_id.values(),
                key=lambda r: (r.get("final_tradable_date") or r.get("planned_tradable_date") or "9999-99-99", r.get("code") or ""),
            )
            _write_csv(admin_path, interim, ADMIN_COLUMNS)
            print(f"[BUILD] 중간 저장 완료 ({idx}/{len(targets)})", file=sys.stderr)
































    if skipped_new:
        print(
            f"[BUILD] 신규 편입 상한({args.max_new}개) 도달 — 남은 신규 {skipped_new}개는 다음 배치에서 이어서 처리",
            file=sys.stderr,
        )
































    phase_seconds["종목 루프"] = time.perf_counter() - loop_started
    leftover_started = time.perf_counter()

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
        try:
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
        except Exception as exc:
            print(
                f"  [ERROR] {name} API 갱신 실패 → 건너뛰고 계속: {redact_sensitive_text(exc)}",
                file=sys.stderr,
            )
            continue
































    # 시트 수기입력 탭에서 내려받은 이벤트 편입 (스팩합병 등 자동 파싱이 안 되는 종목용)
    manual_entries = load_manual_events()
    manual_float_codes: set[str] = set()
    if manual_entries:
        print(f"[BUILD] 수기입력 이벤트 {len(manual_entries)}건 처리", file=sys.stderr)
        manual_reviews, manual_logs = apply_manual_events(manual_entries, existing_rows, existing_by_id, all_rows_by_id)
        all_reviews.extend(manual_reviews)
        all_logs.extend(manual_logs)
        manual_float_codes = {
            normalize_stock_code(entry.get("code"))
            for entry in manual_entries
            if str(entry.get("category") or "").strip() in {"기존주주", "구주·보호예수"}
            and normalize_stock_code(entry.get("code"))
            and _to_int(entry.get("qty")) > 0
        }
        # 수기 투자설명서 값이 운영 이벤트로 정상 편입됐으면 동일 종목의
        # DART 유통가능표 미발견 알림은 더 이상 현재 문제로 남기지 않는다.
        all_reviews = [
            review for review in all_reviews
            if not (
                normalize_stock_code(review.get("code")) in manual_float_codes
                and "유통가능" in str(review.get("issue") or "")
            )
        ]
































    # 같은 해제 건인데 API 확인 여부에 따라 날짜가 갈라지는 것 방지
    all_logs.extend(align_final_dates_with_api(all_rows_by_id))
    # 휴장일 추가로 거래가능일이 바뀌어 ID만 갈라진 옛 행 정리
    all_logs.extend(discard_id_drifted_duplicates(all_rows_by_id))
































    all_rows = sorted(all_rows_by_id.values(), key=lambda r: (r.get("final_tradable_date") or r.get("planned_tradable_date") or "9999-99-99", r.get("code") or ""))
































    # 편입된 전 종목의 최근 상장주식수·종가·비율을 같은 KRX 기준일로 갱신한다.
    phase_seconds["스캔 연도 외 API 검증"] = time.perf_counter() - leftover_started
    market_started = time.perf_counter()
    close_date, market_logs = refresh_market_data(all_rows)
    all_logs.extend(market_logs)
    phase_seconds["KRX 시세"] = time.perf_counter() - market_started
































    resolved_review_ids = {
        f"{row.get('code')}-공모가파싱실패"
        for row in all_rows
        if row.get("code") and _to_int(row.get("ipo_price"))
    }
    resolved_review_ids.update(f"{code}-데이터확인" for code in manual_float_codes)
    review_history = merge_review_history(review_path, all_reviews, resolved_review_ids)
    _write_csv(admin_path, all_rows, ADMIN_COLUMNS)
    _write_csv(review_path, review_history, REVIEW_COLUMNS)
    _append_csv(log_path, all_logs, LOG_COLUMNS)
































    # 상장일 당일 시세 캐시 보강 (랭킹의 상장일 종가·정확한 상장 시점 주식수)
    snapshot_started = time.perf_counter()
    try:
        refresh_listing_day_snapshot(all_rows)
    except Exception as exc:
        print(f"[KRX] 상장일 시세 갱신 실패(무시): {redact_sensitive_text(exc)}", file=sys.stderr)
    phase_seconds["상장일 스냅샷"] = time.perf_counter() - snapshot_started

    # 투자설명서 본문의 상장 직후 유통가능물량 — 캐시에 없는 종목만 새로 찾는다
    float_started = time.perf_counter()
    try:
        refresh_listing_float(all_rows)
    except Exception as exc:
        print(f"[DART] 유통가능물량 문장 갱신 실패(무시): {redact_sensitive_text(exc)}", file=sys.stderr)
    phase_seconds["유통가능 문장"] = time.perf_counter() - float_started

    # 권리락 조정계수 — 마지막으로 본 거래일 이후만 이어서 훑는다(하루 2콜)
    adjust_started = time.perf_counter()
    try:
        from scripts.price_adjustments import scan as scan_price_adjustments

        scan_price_adjustments()
    except Exception as exc:
        print(f"[KRX] 조정계수 갱신 실패(무시): {redact_sensitive_text(exc)}", file=sys.stderr)
    phase_seconds["조정계수"] = time.perf_counter() - adjust_started

    # 확약 해제일 당일 시세 (락업 랭킹의 해제일 등락률)
    release_started = time.perf_counter()
    try:
        refresh_release_day_prices(all_rows)
    except Exception as exc:
        print(f"[KRX] 해제일 시세 갱신 실패(무시): {redact_sensitive_text(exc)}", file=sys.stderr)
    phase_seconds["해제일 시세"] = time.perf_counter() - release_started

    out_path = data_dir / "site_data.json"
    previous_price_date = None
    if out_path.exists():
        try:
            previous_price_date = json.loads(out_path.read_text(encoding="utf-8")).get("updated")
        except Exception:
            previous_price_date = None
    # KRX 호출이 일시 실패하면 기존 종가의 실제 기준일을 유지한다.
    # 실행일로 덮으면 오래된 가격이 오늘 가격처럼 표시되는 문제가 생긴다.
    site_data = rows_to_site_data(all_rows, close_date or previous_price_date)
    out_path.write_text(json.dumps(site_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SAVE] admin={admin_path}", file=sys.stderr)
    print(f"[SAVE] review={review_path}", file=sys.stderr)
    print(f"[SAVE] site_data={out_path}", file=sys.stderr)

    # 일정의 배정표 갱신은 이제 빌드 앞에서 수행한다. 여기서는 락업 파서 쪽에만
    # 있던 확약값을 일정 데이터에 역보강해 다음 실행의 스냅샷을 완성한다.
    schedule_started = time.perf_counter()
    try:
        # 선행 갱신이 네트워크 문제로 실패했으면 기존처럼 마지막에 한 번 더 시도한다.
        if not schedule_pre_refreshed:
            from scripts.sources.ipo_schedule import refresh_ipo_schedule

            retry_snap_date, retry_snap = latest_krx_snapshot()
            retry_base_date, retry_base = latest_base_info()
            refresh_ipo_schedule(
                krx_snapshot=retry_snap,
                krx_trading_date=retry_snap_date or retry_base_date,
                krx_base_info=retry_base,
                backfill_all=bool(getattr(args, "backfill_all", False)),
            )
        # 같은 실적보고서를 락업 파서와 일정 파서가 따로 읽는데 일정 쪽만 배정표를
        # 못 읽은 종목(삼진식품·로킷헬스케어 등)은 재파싱 대신 락업 값을 복사한다.
        sync_commit_alloc_from_lockup(data_dir / "ipo_schedule.json", list(all_rows_by_id.values()))
    except Exception as exc:
        print(
            f"[IPO일정] 갱신 실패(락업 데이터에는 영향 없음): {redact_sensitive_text(exc)}",
            file=sys.stderr,
        )
    phase_seconds["IPO일정"] = time.perf_counter() - schedule_started

    total = sum(phase_seconds.values())
    print(f"[TIME] 총 {total/60:.1f}분", file=sys.stderr)
    for label, seconds in sorted(phase_seconds.items(), key=lambda kv: -kv[1]):
        share = seconds / total * 100 if total else 0
        print(f"[TIME]   {seconds:7.1f}s ({share:4.1f}%) {label}", file=sys.stderr)
    for seconds, stock in sorted(stock_seconds, reverse=True)[:5]:
        print(f"[TIME]   느린 종목 {seconds:6.1f}s {stock}", file=sys.stderr)

    print("[FINISH] 전체 배치 완료", file=sys.stderr)
































































if __name__ == "__main__":
    main()
