"""Pure data transforms for the operator-facing Google Sheet model.

The website and build pipeline keep using the existing JSON/CSV files.  This
module only gives the Sheet a smaller command surface and deliberately reuses
the already committed data during the first migration run.
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from typing import Any, Iterable


MANAGEMENT_COLUMNS = [
    "scope", "name", "corp_code", "stock_code", "market", "listing_date",
    "management_status", "visibility", "listing_date_locked", "manual_ipo_price",
    "manual_ipo_price_locked", "listing_date_edited", "manual_ipo_price_edited",
    "initial_shares", "current_shares", "shares_date",
    "close_price", "content_url", "validation_status", "validation_reason", "memo",
]

CORRECTION_COLUMNS = [
    "task_id", "target", "name", "code", "field", "category", "period",
    "auto_value", "manual_value", "manual_date", "manual_qty",
    "override_mode", "status", "memo", "event_id",
]

SCHEDULE_FIELD_MAP: dict[str, tuple[str, ...]] = {
    "희망가액": ("band_low", "band_high"),
    "확정공모가": ("final_price",),
    "수요예측일": ("forecast_start", "forecast_end"),
    "청약일": ("sub_start", "sub_end"),
    "상장일": ("listing_date",),
    "주관사": ("underwriter",),
    "공모주식수": ("offer_shares",),
}

COMMIT_PERIODS = ["미확약", "15일", "1개월", "3개월", "6개월"]


def norm_name(name: object) -> str:
    return re.sub(r"[\s㈜()\[\]]|주식회사", "", str(name or ""))


def manual_corp_code(name: str) -> str:
    digest = hashlib.sha1(norm_name(name).encode("utf-8")).hexdigest()[:12]
    return f"manual-{digest}"


def _scope_parts(scope: object) -> set[str]:
    text = str(scope or "")
    out: set[str] = set()
    if "IPO일정" in text:
        out.add("IPO일정")
    if "락업" in text:
        out.add("락업")
    return out


def _scope_label(parts: Iterable[str]) -> str:
    values = set(parts)
    if values == {"IPO일정", "락업"}:
        return "IPO일정+락업"
    if "IPO일정" in values:
        return "IPO일정"
    return "락업"


def _row_key(row: dict[str, Any]) -> str:
    name_key = norm_name(row.get("name"))
    if name_key:
        return f"name:{name_key}"
    corp = str(row.get("corp_code") or "").strip()
    if corp:
        return f"corp:{corp}"
    return f"stock:{str(row.get('stock_code') or '').strip()}"


def _fill_missing(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in MANAGEMENT_COLUMNS:
        if not target.get(key) and source.get(key) not in (None, ""):
            target[key] = source[key]


def merge_stock_management(
    saved: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    schedule: dict[str, Any],
) -> list[dict[str, str]]:
    """Merge new commands with all legacy/current data without dropping rows."""
    merged: dict[str, dict[str, Any]] = {}

    def upsert(source: dict[str, Any], scope: str) -> dict[str, Any]:
        key = _row_key(source)
        current = merged.setdefault(key, {column: "" for column in MANAGEMENT_COLUMNS})
        scopes = _scope_parts(current.get("scope")) | _scope_parts(scope)
        current["scope"] = _scope_label(scopes)
        _fill_missing(current, source)
        return current

    # Saved operator decisions always win.  Later sources only fill blanks.
    for row in saved:
        cleaned = {column: str(row.get(column) or "").strip() for column in MANAGEMENT_COLUMNS}
        if cleaned.get("name") or cleaned.get("corp_code") or cleaned.get("stock_code"):
            merged[_row_key(cleaned)] = cleaned

    for target in targets:
        upsert({
            "scope": "락업",
            "name": target.get("name") or "",
            "stock_code": target.get("code") or "",
            "market": target.get("market") or "",
            "listing_date": target.get("listing_date") or "",
            "manual_ipo_price": target.get("manual_ipo_price") or "",
            "manual_ipo_price_locked": target.get("manual_ipo_price_locked") or "N",
            "management_status": "자동",
            "visibility": "",
        }, "락업")

    all_items = list(schedule.get("items") or []) + list(schedule.get("past_items") or [])
    for item in all_items:
        if item.get("fixed_excluded"):
            status, visibility = "제외고정", "비공개"
        elif item.get("manual_entry") or item.get("review_approved"):
            status, visibility = "수동편입", "노출"
        else:
            # 자동 판정 결과를 명령으로 저장하지 않는다. 검토대기 여부는 현황 탭에서
            # 확인하고, 운영자가 개입할 때만 수동편입/비공개를 선택한다.
            status, visibility = "자동", "비공개" if item.get("management_hidden") else ""
        source = {
            "scope": "IPO일정+락업",
            "name": item.get("name") or "",
            "corp_code": item.get("corp_code") or "",
            "stock_code": item.get("stock_code") or "",
            "market": item.get("market") or "",
            "listing_date": item.get("listing_date") or "",
            "listing_date_locked": "Y" if "listing_date" in set(item.get("manual_fields") or []) else "N",
            "manual_ipo_price": item.get("final_price") or "",
            "manual_ipo_price_locked": "Y" if "final_price" in set(item.get("manual_fields") or []) else "N",
            "management_status": status,
            "visibility": visibility,
            "content_url": item.get("content_url") or "",
        }
        # 이름만 수동편입한 후 DART 공식 회사명·기업코드를 알게 된 경우,
        # 기존 운영자 명령을 새 종목으로 중복 생성하지 않고 공식 식별자로 승격한다.
        source_key = _row_key(source)
        alias = norm_name(item.get("management_name"))
        alias_key = f"name:{alias}" if alias else ""
        if alias_key and alias_key != source_key and alias_key in merged:
            current = merged.pop(alias_key)
            destination = merged.pop(source_key, None)
            if destination:
                current["scope"] = _scope_label(
                    _scope_parts(current.get("scope")) | _scope_parts(destination.get("scope")) | {"IPO일정", "락업"}
                )
                _fill_missing(current, destination)
            merged[source_key] = current
            current["scope"] = _scope_label(_scope_parts(current.get("scope")) | {"IPO일정", "락업"})
            _fill_missing(current, source)
        else:
            current = upsert(source, "IPO일정+락업")
        # KRX/DART가 확정한 식별자는 초기 수동 힌트보다 우선한다.
        for identity in ("name", "corp_code", "stock_code", "market", "listing_date"):
            if source.get(identity):
                current[identity] = str(source[identity])
        # Existing saved decisions are not overwritten by inferred state.
        if not current.get("management_status"):
            current["management_status"] = status
        if not current.get("visibility"):
            current["visibility"] = visibility

    # Old IPO취소 tombstones become permanent exclusions during migration.
    for corp_code, tomb in (schedule.get("deleted_corps") or {}).items():
        current = upsert({
            "scope": "IPO일정+락업",
            "name": tomb.get("name") or "",
            "corp_code": corp_code,
            "management_status": "제외고정",
            "visibility": "비공개",
            "memo": "기존 IPO취소 이관",
        }, "IPO일정+락업")
        current["management_status"] = "제외고정"
        current["visibility"] = "비공개"

    rows: list[dict[str, str]] = []
    for row in merged.values():
        if not row.get("management_status"):
            row["management_status"] = "수동편입" if "IPO일정" in _scope_parts(row.get("scope")) else "자동"
        if not row.get("visibility"):
            if row["management_status"] in {"검토대기", "제외고정"}:
                row["visibility"] = "비공개"
            elif row["management_status"] == "수동편입":
                row["visibility"] = "노출"
        rows.append({column: str(row.get(column) or "") for column in MANAGEMENT_COLUMNS})
    return sorted(rows, key=lambda row: (row.get("scope", ""), row.get("listing_date", "9999") or "9999", row.get("name", "")))


def _matches_management(item: dict[str, Any], row: dict[str, Any]) -> bool:
    corp = str(row.get("corp_code") or "").strip()
    stock = str(row.get("stock_code") or "").strip()
    if corp and not corp.startswith("manual-") and corp == str(item.get("corp_code") or ""):
        return True
    if stock and stock == str(item.get("stock_code") or ""):
        return True
    return bool(norm_name(row.get("name")) and norm_name(row.get("name")) == norm_name(item.get("name")))


def exclusion_key(row: dict[str, Any]) -> str:
    corp = str(row.get("corp_code") or "").strip()
    if corp and not corp.startswith("manual-"):
        return f"corp:{corp}"
    return f"name:{norm_name(row.get('name'))}"


def is_fixed_excluded(corp_code: str, name: str, exclusions: dict[str, Any]) -> bool:
    return bool(exclusions.get(f"corp:{corp_code}") or exclusions.get(f"name:{norm_name(name)}"))


def apply_stock_management(
    rows: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    schedule: dict[str, Any],
    today: str | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any], list[str]]:
    """Apply Sheet commands to the existing canonical files in-place safely."""
    today = today or date.today().isoformat()
    all_items = list(schedule.get("items") or [])
    past_items = list(schedule.get("past_items") or [])
    fixed_exclusions: dict[str, Any] = dict(schedule.get("fixed_exclusions") or {})
    history = list(schedule.get("history") or [])

    target_by_name = {norm_name(t.get("name")): dict(t) for t in targets if norm_name(t.get("name"))}
    seed_names: list[str] = []

    for raw in rows:
        row = {column: str(raw.get(column) or "").strip() for column in MANAGEMENT_COLUMNS}
        name = row.get("name", "")
        if not name:
            continue
        scopes = _scope_parts(row.get("scope")) or {"IPO일정", "락업"}
        status = row.get("management_status") or "수동편입"
        visibility = row.get("visibility") or (
            "비공개" if status in {"검토대기", "제외고정"} else ("노출" if status == "수동편입" else "")
        )

        if "락업" in scopes:
            key = norm_name(name)
            old = target_by_name.get(key, {})
            if status != "제외고정":
                target_by_name[key] = {
                    **old,
                    "market": row.get("market") or old.get("market") or "",
                    "name": name,
                    "listing_date": row.get("listing_date") or old.get("listing_date") or "",
                    "code": row.get("stock_code") or old.get("code") or "",
                    "manual_ipo_price": row.get("manual_ipo_price") or old.get("manual_ipo_price") or "",
                    "manual_ipo_price_locked": row.get("manual_ipo_price_locked") or old.get("manual_ipo_price_locked") or "N",
                }
            else:
                target_by_name.pop(key, None)

        if "IPO일정" not in scopes:
            continue

        existing = next((i for i in all_items + past_items if _matches_management(i, row)), None)
        key = exclusion_key(row)
        if status == "제외고정":
            old_status = existing.get("management_status") if existing else ""
            fixed_exclusions[key] = {
                "name": name,
                "corp_code": row.get("corp_code") or (existing or {}).get("corp_code") or "",
                "excluded_at": today,
                "memo": row.get("memo") or "",
            }
            if existing:
                existing["fixed_excluded"] = True
                existing["management_status"] = "제외고정"
                existing["review_pending"] = True
            if old_status != "제외고정":
                history.append({
                    "date": today, "name": name, "type": "고정제외", "field": "노출",
                    "old": old_status or "게시/검토", "new": "제외고정",
                })
            continue

        # Re-enabling is explicit.  A new filing never clears this by itself.
        for candidate in list(fixed_exclusions):
            info = fixed_exclusions.get(candidate) or {}
            if candidate == key or norm_name(info.get("name")) == norm_name(name):
                fixed_exclusions.pop(candidate, None)

        if existing is None:
            corp_code = row.get("corp_code") or manual_corp_code(name)
            existing = {
                "corp_code": corp_code,
                "name": name,
                "management_name": name,
                "first_filing_date": "",
                "last_rcept_no": "",
                "withdrawn": False,
                "manual_entry": True,
                "review_approved": True,
                "review_pending": False,
            }
            all_items.append(existing)
            history.append({
                "date": today, "name": name, "type": "수동편입", "field": "상태",
                "old": "미등록", "new": "공모 준비(미정 선노출)",
            })

        existing.pop("fixed_excluded", None)
        existing["management_status"] = status
        if row.get("corp_code") and not row["corp_code"].startswith("manual-"):
            existing["corp_code"] = row["corp_code"]
        if row.get("stock_code"):
            existing["stock_code"] = row["stock_code"]
        if row.get("market") and not existing.get("market"):
            existing["market"] = row["market"]
        if row.get("listing_date"):
            existing["listing_date"] = row["listing_date"]
        if row.get("manual_ipo_price"):
            try:
                existing["final_price"] = int(str(row["manual_ipo_price"]).replace(",", ""))
            except ValueError:
                pass
        if row.get("content_url"):
            existing["content_url"] = row["content_url"]

        locked = set(existing.get("manual_fields") or [])
        provisional = set(existing.get("provisional_fields") or [])
        for field, flag in (
            ("listing_date", row.get("listing_date_locked")),
            ("final_price", row.get("manual_ipo_price_locked")),
        ):
            if str(flag or "N").upper() == "Y":
                locked.add(field)
                provisional.discard(field)
            else:
                locked.discard(field)
                edited = (
                    row.get("listing_date_edited") if field == "listing_date"
                    else row.get("manual_ipo_price_edited")
                )
                if str(edited or "N").upper() == "Y":
                    provisional.add(field)
        if locked:
            existing["manual_fields"] = sorted(locked)
        else:
            existing.pop("manual_fields", None)
        if provisional:
            existing["provisional_fields"] = sorted(provisional)
        else:
            existing.pop("provisional_fields", None)

        if visibility == "비공개" or status == "검토대기":
            existing["management_hidden"] = True
            existing["review_pending"] = True
            if status == "검토대기":
                existing.pop("manual_entry", None)
                existing.pop("review_approved", None)
        elif status == "수동편입":
            existing["manual_entry"] = True
            existing["review_approved"] = True
            existing["review_pending"] = False
        else:
            existing.pop("management_hidden", None)
            existing.pop("manual_entry", None)
            existing.pop("review_approved", None)
        if visibility == "노출" and status != "검토대기":
            existing.pop("management_hidden", None)
            if status == "수동편입":
                existing["review_pending"] = False

        if existing.get("manual_entry") or not existing.get("last_rcept_no"):
            seed_names.append(name)

    # Rows that predate the new Sheet stay intact because merge_stock_management
    # always places them in the first generated tab.  Do not infer deletion from
    # a missing row; deletion must be the explicit 제외고정 command.
    target_rows = list(target_by_name.values())
    target_rows.sort(key=lambda item: (item.get("listing_date") or "", item.get("name") or ""))
    schedule["items"] = all_items
    schedule["past_items"] = past_items
    schedule["fixed_exclusions"] = fixed_exclusions
    schedule["history"] = history[-500:]
    return target_rows, schedule, sorted(set(seed_names))


def format_schedule_value(item: dict[str, Any], field: str) -> str:
    if field == "희망가액":
        low, high = item.get("band_low") or 0, item.get("band_high") or 0
        return f"{low} ~ {high}" if low and high else ""
    if field == "확정공모가":
        return str(item.get("final_price") or "")
    if field == "수요예측일":
        start, end = item.get("forecast_start") or "", item.get("forecast_end") or ""
        return start if start and start == end else (f"{start} ~ {end}" if start else "")
    if field == "청약일":
        start, end = item.get("sub_start") or "", item.get("sub_end") or ""
        return start if start and start == end else (f"{start} ~ {end}" if start else "")
    if field == "상장일":
        return str(item.get("listing_date") or "")
    if field == "주관사":
        return str(item.get("underwriter") or "")
    if field == "공모주식수":
        return str(item.get("offer_shares") or "")
    return ""


def _task(base: dict[str, Any], existing: dict[str, dict[str, Any]]) -> dict[str, str]:
    saved = existing.get(str(base.get("task_id") or ""), {})
    row: dict[str, str] = {}
    for column in CORRECTION_COLUMNS:
        value = saved.get(column) if saved.get(column) not in (None, "") else base.get(column, "")
        row[column] = str(value or "")
    if base.get("status") == "자동해결":
        row["status"] = "자동해결"
    return row


def build_correction_tasks(
    saved: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    schedule: dict[str, Any],
    admin_rows: list[dict[str, Any]],
    manual_events: list[dict[str, Any]],
    today: str | None = None,
) -> list[dict[str, str]]:
    """Build one operator queue while preserving every previously entered value."""
    today_date = date.fromisoformat(today or date.today().isoformat())
    saved_by_id = {str(row.get("task_id") or ""): row for row in saved if row.get("task_id")}
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(base: dict[str, Any]) -> None:
        task_id = str(base.get("task_id") or "")
        if not task_id or task_id in seen:
            return
        seen.add(task_id)
        out.append(_task(base, saved_by_id))

    target_by_code = {str(t.get("code") or ""): t for t in targets if t.get("code")}
    admin_codes = {str(r.get("code") or "") for r in admin_rows}
    ipo_codes = {str(r.get("code") or "") for r in admin_rows if r.get("category") == "IPO기관"}
    float_codes = {str(r.get("code") or "") for r in admin_rows if r.get("category") == "구주·보호예수"}
    priced = {str(r.get("code") or "") for r in admin_rows if str(r.get("ipo_price") or "").replace(",", "").isdigit() and int(str(r.get("ipo_price") or "").replace(",", "")) > 0}
    priced |= {code for code, t in target_by_code.items() if str(t.get("manual_ipo_price") or "").replace(",", "").isdigit() and int(str(t.get("manual_ipo_price") or "").replace(",", "")) > 0}

    for code, target in target_by_code.items():
        common = {"target": "락업", "name": target.get("name") or "", "code": code, "override_mode": "고정", "status": "대기"}
        if code in admin_codes and code not in priced:
            add({**common, "task_id": f"gap:price:{code}", "field": "공모가"})
        if code not in float_codes:
            add({**common, "task_id": f"gap:float:{code}", "field": "락업이벤트", "category": "기존주주"})
        listing = str(target.get("listing_date") or "")
        if code not in ipo_codes and listing and listing >= (today_date - timedelta(days=190)).isoformat():
            add({**common, "task_id": f"gap:ipo:{code}", "field": "락업이벤트", "category": "IPO기관"})

    for event in manual_events:
        code = str(event.get("code") or "")
        task_id = f"manual:{code}:{event.get('category','')}:{event.get('period','')}:{event.get('date','')}"
        add({
            "task_id": task_id, "target": "락업", "name": (target_by_code.get(code) or {}).get("name", ""),
            "code": code, "field": "락업이벤트", "category": event.get("category") or "",
            "period": event.get("period") or "", "manual_date": event.get("date") or "",
            "manual_qty": event.get("qty") or "", "override_mode": "고정", "status": "적용",
        })

    for row in admin_rows:
        if not (row.get("manual_date") or row.get("manual_qty") or row.get("memo") or row.get("review_needed") == "Y"):
            continue
        event_id = str(row.get("event_id") or "")
        add({
            "task_id": f"event:{event_id}", "target": "락업", "name": row.get("name") or "",
            "code": row.get("code") or "", "field": "기존이벤트보정", "category": row.get("category") or "",
            "period": row.get("period") or "", "auto_value": f"{row.get('planned_date') or ''} / {row.get('planned_qty') or ''}",
            "manual_date": row.get("manual_date") or "", "manual_qty": row.get("manual_qty") or "",
            "override_mode": "고정" if str(row.get("manual_lock") or "N").upper() == "Y" else "임시",
            "status": "검토필요" if row.get("review_needed") == "Y" else "적용",
            "memo": row.get("memo") or "", "event_id": event_id,
        })

    for item in list(schedule.get("items") or []) + list(schedule.get("past_items") or []):
        if item.get("fixed_excluded"):
            continue
        locked = set(item.get("manual_fields") or [])
        provisional = set(item.get("provisional_fields") or [])
        is_manual = bool(item.get("manual_entry"))
        for label, fields in SCHEDULE_FIELD_MAP.items():
            task_id = f"schedule:{item.get('corp_code') or manual_corp_code(item.get('name') or '')}:{label}"
            saved_row = saved_by_id.get(task_id, {})
            missing = not all(item.get(field) for field in fields)
            touched = bool(locked.intersection(fields) or provisional.intersection(fields))
            if not ((is_manual and missing) or touched):
                # 임시 보정 후 DART 공식값이 들어와 provisional 표시가 해제되면
                # 행을 지우지 않고 자동해결로 남겨 어떤 값이 승계됐는지 확인할 수 있게 한다.
                if (
                    saved_row.get("override_mode") == "임시"
                    and saved_row.get("manual_value")
                    and not missing
                ):
                    add({
                        "task_id": task_id, "target": "IPO일정", "name": item.get("name") or "",
                        "code": item.get("corp_code") or "", "field": label,
                        "auto_value": format_schedule_value(item, label),
                        "manual_value": saved_row.get("manual_value") or "",
                        "override_mode": "임시", "status": "자동해결",
                    })
                continue
            mode = "고정" if locked.intersection(fields) else "임시"
            status = "적용" if touched else "대기"
            add({
                "task_id": task_id, "target": "IPO일정", "name": item.get("name") or "",
                "code": item.get("corp_code") or "", "field": label,
                "auto_value": format_schedule_value(item, label),
                "manual_value": format_schedule_value(item, label) if touched else "",
                "override_mode": mode, "status": status,
            })

        # 자동 파싱이 끝까지 실패한 경우의 수기 안전망. 신청수량만 넣으면 화면의
        # 배정률(배정수량/신청수량)은 자동 계산된다.
        apply_by_period = {
            str(value.get("period") or ""): value
            for value in (item.get("commit_apply") or [])
            if isinstance(value, dict)
        }
        if item.get("commit_alloc") or item.get("demand_ratio"):
            corp_key = item.get("corp_code") or manual_corp_code(item.get("name") or "")
            for period in COMMIT_PERIODS:
                if period in apply_by_period:
                    continue
                add({
                    "task_id": f"schedule:{corp_key}:기관신청물량:{period}",
                    "target": "IPO일정",
                    "name": item.get("name") or "",
                    "code": item.get("corp_code") or "",
                    "field": "기관신청물량",
                    "period": period,
                    "manual_qty": "",
                    "override_mode": "고정",
                    "status": "대기",
                })

    # Keep operator-created rows that are not generated by the current gap scan.
    for task_id, row in saved_by_id.items():
        if task_id not in seen:
            out.append({column: str(row.get(column) or "") for column in CORRECTION_COLUMNS})
    return sorted(out, key=lambda row: (row.get("status") == "자동해결", row.get("target", ""), row.get("name", ""), row.get("field", ""), row.get("task_id", "")))


def _numbers(value: object) -> list[int]:
    return [int(token.replace(",", "")) for token in re.findall(r"\d[\d,]*", str(value or ""))]


def _dates(value: object) -> list[str]:
    out: list[str] = []
    for year, month, day in re.findall(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", str(value or "")):
        out.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    return out


def apply_schedule_correction(item: dict[str, Any], row: dict[str, Any]) -> bool:
    """Apply one IPO schedule correction. Blank cells never lock a field."""
    label = str(row.get("field") or "")
    fields = SCHEDULE_FIELD_MAP.get(label)
    value = str(row.get("manual_value") or "").strip()
    if not fields or not value or row.get("status") in {"자동해결", "취소"}:
        return False

    before = [item.get(field) for field in fields]
    before_locked = set(item.get("manual_fields") or [])
    before_provisional = set(item.get("provisional_fields") or [])
    if label in {"희망가액"}:
        nums = _numbers(value)
        if len(nums) < 2:
            return False
        item[fields[0]], item[fields[1]] = nums[0], nums[1]
    elif label in {"확정공모가", "공모주식수"}:
        nums = _numbers(value)
        if not nums:
            return False
        item[fields[0]] = nums[0]
    elif label in {"수요예측일", "청약일"}:
        dates = _dates(value)
        if not dates:
            return False
        item[fields[0]], item[fields[1]] = dates[0], dates[-1]
    elif label == "상장일":
        dates = _dates(value)
        if not dates:
            return False
        item[fields[0]] = dates[0]
    else:
        item[fields[0]] = value

    locked = set(item.get("manual_fields") or [])
    provisional = set(item.get("provisional_fields") or [])
    if row.get("override_mode") == "고정":
        locked.update(fields)
        provisional.difference_update(fields)
    else:
        provisional.update(fields)
        locked.difference_update(fields)
    if locked:
        item["manual_fields"] = sorted(locked)
    else:
        item.pop("manual_fields", None)
    if provisional:
        item["provisional_fields"] = sorted(provisional)
    else:
        item.pop("provisional_fields", None)
    return (
        before != [item.get(field) for field in fields]
        or before_locked != set(item.get("manual_fields") or [])
        or before_provisional != set(item.get("provisional_fields") or [])
    )


def release_schedule_correction(item: dict[str, Any], row: dict[str, Any]) -> bool:
    """보정방식=자동복귀: 수기값과 잠금을 지우고 다음 자동 수집에 맡긴다."""
    if str(row.get("override_mode") or "") != "자동복귀":
        return False
    fields = SCHEDULE_FIELD_MAP.get(str(row.get("field") or ""))
    if not fields:
        return False
    before = (
        [item.get(field) for field in fields],
        list(item.get("manual_fields") or []),
        list(item.get("provisional_fields") or []),
    )
    for field in fields:
        item.pop(field, None)
    locked = set(item.get("manual_fields") or []) - set(fields)
    provisional = set(item.get("provisional_fields") or []) - set(fields)
    if locked:
        item["manual_fields"] = sorted(locked)
    else:
        item.pop("manual_fields", None)
    if provisional:
        item["provisional_fields"] = sorted(provisional)
    else:
        item.pop("provisional_fields", None)
    # 같은 공시번호라도 다음 배치에서 자동 필드를 다시 확인한다.
    item["ipo_parse_version"] = 0
    after = (
        [item.get(field) for field in fields],
        list(item.get("manual_fields") or []),
        list(item.get("provisional_fields") or []),
    )
    return before != after


def apply_commit_apply_correction(item: dict[str, Any], row: dict[str, Any]) -> bool:
    """보정작업의 기간별 기관 신청수량을 IPO 일정 데이터에 반영한다."""
    if str(row.get("field") or "") != "기관신청물량":
        return False
    period = str(row.get("period") or "").strip()
    qtys = _numbers(row.get("manual_qty") or row.get("manual_value"))
    if period not in COMMIT_PERIODS or not qtys or qtys[0] <= 0:
        return False
    qty = qtys[0]
    current = {
        str(value.get("period") or ""): dict(value)
        for value in (item.get("commit_apply") or [])
        if isinstance(value, dict) and value.get("period")
    }
    before = current.get(period, {}).get("qty")
    current[period] = {
        "period": period,
        "qty": qty,
        "pct": current.get(period, {}).get("pct", 0),
    }
    total = sum(int(current[p].get("qty") or 0) for p in COMMIT_PERIODS if p in current)
    complete = all(p in current and int(current[p].get("qty") or 0) > 0 for p in COMMIT_PERIODS)
    if complete and total:
        for p in COMMIT_PERIODS:
            current[p]["pct"] = round(int(current[p]["qty"]) / total * 100, 2)
    item["commit_apply"] = [current[p] for p in COMMIT_PERIODS if p in current]
    return before != qty
