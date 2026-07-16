"""Google Sheets and local CSV synchronization.

Commands:
  python -m scripts.sheets_sync pull-admin
  python -m scripts.sheets_sync push-all
  python -m scripts.sheets_sync reset-all
"""
from __future__ import annotations


import argparse
import csv
import glob
import json
import os
import sys
from datetime import date
from pathlib import Path


import gspread
from gspread.utils import rowcol_to_a1

from scripts.management import (
    CORRECTION_COLUMNS,
    MANAGEMENT_COLUMNS,
    SCHEDULE_FIELD_MAP,
    apply_commit_apply_correction,
    apply_schedule_correction,
    apply_stock_management,
    build_correction_tasks,
    merge_stock_management,
    norm_name,
    release_schedule_correction,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SHEET_ID = "1THcCbn5n9NQesOa0JHV3B-pdCeab8sRqMZhxOIWI-pg"


ADMIN_COLUMNS = [
    "event_id", "code", "name", "market", "listing_date", "shares", "current_shares", "shares_date",
    "close_price", "ipo_price",
    "category", "type", "period",
    "planned_date", "planned_tradable_date", "planned_date_display", "planned_qty", "planned_pct",
    "dart_rcp", "dart_source", "parse_note",
    "api_return_date", "api_return_qty", "api_reason",
    "manual_date", "manual_qty", "manual_lock", "manual_mode", "sheet_visible",
    "final_date", "final_tradable_date", "final_date_display", "final_qty", "final_pct",
    "status", "review_needed", "memo", "updated_at",
]


ADMIN_SHEET_COLUMNS = [
    "name", "code", "market", "category", "period",
    "listing_date", "close_price", "ipo_price", "shares", "current_shares",
    "planned_date", "planned_qty", "planned_pct",
    "api_return_date", "api_return_qty", "api_reason",
    "manual_lock", "manual_date", "manual_qty", "manual_mode", "sheet_visible", "memo",
    "final_date", "final_tradable_date", "final_qty", "final_pct",
    "status", "review_needed",
    "event_id", "type", "planned_tradable_date", "planned_date_display",
    "dart_rcp", "dart_source", "parse_note", "final_date_display", "updated_at",
]


IPO_ADMIN_SHEET_COLUMNS = [
    "name", "code", "market", "period",
    "listing_date", "close_price", "ipo_price", "shares", "current_shares",
    "planned_date", "planned_qty", "planned_pct",
    "manual_lock", "manual_date", "manual_qty", "manual_mode", "sheet_visible", "memo",
    "final_date", "final_tradable_date", "final_qty", "final_pct",
    "status", "review_needed",
    "event_id", "type", "category", "planned_tradable_date", "planned_date_display",
    "dart_rcp", "dart_source", "parse_note", "final_date_display", "updated_at",
]


FLOAT_ADMIN_SHEET_COLUMNS = [
    "name", "code", "market", "period",
    "listing_date", "close_price", "shares", "current_shares",
    "planned_date", "planned_qty", "planned_pct",
    "api_return_date", "api_return_qty", "api_reason",
    "manual_lock", "manual_date", "manual_qty", "manual_mode", "sheet_visible", "memo",
    "final_date", "final_tradable_date", "final_qty", "final_pct",
    "status", "review_needed",
    "event_id", "type", "category", "planned_tradable_date", "planned_date_display",
    "dart_rcp", "dart_source", "parse_note", "final_date_display", "updated_at",
]


REVIEW_COLUMNS = [
    "status", "name", "code", "review_type", "target", "issue", "comparison",
    "first_detected", "last_detected", "resolved_at", "operator_memo", "review_id", "event_id",
]


LOG_COLUMNS = [
    "time", "event_id", "code", "name", "field", "old_value", "new_value", "reason",
]


UNIVERSE_REVIEW_COLUMNS = [
    "name", "code", "market", "listing_date", "shares", "close_price",
    "classification", "classification_reason", "review_decision", "review_memo",
    "rcp", "detected_bas_dd",
]


REVIEW_DECISIONS_PATH = ROOT_DIR / "data" / "listing_review_decisions.json"


# 휴장일 탭 — 운영자가 연 단위로 채우는 거래소 휴장일. 배치가 내려받아 해제일 보정에 사용
HOLIDAYS_PATH = ROOT_DIR / "data" / "holidays.json"
HOLIDAY_TAB = "휴장일"


# IPO종목 탭 — 편입 대상 종목의 유일한 원천 (구분/회사명/상장일/종목코드)
IPO_TARGETS_PATH = ROOT_DIR / "data" / "ipo_targets.json"
IPO_TARGET_TAB = "IPO종목"


# 새 운영 구조. 기존 탭/파일은 첫 배치 이관과 하위 호환에만 사용한다.
STOCK_MANAGEMENT_PATH = ROOT_DIR / "data" / "stock_management.json"
STOCK_MANAGEMENT_TAB = "종목관리"
STOCK_MANAGEMENT_HEADERS = [
    "관리", "홈페이지노출", "기업명", "DART기업코드", "종목코드", "시장",
    "상장일", "상장일고정", "공모가", "공모가고정",
    "최초상장주식수", "현재상장주식수", "상장주식수기준일", "종가",
    "콘텐츠링크", "검증상태", "검증사유", "메모",
]
STOCK_MANAGEMENT_KEYS = {
    "관리": "management_status", "홈페이지노출": "visibility", "기업명": "name",
    "DART기업코드": "corp_code", "종목코드": "stock_code", "시장": "market",
    "상장일": "listing_date", "상장일고정": "listing_date_locked",
    "공모가": "manual_ipo_price", "공모가고정": "manual_ipo_price_locked",
    "최초상장주식수": "initial_shares", "현재상장주식수": "current_shares",
    "상장주식수기준일": "shares_date", "종가": "close_price",
    "콘텐츠링크": "content_url", "검증상태": "validation_status",
    "검증사유": "validation_reason", "메모": "memo",
}

CORRECTION_PATH = ROOT_DIR / "data" / "correction_tasks.json"
CORRECTION_TAB = "보정작업"
CORRECTION_HEADERS = [
    "작업ID", "대상", "기업명", "코드", "항목", "구분", "기간",
    "자동값", "수기값", "수기일자", "수기수량", "보정방식", "처리상태", "메모", "이벤트ID",
]
CORRECTION_KEYS = dict(zip(CORRECTION_HEADERS, CORRECTION_COLUMNS))


# 작업목록 탭 — 운영자 보완 입력의 단일 창구. 배치가 "다 채운 행"만 수거해 표준
# 통로(IPO종목 수동공모가 / 수기입력)로 옮기고, 남은 갭만 다시 나열한다.
# 규칙: 빈칸 = 무시(다음 목록에 유지), 전부 채움 = 반영, 일부만 채움 = 값 보존.
WORKLIST_TAB = "작업목록"
WORKLIST_BACKUP_PATH = ROOT_DIR / "data" / "worklist_backup.json"


IPO_SCHEDULE_PATH = ROOT_DIR / "data" / "ipo_schedule.json"
IPO_SCHEDULE_TAB = "IPO일정"
IPO_SCHEDULE_VIEW_TAB = IPO_SCHEDULE_TAB
IPO_SCHEDULE_BACKUP_PATH = ROOT_DIR / "data" / "ipo_schedule_sheet_backup.json"
# 배치가 마지막으로 쓴 값 스냅샷 — 시트 값과 이게 다르면 "사용자 수정"으로 판정한다
IPO_SCHEDULE_WRITTEN_PATH = ROOT_DIR / "data" / "ipo_sheet_written.json"
COMMIT_TIER_ORDER = ["미확약", "15일", "1개월", "3개월", "6개월"]
IPO_SCHEDULE_HEADERS = [
    "기업명", "상태", "시장", "주관사", "희망가액", "확정공모가", "공모주식수",
    "수요예측일", "청약일", "상장일", "검토", "IPO취소", "수요예측경쟁률", "개인청약경쟁률",
    "신청_미확약", "신청_15일", "신청_1개월", "신청_3개월", "신청_6개월",
    "배정_미확약", "배정_15일", "배정_1개월", "배정_3개월", "배정_6개월",
    "콘텐츠링크",
]
IPO_SCHEDULE_VIEW_HEADERS = [
    "고정", "노출", "기업명", "희망가액", "공모주식수", "수요예측일", "청약일",
    "수요예측경쟁률", "개인청약경쟁률", "주관사", "검증상태", "검증사유",
    "DART기업코드", "이벤트ID", "콘텐츠링크",
]
# 사용자가 수정하면 파싱보다 우선하는 열 → 잠글 item 필드 매핑
IPO_EDITABLE_COLUMNS = {
    "확정공모가": ["final_price"],
    "수요예측일": ["forecast_start", "forecast_end"],
    "청약일": ["sub_start", "sub_end"],
    "상장일": ["listing_date"],
}


# 수기입력 탭 — 운영자가 필수값만 채우면 배치가 나머지를 자동으로 채워 편입한다
MANUAL_EVENTS_PATH = ROOT_DIR / "data" / "manual_events.json"
MANUAL_EVENT_TAB = "수기입력"
MANUAL_EVENT_HEADERS = ["종목코드", "구분", "락업기간", "해제일", "물량"]
MANUAL_EVENT_KEYS = {
    "종목코드": "code",
    "구분": "category",
    "락업기간": "period",
    "해제일": "date",
    "물량": "qty",
}


HEADER_KO = {
    "event_id": "이벤트ID",
    "code": "종목코드",
    "name": "종목명",
    "market": "시장",
    "listing_date": "상장일",
    "shares": "상장주식수",
    "current_shares": "최근상장주식수",
    "shares_date": "상장주식수기준일",
    "close_price": "종가",
    "ipo_price": "공모가",
    "category": "구분",
    "type": "원본유형",
    "period": "락업기간",
    "planned_date": "예정해제일",
    "planned_tradable_date": "예정거래가능일",
    "planned_date_display": "예정일표시",
    "planned_qty": "예정물량",
    "planned_pct": "예정비중(%)",
    "dart_rcp": "DART접수번호",
    "dart_source": "DART출처",
    "parse_note": "파싱메모",
    "api_return_date": "API반환일",
    "api_return_qty": "API반환물량",
    "api_reason": "API사유",
    "manual_date": "수동해제일",
    "manual_qty": "수동물량",
    "manual_lock": "수동값사용(Y/N)",
    "manual_mode": "수기모드",
    "sheet_visible": "노출(Y/N)",
    "final_date": "최종해제일",
    "final_tradable_date": "최종거래가능일",
    "final_date_display": "최종일표시",
    "final_qty": "최종물량",
    "final_pct": "최종비중(%)",
    "status": "상태",
    "review_needed": "검토필요(Y/N)",
    "memo": "운영자메모",
    "review_id": "검토ID",
    "review_type": "검토유형",
    "target": "대상",
    "comparison": "비교내용",
    "first_detected": "최초감지일",
    "last_detected": "최근감지일",
    "resolved_at": "해결일",
    "operator_memo": "처리메모",
    "updated_at": "갱신시각",
    "detected_at": "감지시각",
    "issue": "검토사유",
    "time": "변경시각",
    "field": "변경필드",
    "old_value": "이전값",
    "new_value": "변경값",
    "reason": "변경사유",
    "classification": "판정상태",
    "classification_reason": "판정사유",
    "rcp": "DART접수번호",
    "detected_bas_dd": "상장감지기준일",
    "review_decision": "검토결과",
    "review_memo": "운영자메모",
}
HEADER_INTERNAL = {label: key for key, label in HEADER_KO.items()}


# 검토필요 탭은 폐지 — 운영자 보완 입력은 작업목록 탭으로 일원화 (review_needed.csv는 내부 기록용으로만 유지)
TAB_CONFIG = [("로그", "lockup_log.csv", LOG_COLUMNS)]


ADMIN_TAB_CONFIG = [("IPO기관", "IPO기관", IPO_ADMIN_SHEET_COLUMNS), ("기존주주", "구주·보호예수", FLOAT_ADMIN_SHEET_COLUMNS)]
LEGACY_ADMIN_TABS = ("운영_락업일정", "락업이벤트", "lockup_admin")

SIMPLE_SHEET_STATE_PATH = ROOT_DIR / "data" / "simple_sheet_state.json"
IPO_INSTITUTION_HEADERS = [
    "고정", "노출", "종목명", "종목코드", "기간", "신청물량", "배정물량",
    "배정률(%)", "배정비중(%)", "해제일", "검증상태", "검증사유", "이벤트ID", "DART기업코드",
]
HOLDER_HEADERS = [
    "고정", "노출", "종목명", "종목코드", "락업기간", "해제일", "물량",
    "현재주식수기준비중(%)", "검증상태", "검증사유", "이벤트ID",
]


MANUAL_COLUMNS = ("manual_lock", "manual_date", "manual_qty", "manual_mode", "sheet_visible", "memo")
REVIEW_MANUAL_COLUMNS = ("status", "operator_memo")


SHEET_INTEGER_COLUMNS = {
    "close_price", "ipo_price", "shares", "current_shares",
    "planned_qty", "api_return_qty", "manual_qty", "final_qty",
    "old_value", "new_value",
}


def format_sheet_value(column: str, value: object) -> object:
    if column not in SHEET_INTEGER_COLUMNS:
        return value
    text = str(value or "").strip().replace(",", "")
    if not text:
        return ""
    sign = "-" if text.startswith("-") else ""
    number = text[1:] if sign else text
    if not number.isdigit():
        return value
    return f"{sign}{int(number):,}"




def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Sheets 동기화")
    parser.add_argument("command", choices=["pull-admin", "push-all", "reset-all"])
    return parser.parse_args()




def build_client() -> gspread.Client:
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw_json:
        return gspread.service_account_from_dict(json.loads(raw_json))


    configured_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if configured_file:
        return gspread.service_account(filename=configured_file)


    hits = sorted(glob.glob(str(ROOT_DIR / "project-*.json")))
    hits.extend(sorted(glob.glob(str(ROOT_DIR / "*service-account*.json"))))
    if not hits:
        raise FileNotFoundError(
            "Google 서비스 계정 인증정보가 없습니다. "
            "GOOGLE_SERVICE_ACCOUNT_JSON 또는 GOOGLE_SERVICE_ACCOUNT_FILE을 설정하세요."
        )
    return gspread.service_account(filename=hits[0])




def sheet_id() -> str:
    return os.getenv("GOOGLE_SHEET_ID", DEFAULT_SHEET_ID).strip()




def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]




def write_csv_dicts(path: Path, rows: list[dict[str, str]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({column: row.get(column, "") for column in columns} for row in rows)


def read_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [dict(row) for row in value] if isinstance(value, list) else []


def read_schedule_data() -> dict:
    if not IPO_SCHEDULE_PATH.exists():
        return {"updated": "", "items": [], "past_items": [], "history": []}
    try:
        value = json.loads(IPO_SCHEDULE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"updated": "", "items": [], "past_items": [], "history": []}
    return value if isinstance(value, dict) else {"updated": "", "items": [], "past_items": [], "history": []}


def load_simple_sheet_state() -> dict:
    if not SIMPLE_SHEET_STATE_PATH.exists():
        return {"management": {}, "schedule": {}, "ipo_institution": {}, "holders": {}}
    try:
        value = json.loads(SIMPLE_SHEET_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        value = {}
    return {
        key: dict(value.get(key) or {})
        for key in ("management", "schedule", "ipo_institution", "holders")
    }


def yn(value: object, default: str = "N") -> str:
    text = str(value or "").strip().upper()
    if text in {"TRUE", "Y", "예", "노출", "관리"}:
        return "Y"
    if text in {"FALSE", "N", "아니오", "비공개", "제외"}:
        return "N"
    return default


def number(value: object) -> int:
    text = str(value or "").replace(",", "").replace("원", "").strip()
    try:
        return int(float(text)) if text else 0
    except ValueError:
        return 0


def decimal(value: object) -> float:
    text = str(value or "").replace(",", "").replace("%", "").replace(":1", "").strip()
    try:
        return float(text) if text else 0.0
    except ValueError:
        return 0.0


def all_schedule_items(schedule: dict) -> list[dict]:
    return list(schedule.get("items") or []) + list(schedule.get("past_items") or [])


def item_key(item: dict) -> str:
    return str(item.get("corp_code") or f"name:{norm_name(item.get('name'))}")


def table_records(values: list[list[str]], key_map: dict[str, str]) -> list[dict[str, str]]:
    if len(values) < 2:
        return []
    headers = [key_map.get(cell.strip(), cell.strip()) for cell in values[0]]
    out: list[dict[str, str]] = []
    for raw in values[1:]:
        padded = raw + [""] * max(0, len(headers) - len(raw))
        row = {headers[index]: padded[index].strip() for index in range(len(headers))}
        if any(row.get(key, "") for key in key_map.values()):
            out.append(row)
    return out


def has_sheet_headers(spreadsheet: gspread.Spreadsheet, title: str, required: set[str]) -> bool:
    try:
        values = spreadsheet.worksheet(title).get_all_values()
    except gspread.WorksheetNotFound:
        return False
    headers = {str(value).strip() for value in (values[0] if values else [])}
    return required.issubset(headers)




def price_date_suffix() -> str:
    """종가 기준일(예: '26-07-08'). site_data.json의 updated 값에서 가져온다."""
    try:
        data = json.loads((ROOT_DIR / "data" / "site_data.json").read_text(encoding="utf-8"))
        updated = str(data.get("updated", ""))
        return updated[2:] if len(updated) == 10 else ""
    except Exception:
        return ""




def header_label(column: str) -> str:
    label = HEADER_KO.get(column, column)
    if column == "close_price":
        suffix = price_date_suffix()
        if suffix:
            return f"{label}({suffix})"
    if column == "current_shares":
        try:
            data = json.loads((ROOT_DIR / "data" / "site_data.json").read_text(encoding="utf-8"))
            suffix = str(data.get("shares_updated") or data.get("updated") or "")
            if len(suffix) == 10:
                return f"상장주식수({suffix})"
        except Exception:
            pass
    return label




def internal_header(value: str) -> str:
    cleaned = value.strip()
    if cleaned == "처리상태":
        return "status"
    if cleaned in HEADER_INTERNAL:
        return HEADER_INTERNAL[cleaned]
    # "종가(26-07-08)"처럼 기준일이 붙은 종가 헤더도 인식
    if cleaned.startswith("종가("):
        return "close_price"
    if cleaned.startswith("상장주식수("):
        return "current_shares"
    return cleaned




def worksheet_records(ws: gspread.Worksheet) -> list[dict[str, str]]:
    values = ws.get_all_values()
    if len(values) < 2:
        return []
    headers = [internal_header(value) for value in values[0]]
    records: list[dict[str, str]] = []
    for row in values[1:]:
        padded = row + [""] * max(0, len(headers) - len(row))
        record = {headers[index]: padded[index] for index in range(len(headers))}
        if any(value.strip() for value in record.values()):
            records.append(record)
    return records




def admin_worksheets(spreadsheet: gspread.Spreadsheet) -> list[gspread.Worksheet]:
    worksheets: list[gspread.Worksheet] = []
    for title, _, _ in ADMIN_TAB_CONFIG:
        try:
            worksheets.append(spreadsheet.worksheet(title))
        except gspread.WorksheetNotFound:
            pass
    if worksheets:
        return worksheets
    for title in LEGACY_ADMIN_TABS:
        try:
            return [spreadsheet.worksheet(title)]
        except gspread.WorksheetNotFound:
            pass
    return [spreadsheet.get_worksheet(0)]


def pull_stock_management(spreadsheet: gspread.Spreadsheet) -> None:
    """새 종목관리 탭을 기존 파일과 병합해 편입/노출/고정제외 명령을 적용한다.

    탭이 아직 없는 첫 실행은 커밋된 JSON과 기존 시트에서 만든 파일을 그대로
    부트스트랩한다. 따라서 기존 종목을 비우거나 전체 DART 재파싱하지 않는다.
    """
    saved = read_json_list(STOCK_MANAGEMENT_PATH)
    targets = read_json_list(IPO_TARGETS_PATH)
    schedule = read_schedule_data()
    sheet_rows: list[dict[str, str]] = []
    try:
        values = spreadsheet.worksheet(STOCK_MANAGEMENT_TAB).get_all_values()
        if {"관리", "홈페이지노출", "기업명"}.issubset({cell.strip() for cell in (values[0] if values else [])}):
            sheet_rows = table_records(values, STOCK_MANAGEMENT_KEYS)
    except gspread.WorksheetNotFound:
        pass

    state = load_simple_sheet_state().get("management", {})
    for row in sheet_rows:
        key = str(row.get("corp_code") or f"name:{norm_name(row.get('name'))}")
        previous = dict(state.get(key) or {})
        managed = yn(row.get("management_status"), "Y")
        visible = yn(row.get("visibility"), "Y")
        row["management_status"] = "제외고정" if managed == "N" else (
            "수동편입" if not row.get("corp_code") and not row.get("stock_code") else "자동"
        )
        row["visibility"] = "노출" if visible == "Y" else "비공개"
        row["scope"] = "IPO일정+락업"
        for field, lock_field, edited_field in (
            ("listing_date", "listing_date_locked", "listing_date_edited"),
            ("manual_ipo_price", "manual_ipo_price_locked", "manual_ipo_price_edited"),
        ):
            row[lock_field] = yn(row.get(lock_field), "N")
            current = str(row.get(field) or "").replace(",", "").strip()
            old = str(previous.get(field) or "").replace(",", "").strip()
            changed = bool(previous and current != old)
            row[edited_field] = "Y" if changed else "N"
            # 공식값이 이미 있으면 고정하지 않은 수기 수정은 즉시 되돌린다.
            if changed and row[lock_field] != "Y" and old:
                row[field] = previous.get(field) or ""
                row[edited_field] = "N"
        code = str(row.get("stock_code") or "").strip()
        if code.isdigit() and len(code) < 6:
            row["stock_code"] = code.zfill(6)
        corp = str(row.get("corp_code") or "").strip()
        if corp.isdigit() and len(corp) < 8:
            row["corp_code"] = corp.zfill(8)
        if row.get("name") and not row.get("management_status"):
            row["management_status"] = "수동편입"

    management = merge_stock_management(sheet_rows or saved, targets, schedule)
    targets, schedule, seed_names = apply_stock_management(management, targets, schedule)

    STOCK_MANAGEMENT_PATH.write_text(json.dumps(management, ensure_ascii=False, indent=2), encoding="utf-8")
    IPO_TARGETS_PATH.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")
    IPO_SCHEDULE_PATH.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT_DIR / "data" / "ipo_seed_names.json").write_text(
        json.dumps(seed_names, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    source = "종목관리 탭" if sheet_rows else "기존 데이터 이관"
    print(f"[SHEET] {source}: {len(management)}종목 (DART 재조회 요청 {len(seed_names)}종목)", file=sys.stderr)


def _find_schedule_item(schedule: dict, code: str, name: str) -> dict | None:
    all_items = list(schedule.get("items") or []) + list(schedule.get("past_items") or [])
    if code:
        found = next((item for item in all_items if str(item.get("corp_code") or "") == code), None)
        if found:
            return found
    key = norm_name(name)
    return next((item for item in all_items if key and norm_name(item.get("name")) == key), None)


def pull_correction_tasks(spreadsheet: gspread.Spreadsheet) -> None:
    """보정작업의 입력을 기존 표준 파일에 적용한다. 새 탭 값이 구형 탭보다 우선한다."""
    saved = read_json_list(CORRECTION_PATH)
    sheet_rows: list[dict[str, str]] = []
    try:
        sheet_rows = table_records(spreadsheet.worksheet(CORRECTION_TAB).get_all_values(), CORRECTION_KEYS)
    except gspread.WorksheetNotFound:
        pass

    # 행 삭제는 명령으로 해석하지 않는다. 취소는 처리상태=취소로 명시한다.
    by_id = {str(row.get("task_id") or ""): dict(row) for row in saved if row.get("task_id")}
    for index, row in enumerate(sheet_rows, start=2):
        task_id = str(row.get("task_id") or "").strip()
        if not task_id and (row.get("name") or row.get("code")) and row.get("field"):
            task_id = "manual:{target}:{code}:{name}:{field}:{period}:{index}".format(
                target=row.get("target") or "", code=row.get("code") or "",
                name=norm_name(row.get("name")), field=row.get("field") or "",
                period=row.get("period") or "", index=index,
            )
            row["task_id"] = task_id
        if task_id:
            by_id[task_id] = {column: str(row.get(column) or "") for column in CORRECTION_COLUMNS}
    tasks = list(by_id.values())

    targets = read_json_list(IPO_TARGETS_PATH)
    schedule = read_schedule_data()
    admin_rows = read_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv")
    manual_events = read_json_list(MANUAL_EVENTS_PATH)
    admin_by_id = {row.get("event_id", ""): row for row in admin_rows if row.get("event_id")}
    target_by_code = {str(row.get("code") or ""): row for row in targets if row.get("code")}
    manual_keys = {
        (str(row.get("code") or ""), str(row.get("category") or ""), str(row.get("period") or ""), str(row.get("date") or ""))
        for row in manual_events
    }

    from datetime import date as _date
    from scripts.utils.dates import calc_release_date

    changed_schedule = False
    for row in tasks:
        if str(row.get("status") or "") in {"자동해결", "취소"}:
            continue
        target = str(row.get("target") or "")
        if target == "IPO일정":
            item = _find_schedule_item(schedule, str(row.get("code") or ""), str(row.get("name") or ""))
            if not item:
                continue
            if str(row.get("override_mode") or "") == "자동복귀":
                fields = SCHEDULE_FIELD_MAP.get(str(row.get("field") or "")) or ()
                old_value = next((str(item.get(field) or "") for field in fields if item.get(field)), "")
                if release_schedule_correction(item, row):
                    schedule.setdefault("history", []).append({
                        "date": _date.today().isoformat(), "name": item.get("name") or row.get("name") or "",
                        "type": "자동복귀", "field": row.get("field") or "",
                        "old": old_value, "new": "자동 수집 대기",
                    })
                    row["status"] = "적용"
                    changed_schedule = True
                continue
            if str(row.get("field") or "") == "기관신청물량":
                if apply_commit_apply_correction(item, row):
                    schedule.setdefault("history", []).append({
                        "date": _date.today().isoformat(), "name": item.get("name") or row.get("name") or "",
                        "type": "수기변경", "field": f"기관신청물량({row.get('period') or ''})",
                        "old": "", "new": row.get("manual_qty") or row.get("manual_value") or "",
                    })
                    row["status"] = "적용"
                    changed_schedule = True
                continue
            old_value = next((str(item.get(field) or "") for field in SCHEDULE_FIELD_MAP.get(str(row.get("field") or ""), ()) if item.get(field)), "")
            if apply_schedule_correction(item, row):
                schedule.setdefault("history", []).append({
                    "date": _date.today().isoformat(), "name": item.get("name") or row.get("name") or "",
                    "type": "수기변경", "field": row.get("field") or "",
                    "old": old_value, "new": row.get("manual_value") or "",
                })
                row["status"] = "적용"
                changed_schedule = True
            continue

        code = str(row.get("code") or "").strip()
        field = str(row.get("field") or "")
        if field == "공모가":
            digits = "".join(ch for ch in str(row.get("manual_value") or "") if ch.isdigit())
            target_row = target_by_code.get(code)
            if target_row and digits:
                target_row["manual_ipo_price"] = digits
                row["status"] = "적용"
        elif field == "기존이벤트보정":
            event = admin_by_id.get(str(row.get("event_id") or ""))
            if event and (row.get("manual_date") or row.get("manual_qty")):
                event["manual_date"] = str(row.get("manual_date") or "")
                event["manual_qty"] = str(row.get("manual_qty") or "").replace(",", "")
                event["manual_lock"] = "Y"
                event["memo"] = str(row.get("memo") or "")
                row["status"] = "적용"
        elif field == "락업이벤트":
            period = str(row.get("period") or "").strip()
            qty = str(row.get("manual_qty") or "").replace(",", "").strip()
            release_date = str(row.get("manual_date") or "").strip()
            target_row = target_by_code.get(code) or {}
            if not release_date and period and target_row.get("listing_date"):
                try:
                    _, _, release_date = calc_release_date(str(target_row["listing_date"]), period)
                except Exception:
                    release_date = ""
            category = str(row.get("category") or "").strip()
            key = (code, category, period, release_date)
            if code and category in {"IPO기관", "기존주주"} and period and qty.isdigit() and release_date and key not in manual_keys:
                manual_events.append({"code": code, "category": category, "period": period, "date": release_date, "qty": qty})
                manual_keys.add(key)
                row["manual_date"] = release_date
                row["status"] = "적용"

    if changed_schedule:
        schedule["history"] = list(schedule.get("history") or [])[-500:]
    IPO_TARGETS_PATH.write_text(json.dumps(targets, ensure_ascii=False, indent=2), encoding="utf-8")
    IPO_SCHEDULE_PATH.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    MANUAL_EVENTS_PATH.write_text(json.dumps(manual_events, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv", admin_rows, ADMIN_COLUMNS)
    CORRECTION_PATH.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8")
    if sheet_rows:
        print(f"[SHEET] 보정작업 입력 반영: {len(sheet_rows)}행", file=sys.stderr)


def _schedule_snapshot(item: dict) -> dict[str, str]:
    low, high = number(item.get("band_low")), number(item.get("band_high"))
    return {
        "band": f"{low:,} ~ {high:,}" if low and high else "",
        "offer_shares": f"{number(item.get('offer_shares')):,}" if number(item.get("offer_shares")) else "",
        "forecast": _date_range_text(item.get("forecast_start"), item.get("forecast_end")),
        "subscription": _date_range_text(item.get("sub_start"), item.get("sub_end")),
        "demand_ratio": str(item.get("demand_ratio") or ""),
        "sub_ratio": str(item.get("sub_ratio") or ""),
        "underwriter": str(item.get("underwriter") or ""),
        "content_url": str(item.get("content_url") or ""),
    }


def _date_range_text(start: object, end: object) -> str:
    left, right = str(start or ""), str(end or "")
    return left if left and (not right or left == right) else (f"{left} ~ {right}" if left else "")


def _apply_schedule_cell(item: dict, key: str, value: str) -> tuple[str, ...]:
    if key == "band":
        nums = [number(token) for token in value.replace("~", " ").split() if number(token)]
        if len(nums) >= 2:
            item["band_low"], item["band_high"] = nums[0], nums[-1]
        return ("band_low", "band_high")
    if key == "offer_shares":
        if number(value):
            item["offer_shares"] = number(value)
        return ("offer_shares",)
    if key in {"forecast", "subscription"}:
        dates = _parse_sheet_dates(value)
        fields = ("forecast_start", "forecast_end") if key == "forecast" else ("sub_start", "sub_end")
        if dates:
            item[fields[0]], item[fields[1]] = dates[0], dates[-1]
        return fields
    if key in {"demand_ratio", "sub_ratio"}:
        if decimal(value):
            item[key] = decimal(value)
        return (key,)
    if key == "underwriter":
        item["underwriter"] = value
        return ("underwriter",)
    if key == "content_url":
        item["content_url"] = value
        return ("content_url",)
    return ()


def pull_simple_schedule_tab(spreadsheet: gspread.Spreadsheet) -> None:
    try:
        values = spreadsheet.worksheet(IPO_SCHEDULE_TAB).get_all_values()
    except gspread.WorksheetNotFound:
        return
    if not {"고정", "노출", "기업명"}.issubset({cell.strip() for cell in (values[0] if values else [])}):
        return
    key_map = {
        "고정": "locked", "노출": "visible", "기업명": "name", "희망가액": "band",
        "공모주식수": "offer_shares", "수요예측일": "forecast", "청약일": "subscription",
        "수요예측경쟁률": "demand_ratio", "개인청약경쟁률": "sub_ratio", "주관사": "underwriter",
        "DART기업코드": "corp_code", "콘텐츠링크": "content_url",
    }
    rows = table_records(values, key_map)
    if not rows:
        return
    schedule = read_schedule_data()
    state = load_simple_sheet_state().get("schedule", {})
    items = all_schedule_items(schedule)
    history = list(schedule.get("history") or [])
    today = __import__("datetime").date.today().isoformat()
    domain = {"band_low", "band_high", "offer_shares", "forecast_start", "forecast_end", "sub_start", "sub_end", "demand_ratio", "sub_ratio", "underwriter"}
    changed = 0
    for row in rows:
        item = _find_schedule_item(schedule, str(row.get("corp_code") or ""), str(row.get("name") or ""))
        if not item:
            item = {
                "corp_code": row.get("corp_code") or f"manual-{norm_name(row.get('name'))}",
                "name": row.get("name") or "", "manual_entry": True,
                "review_approved": True, "review_pending": False,
            }
            schedule.setdefault("items", []).append(item)
            items.append(item)
        key = item_key(item)
        previous = dict(state.get(key) or {})
        locked = yn(row.get("locked"), "N") == "Y"
        manual_fields = set(item.get("manual_fields") or [])
        provisional = set(item.get("provisional_fields") or [])
        if locked:
            # 체크만 해도 현재 표시된 이 탭의 값 전체를 고정한다.
            manual_fields.update(field for field in domain if item.get(field) not in (None, "", 0))
            provisional.difference_update(domain)
        else:
            manual_fields.difference_update(domain)
        for cell_key in ("band", "offer_shares", "forecast", "subscription", "demand_ratio", "sub_ratio", "underwriter", "content_url"):
            current = str(row.get(cell_key) or "").strip()
            old = str(previous.get(cell_key) or "").strip()
            if not previous or current == old:
                continue
            if not locked and old:
                continue
            fields = set(_apply_schedule_cell(item, cell_key, current))
            if locked:
                manual_fields.update(fields)
                provisional.difference_update(fields)
            else:
                provisional.update(fields)
            history.append({"date": today, "name": item.get("name") or "", "type": "수기변경", "field": cell_key, "old": old, "new": current})
            changed += 1
        if manual_fields:
            item["manual_fields"] = sorted(manual_fields)
        else:
            item.pop("manual_fields", None)
        if provisional:
            item["provisional_fields"] = sorted(provisional)
        else:
            item.pop("provisional_fields", None)
        item["schedule_hidden"] = yn(row.get("visible"), "Y") != "Y"
    schedule["history"] = history[-500:]
    IPO_SCHEDULE_PATH.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    if changed:
        print(f"[SHEET] IPO일정 직접 수정 {changed}개 반영", file=sys.stderr)


def _schedule_by_corp_or_name(schedule: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    by_corp, by_name = {}, {}
    for item in all_schedule_items(schedule):
        if item.get("corp_code"):
            by_corp[str(item["corp_code"])] = item
        if norm_name(item.get("name")):
            by_name[norm_name(item.get("name"))] = item
    return by_corp, by_name


def pull_simple_event_tabs(spreadsheet: gspread.Spreadsheet) -> None:
    admin_path = ROOT_DIR / "data" / "lockup_admin.csv"
    admin_rows = read_csv_dicts(admin_path)
    by_id = {str(row.get("event_id") or ""): row for row in admin_rows if row.get("event_id")}
    schedule = read_schedule_data()
    history = list(schedule.get("history") or [])
    today = date.today().isoformat()
    by_corp, by_name = _schedule_by_corp_or_name(schedule)
    state = load_simple_sheet_state()
    manual_events = read_json_list(MANUAL_EVENTS_PATH)
    manual_event_keys = {
        (str(row.get("code") or ""), str(row.get("category") or ""), str(row.get("period") or ""), str(row.get("date") or ""))
        for row in manual_events
    }

    def pull_tab(title: str, kind: str) -> None:
        try:
            values = spreadsheet.worksheet(title).get_all_values()
        except gspread.WorksheetNotFound:
            return
        if not {"고정", "노출"}.issubset({cell.strip() for cell in (values[0] if values else [])}):
            return
        headers = IPO_INSTITUTION_HEADERS if kind == "ipo" else HOLDER_HEADERS
        key_map = {header: header for header in headers}
        rows = table_records(values, key_map)
        previous_rows = dict(state.get("ipo_institution" if kind == "ipo" else "holders") or {})
        seen: set[str] = set()
        for index, raw in enumerate(rows, start=2):
            event_id = str(raw.get("이벤트ID") or "").strip()
            corp_code = str(raw.get("DART기업코드") or "").strip()
            period = str(raw.get("기간") or raw.get("락업기간") or "").strip()
            key = event_id or f"{corp_code or norm_name(raw.get('종목명'))}:{period}:{index}"
            seen.add(key)
            previous = dict(previous_rows.get(key) or {})
            locked = yn(raw.get("고정"), "N") == "Y"
            visible = yn(raw.get("노출"), "Y")
            event = by_id.get(event_id)
            if event:
                old_visible, old_lock = event.get("sheet_visible") or "Y", event.get("manual_lock") or "N"
                event["sheet_visible"] = visible
                event["manual_lock"] = "Y" if locked else "N"
                if old_visible != visible:
                    history.append({"date": today, "name": event.get("name") or "", "type": "노출변경", "field": f"{kind}:{period}", "old": old_visible, "new": visible})
                if old_lock != event["manual_lock"]:
                    history.append({"date": today, "name": event.get("name") or "", "type": "고정변경", "field": f"{kind}:{period}", "old": old_lock, "new": event["manual_lock"]})
                for sheet_field, event_field in (("배정물량", "manual_qty"), ("물량", "manual_qty"), ("해제일", "manual_date")):
                    current = str(raw.get(sheet_field) or "").replace(",", "").strip()
                    old = str(previous.get(sheet_field) or "").replace(",", "").strip()
                    if current and (locked or (previous and current != old and not old)):
                        event[event_field] = current
                        event["manual_mode"] = "고정" if locked else "임시"
                        if current != old:
                            history.append({"date": today, "name": event.get("name") or "", "type": "수기변경", "field": sheet_field, "old": old, "new": current})
            elif kind == "holder" and raw.get("종목코드") and period and raw.get("해제일") and number(raw.get("물량")):
                manual_key = (str(raw.get("종목코드") or "").zfill(6), "기존주주", period, str(raw.get("해제일") or ""))
                if manual_key not in manual_event_keys:
                    manual_events.append({
                        "code": manual_key[0], "category": "기존주주",
                        "period": period, "date": manual_key[3], "qty": number(raw.get("물량")),
                        "sheet_visible": visible, "manual_lock": "Y" if locked else "N",
                    })
                    manual_event_keys.add(manual_key)
            if kind == "ipo":
                item = by_corp.get(corp_code) or by_name.get(norm_name(raw.get("종목명")))
                if item:
                    manual = dict(item.get("manual_commit_apply") or {})
                    current = number(raw.get("신청물량"))
                    old = number(previous.get("신청물량"))
                    if current and (locked or (previous and current != old and not old)):
                        manual[period] = {"qty": current, "locked": locked, "visible": visible == "Y"}
                        if current != old:
                            history.append({"date": today, "name": item.get("name") or "", "type": "수기변경", "field": f"기관신청물량({period})", "old": old, "new": current})
                    elif current and previous and yn(previous.get("노출"), "Y") != visible:
                        manual[period] = {"qty": current, "locked": locked, "visible": visible == "Y"}
                    elif period in manual:
                        manual[period]["locked"] = locked
                        manual[period]["visible"] = visible == "Y"
                    item["manual_commit_apply"] = manual
        for missing in set(previous_rows) - seen:
            previous = previous_rows[missing]
            event = by_id.get(str(previous.get("이벤트ID") or ""))
            if event:
                event["sheet_visible"] = "N"
                history.append({"date": today, "name": event.get("name") or "", "type": "행삭제", "field": f"{kind}:{event.get('period') or ''}", "old": "노출", "new": "비노출"})
            elif kind == "ipo":
                item = by_corp.get(str(previous.get("DART기업코드") or "")) or by_name.get(norm_name(previous.get("종목명")))
                period = str(previous.get("기간") or "")
                qty = number(previous.get("신청물량"))
                if item and period and qty:
                    manual = dict(item.get("manual_commit_apply") or {})
                    manual[period] = {"qty": qty, "locked": False, "visible": False}
                    item["manual_commit_apply"] = manual
                    history.append({"date": today, "name": item.get("name") or "", "type": "행삭제", "field": f"ipo:{period}", "old": "노출", "new": "비노출"})

    pull_tab("IPO기관", "ipo")
    pull_tab("기존주주", "holder")
    write_csv_dicts(admin_path, admin_rows, ADMIN_COLUMNS)
    schedule["history"] = history[-500:]
    IPO_SCHEDULE_PATH.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
    MANUAL_EVENTS_PATH.write_text(json.dumps(manual_events, ensure_ascii=False, indent=2), encoding="utf-8")




def pull_admin(spreadsheet: gspread.Spreadsheet) -> None:
    csv_path = ROOT_DIR / "data" / "lockup_admin.csv"
    local_rows = read_csv_dicts(csv_path)
    new_structure = False
    new_structure = all((
        has_sheet_headers(spreadsheet, STOCK_MANAGEMENT_TAB, {"관리", "홈페이지노출", "기업명"}),
        has_sheet_headers(spreadsheet, IPO_SCHEDULE_TAB, {"고정", "노출", "기업명"}),
        has_sheet_headers(spreadsheet, "IPO기관", {"고정", "노출", "기간"}),
        has_sheet_headers(spreadsheet, "기존주주", {"고정", "노출", "락업기간"}),
    ))

    if local_rows and not new_structure:
        sheet_rows: list[dict[str, str]] = []
        for worksheet in admin_worksheets(spreadsheet):
            sheet_rows.extend(worksheet_records(worksheet))
        sheet_by_id = {row.get("event_id", ""): row for row in sheet_rows if row.get("event_id")}
        updated = 0
        for local in local_rows:
            sheet_row = sheet_by_id.get(local.get("event_id", ""))
            if not sheet_row:
                continue
            changed = False
            for column in MANUAL_COLUMNS:
                value = sheet_row.get(column, "")
                if local.get(column, "") != value:
                    local[column] = value
                    changed = True
            if changed:
                updated += 1
        write_csv_dicts(csv_path, local_rows, ADMIN_COLUMNS)
        print(f"[SHEET] 기존 락업 수동값 이관: {updated}개 행", file=sys.stderr)
    elif not local_rows:
        print("[SHEET] lockup_admin.csv 없음 — 종목관리/보정작업 이관은 계속합니다.", file=sys.stderr)
    else:
        print("[SHEET] 새 관리 탭 사용 — 구형 락업 입력 탭은 읽지 않습니다.", file=sys.stderr)

    # 첫 배치에만 구형 탭을 읽는다. 새 탭 생성 후에는 오래된 복제본이 다시 원천이 되지 않는다.
    if not new_structure:
        pull_worklist(spreadsheet)
        pull_ipo_targets(spreadsheet)
        pull_manual_events(spreadsheet)
    # 보정작업은 첫 마이그레이션 때만 읽는다. 이후에는 각 도메인 탭에서 직접 수정한다.
    pull_stock_management(spreadsheet)
    if not new_structure:
        pull_correction_tasks(spreadsheet)
    pull_simple_schedule_tab(spreadsheet)
    pull_simple_event_tabs(spreadsheet)
    pull_holidays(spreadsheet)




def pull_review_status(spreadsheet: gspread.Spreadsheet) -> None:
    """검토 탭에서 관리자가 선택한 해결상태와 처리메모를 보존한다."""
    path = ROOT_DIR / "data" / "review_needed.csv"
    rows = read_csv_dicts(path)
    if not rows:
        return
    try:
        sheet_rows = worksheet_records(spreadsheet.worksheet("검토필요"))
    except gspread.WorksheetNotFound:
        return
    by_id = {row.get("review_id", ""): row for row in sheet_rows if row.get("review_id")}
    for row in rows:
        sheet_row = by_id.get(row.get("review_id", ""))
        if not sheet_row:
            continue
        for column in REVIEW_MANUAL_COLUMNS:
            value = sheet_row.get(column, "").strip()
            if value:
                row[column] = value
    write_csv_dicts(path, rows, list(rows[0].keys()))




def pull_review_decisions(spreadsheet: gspread.Spreadsheet) -> None:
    try:
        sheet_rows = worksheet_records(spreadsheet.worksheet("상장후보_검토"))
    except gspread.WorksheetNotFound:
        return


    existing = []
    if REVIEW_DECISIONS_PATH.exists():
        existing = json.loads(REVIEW_DECISIONS_PATH.read_text(encoding="utf-8"))
    by_code = {row.get("code", ""): row for row in existing if row.get("code")}


    for row in sheet_rows:
        decision = row.get("review_decision", "").strip()
        code = row.get("code", "").strip()
        if not code or decision not in {"IPO", "비IPO"}:
            continue
        by_code[code] = {
            **{column: row.get(column, "") for column in UNIVERSE_REVIEW_COLUMNS},
            "review_decision": decision,
            "review_memo": row.get("review_memo", "").strip(),
        }


    decisions = sorted(by_code.values(), key=lambda row: (row.get("listing_date", ""), row.get("code", "")))
    REVIEW_DECISIONS_PATH.write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[SHEET] 상장후보 검토결과 내려받기: {len(decisions)}개", file=sys.stderr)




def ensure_manual_event_tab(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    """수기입력 탭이 없으면 헤더·서식과 함께 만든다. 있으면 내용은 절대 건드리지 않는다."""
    try:
        return spreadsheet.worksheet(MANUAL_EVENT_TAB)
    except gspread.WorksheetNotFound:
        pass


    worksheet = spreadsheet.add_worksheet(title=MANUAL_EVENT_TAB, rows=200, cols=len(MANUAL_EVENT_HEADERS) + 1)
    worksheet.update([MANUAL_EVENT_HEADERS], "A1", value_input_option="USER_ENTERED")
    worksheet.freeze(rows=1)
    worksheet.format(
        "1:1",
        {
            "backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.85},
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
        },
    )
    category_column = MANUAL_EVENT_HEADERS.index("구분")
    spreadsheet.batch_update({
        "requests": [{
            "setDataValidation": {
                "range": {
                    "sheetId": worksheet.id,
                    "startRowIndex": 1,
                    "endRowIndex": worksheet.row_count,
                    "startColumnIndex": category_column,
                    "endColumnIndex": category_column + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": "IPO기관"},
                            {"userEnteredValue": "기존주주"},
                        ],
                    },
                    "strict": True,
                    "showCustomUi": True,
                },
            }
        }]
    })
    print(f"[SHEET] {MANUAL_EVENT_TAB} 탭 생성", file=sys.stderr)
    return worksheet




def pull_manual_events(spreadsheet: gspread.Spreadsheet) -> None:
    worksheet = ensure_manual_event_tab(spreadsheet)
    values = worksheet.get_all_values()
    entries: list[dict[str, str]] = []
    if len(values) >= 2:
        headers = [MANUAL_EVENT_KEYS.get(value.strip(), value.strip()) for value in values[0]]
        for row in values[1:]:
            padded = row + [""] * max(0, len(headers) - len(row))
            record = {headers[index]: padded[index].strip() for index in range(len(headers))}
            if any(record.get(key, "") for key in MANUAL_EVENT_KEYS.values()):
                entries.append({key: record.get(key, "") for key in MANUAL_EVENT_KEYS.values()})
    MANUAL_EVENTS_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SHEET] 수기입력 내려받기: {len(entries)}건", file=sys.stderr)




def pull_ipo_targets(spreadsheet: gspread.Spreadsheet) -> None:
    """IPO종목 탭(구분/회사명/상장일/종목코드/수동공모가)을 내려받는다.

    KRX 연간 스캔을 대체하는 유일한 대상 원천 — 운영자가 행을 추가하면
    다음 배치에서 그 종목이 편입된다. 탭이 없으면 기존 파일을 유지한다.
    """
    import re


    try:
        worksheet = spreadsheet.worksheet(IPO_TARGET_TAB)
    except gspread.WorksheetNotFound:
        print("[SHEET] IPO종목 탭이 없어 기존 대상 목록을 유지합니다.", file=sys.stderr)
        return


    values = worksheet.get_all_values()
    if not values:
        return
    headers = [cell.strip() for cell in values[0]]


    def column_index(labels: tuple[str, ...], fallback: int) -> int:
        for label in labels:
            if label in headers:
                return headers.index(label)
        return fallback


    market_index = column_index(("구분", "시장"), 0)
    name_index = column_index(("회사명", "종목명"), 1)
    listing_index = column_index(("상장일",), 2)
    code_index = column_index(("종목코드",), 3)
    manual_price_index = column_index(("수동공모가",), 4)


    entries: list[dict[str, str]] = []
    skipped = 0
    for row in values[1:]:
        padded = [cell.strip() for cell in row] + [""] * max(0, len(headers) - len(row) + 1)
        market = padded[market_index] if market_index < len(padded) else ""
        name = padded[name_index] if name_index < len(padded) else ""
        listing = padded[listing_index] if listing_index < len(padded) else ""
        code = padded[code_index] if code_index < len(padded) else ""
        manual_ipo_price = padded[manual_price_index] if manual_price_index < len(padded) else ""
        # 구글시트가 숫자 취급하며 잘라먹은 앞자리 0 복원 (예: 31210 → 031210)
        if code.isdigit() and len(code) < 6:
            code = code.zfill(6)
        if not (name or code):
            continue
        normalized = listing.replace(".", "-").replace("/", "-")
        match = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", normalized)
        # 종목코드가 없어도 통과시킨다 — 상장 후 KRX 스냅샷의 find_stock_by_name이 이름으로 코드를 자동 발견한다.
        # 이름·상장일만 필수(형식 맞아야 함).
        if not name or not match:
            skipped += 1
            continue
        entries.append({
            "market": market,
            "name": name,
            "listing_date": f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}",
            "code": code,
            # 빈칸은 기존값/DART 자동 파싱을 유지한다. 0으로 해석하지 않는다.
            "manual_ipo_price": manual_ipo_price.replace(",", ""),
        })
    IPO_TARGETS_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    note = f" (형식 불완전 {skipped}건 제외)" if skipped else ""
    print(f"[SHEET] IPO종목 목록 내려받기: {len(entries)}건{note}", file=sys.stderr)




def _pad_code(code: str) -> str:
    code = (code or "").strip()
    return code.zfill(6) if code.isdigit() and len(code) < 6 else code




def _worklist_entries(values: list[list[str]]) -> list[tuple[int, str, list[str]]]:
    """작업목록 raw 값 → (섹션번호, 종목코드, [입력칸 3개]) 목록."""
    section = 0
    out: list[tuple[int, str, list[str]]] = []
    for row in values:
        first = (row[0] if row else "").strip()
        if first.startswith("[1]"):
            section = 1
            continue
        if first.startswith("[2]"):
            section = 2
            continue
        if first.startswith("[3]"):
            section = 3
            continue
        if first.startswith("[4]"):
            section = 4
            continue
        if not first or first == "종목코드" or not section:
            continue
        padded = [cell.strip() for cell in row] + [""] * 6
        out.append((section, _pad_code(first), padded[3:6]))
    return out




def pull_worklist(spreadsheet: gspread.Spreadsheet) -> None:
    """작업목록에서 '다 채운 행'만 수거해 표준 통로로 옮긴다.

    - 섹션1(공모가): 숫자면 IPO종목 탭 수동공모가에 기록
    - 섹션2/3(물량): 기간·해제일·물량이 모두 채워진 행만 수기입력 탭에 추가
    - 수거 전 탭 전체를 백업 파일에 저장 (실수로 지워져도 복구 가능)
    """
    import re
    from datetime import datetime


    try:
        worksheet = spreadsheet.worksheet(WORKLIST_TAB)
    except gspread.WorksheetNotFound:
        return
    values = worksheet.get_all_values()
    WORKLIST_BACKUP_PATH.write_text(
        json.dumps({"saved_at": datetime.today().strftime("%Y-%m-%d %H:%M:%S"), "values": values}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


    # 해제일은 입력받지 않는다 — 상장일 + 기간으로 자동 계산(주말·휴장일 보정 포함)
    from scripts.utils.dates import calc_release_date


    listing_by_code: dict[str, str] = {}
    if IPO_TARGETS_PATH.exists():
        for t in json.loads(IPO_TARGETS_PATH.read_text(encoding="utf-8")):
            listing_by_code[t.get("code", "")] = t.get("listing_date", "")


    prices: dict[str, str] = {}
    manual_rows: list[list[str]] = []
    for section, code, inputs in _worklist_entries(values):
        if section == 4:
            continue  # 확인 필요 IPO종목은 읽기 전용 — 배치가 자동으로 재확인·재작성한다
        if section == 1:
            price = inputs[0].replace(",", "")
            if price.isdigit() and int(price) > 0:
                prices[code] = price
        else:
            period, qty = inputs[0], inputs[1].replace(",", "")
            listing = listing_by_code.get(code, "")
            if period and qty.isdigit() and listing:
                try:
                    _, _, tradable = calc_release_date(listing, period)
                except Exception:
                    continue  # 기간 표기 이상 — 입력값은 목록 재생성 때 보존됨
                gubun = "기존주주" if section == 2 else "IPO기관"
                manual_rows.append([code, gubun, period, tradable, qty])


    if prices:
        ipo = spreadsheet.worksheet(IPO_TARGET_TAB)
        vals = ipo.get_all_values()
        headers = [h.strip() for h in vals[0]]
        code_index = headers.index("종목코드")
        price_index = headers.index("수동공모가")
        updates = []
        for row_no, row in enumerate(vals[1:], start=2):
            code = _pad_code(row[code_index] if len(row) > code_index else "")
            existing_price = (row[price_index] if len(row) > price_index else "").strip().replace(",", "")
            if code in prices and existing_price != prices[code]:
                updates.append({"range": rowcol_to_a1(row_no, price_index + 1), "values": [[prices[code]]]})
        if updates:
            ipo.batch_update(updates, value_input_option="USER_ENTERED")
        print(f"[SHEET] 작업목록 → 수동공모가 이관: {len(updates)}건", file=sys.stderr)


    if manual_rows:
        manual_ws = ensure_manual_event_tab(spreadsheet)
        existing = {
            (_pad_code(r[0]), r[2].strip(), r[3].strip())
            for r in manual_ws.get_all_values()[1:]
            if len(r) >= 4 and r[0].strip()
        }
        to_add = [r for r in manual_rows if (r[0], r[2], r[3]) not in existing]
        if to_add:
            manual_ws.append_rows(to_add, value_input_option="USER_ENTERED")
        print(f"[SHEET] 작업목록 → 수기입력 이관: {len(to_add)}건 (중복 제외 {len(manual_rows) - len(to_add)}건)", file=sys.stderr)




def regenerate_worklist(spreadsheet: gspread.Spreadsheet) -> None:
    """배치 결과 기준으로 남은 갭만 작업목록에 다시 나열한다.

    - [1] 공모가 미확인 / [2] 구주 물량 없음 / [3] IPO확약 없음(확약이 아직 살아있는 종목만)
    - 채웠지만 아직 반영되지 않은 값(형식 미달 등)은 지우지 않고 그대로 살린다
    """
    from datetime import datetime, timedelta


    carry: dict[tuple[int, str], list[str]] = {}
    try:
        old = spreadsheet.worksheet(WORKLIST_TAB)
        for section, code, inputs in _worklist_entries(old.get_all_values()):
            if any(inputs):
                carry[(section, code)] = inputs
        spreadsheet.del_worksheet(old)
    except gspread.WorksheetNotFound:
        pass


    rows_csv = read_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv")
    targets = json.loads(IPO_TARGETS_PATH.read_text(encoding="utf-8")) if IPO_TARGETS_PATH.exists() else []
    # 종목코드 있는 대상만 작업목록에 나열한다. 코드 없는(상장 전) 종목은 빈 키("")로 충돌해
    # 하나만 살아남던 버그가 있었고(레메디/에이치엘지노믹스), 코드 없으면 락업 이벤트 매칭도
    # 불가하다. 이런 종목은 상장 후 KRX 코드가 잡히면 자동 편입되므로 여기서 제외한다.
    tmap = {t["code"]: t for t in targets if (t.get("code") or "").strip()}


    def to_int(value: str) -> int:
        try:
            return int(str(value).replace(",", "") or 0)
        except Exception:
            return 0


    admin_codes = {r.get("code") for r in rows_csv}
    ipo_codes = {r.get("code") for r in rows_csv if r.get("category") == "IPO기관"}
    float_codes = {r.get("code") for r in rows_csv if r.get("category") == "구주·보호예수"}
    priced = {r.get("code") for r in rows_csv if to_int(r.get("ipo_price", ""))}
    priced.update({c for c, t in tmap.items() if to_int(t.get("manual_ipo_price", ""))})


    by_recent = lambda c: tmap[c].get("listing_date", "")
    no_price = sorted([c for c in tmap if c in admin_codes and c not in priced], key=by_recent, reverse=True)
    no_float = sorted([c for c in tmap if c not in float_codes], key=by_recent, reverse=True)
    # IPO확약은 최장 6개월 — 이미 전부 만료된 과거 상장주는 지난 내역이라 입력받지 않는다
    live_cutoff = (datetime.today() - timedelta(days=190)).strftime("%Y-%m-%d")
    no_ipo = sorted(
        [c for c in tmap if c not in ipo_codes and tmap[c].get("listing_date", "") >= live_cutoff],
        key=by_recent, reverse=True,
    )


    out: list[list[str]] = []


    def add_section(no: int, title: str, codes: list[str]) -> None:
        out.append([title, "", "", "", "", ""])
        # 해제일 입력칸 없음 — 상장일+기간으로 자동 계산되므로 기간·물량만 받는다
        header = ["종목코드", "종목명", "상장일", "공모가(원)"] if no == 1 else ["종목코드", "종목명", "상장일", "락업기간", "물량(주)"]
        out.append(header + [""] * (6 - len(header)))
        for code in codes:
            saved = carry.get((no, code), ["", "", ""])
            base = [code, tmap[code].get("name", ""), tmap[code].get("listing_date", "")]
            out.append(base + ([saved[0], "", ""] if no == 1 else [saved[0], saved[1], ""]))
        out.append(["", "", "", "", "", ""])


    add_section(1, "[1] 공모가 입력 — 공모가(원) 칸만 채우면 됩니다 (표시용)", no_price)
    add_section(2, "[2] 기존주주(구주) 물량 입력 — 캘린더 정확도 직결. 한 종목 여러 건이면 행 복사", no_float)
    add_section(3, "[3] IPO기관 확약 입력 — 확약이 아직 살아있는 최근 상장주만", no_ipo)

    # [4] IPO일정에 이름만 추가했는데 자동편입 실패/대기 중인 회사 — 읽기 전용, 배치가 매번 재확인·재작성
    seed_pending: list[dict[str, str]] = []
    schedule_path = ROOT_DIR / "data" / "ipo_schedule.json"
    if schedule_path.exists():
        try:
            seed_pending = json.loads(schedule_path.read_text(encoding="utf-8")).get("seed_pending", [])
        except Exception:
            seed_pending = []
    seed_status_label = {"not_found": "DART 미등록", "pending": "공시 대기"}
    out.append(["[4] 확인 필요 IPO종목 — 자동편입 실패/대기 중 (읽기 전용, 직접 입력 불필요)", "", "", "", "", ""])
    out.append(["종목명", "상태", "DART 검색 링크", "", "", ""])
    for p in seed_pending:
        out.append([p.get("name", ""), seed_status_label.get(p.get("status", ""), p.get("status", "")), p.get("link", ""), "", "", ""])
    out.append(["", "", "", "", "", ""])

    worksheet = spreadsheet.add_worksheet(title=WORKLIST_TAB, rows=len(out) + 30, cols=8)
    worksheet.update(out, "A1", value_input_option="USER_ENTERED")
    for line_no, row in enumerate(out, start=1):
        if row[0].startswith("[") or row[0] in ("종목코드", "종목명"):
            worksheet.format(f"{line_no}:{line_no}", {"textFormat": {"bold": True}})
    print(
        f"[SHEET] 작업목록 재생성: 공모가 {len(no_price)} / 구주 {len(no_float)} / "
        f"IPO확약 {len(no_ipo)} / 확인필요 {len(seed_pending)}종목",
        file=sys.stderr,
    )




def pull_holidays(spreadsheet: gspread.Spreadsheet) -> None:
    """휴장일 탭의 날짜를 전부 수집해 data/holidays.json으로 저장한다.

    탭 형식은 자유(일자/요일/비고 등) — 셀에서 YYYY-MM-DD 꼴 날짜만 골라 쓴다.
    탭이 없으면 기존 파일을 유지한다 (지워버리지 않음).
    """
    import re


    try:
        worksheet = spreadsheet.worksheet(HOLIDAY_TAB)
    except gspread.WorksheetNotFound:
        print("[SHEET] 휴장일 탭이 없어 기존 휴장일 파일을 유지합니다.", file=sys.stderr)
        return


    # {날짜: 휴일이름} 형태 — 이름은 캘린더 뷰 표시에 쓴다
    holidays: dict[str, str] = {}
    for row in worksheet.get_all_values():
        date_value = ""
        labels: list[str] = []
        for cell in row:
            cell = cell.strip()
            match = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", cell)
            if match and not date_value:
                date_value = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
            elif cell and not cell.endswith("요일") and cell not in ("일자", "비고"):
                labels.append(cell)
        if date_value:
            holidays[date_value] = labels[-1] if labels else "휴장일"
    HOLIDAYS_PATH.write_text(json.dumps(holidays, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SHEET] 휴장일 내려받기: {len(holidays)}일", file=sys.stderr)




def reset_worksheets(spreadsheet: gspread.Spreadsheet) -> None:
    worksheets = spreadsheet.worksheets()
    first_title = STOCK_MANAGEMENT_TAB
    primary = worksheets[0]
    primary.clear()
    primary.update_title(first_title)
    for worksheet in worksheets[1:]:
        spreadsheet.del_worksheet(worksheet)




def get_or_create_worksheet(
    spreadsheet: gspread.Spreadsheet,
    title: str,
    row_count: int,
    column_count: int,
) -> gspread.Worksheet:
    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(
            title=title,
            rows=max(row_count, 100),
            cols=max(column_count, 20),
        )
    worksheet.resize(rows=max(row_count, 100), cols=max(column_count, 20))
    return worksheet




def push_tab(
    spreadsheet: gspread.Spreadsheet,
    title: str,
    filename: str,
    columns: list[str],
) -> None:
    rows = read_csv_dicts(ROOT_DIR / "data" / filename)
    if title == "로그":
        for entry in read_schedule_data().get("history") or []:
            rows.append({
                "time": entry.get("date") or "", "event_id": "",
                "code": entry.get("code") or "", "name": entry.get("name") or "",
                "field": entry.get("field") or entry.get("type") or "",
                "old_value": entry.get("old") or "", "new_value": entry.get("new") or "",
                "reason": entry.get("type") or "IPO일정 변경",
            })
        unique: dict[tuple[str, ...], dict] = {}
        for row in rows:
            key = tuple(str(row.get(column) or "") for column in columns)
            unique[key] = row
        rows = sorted(unique.values(), key=lambda row: str(row.get("time") or ""), reverse=True)
    push_rows(spreadsheet, title, rows, columns)



def push_admin_tabs(spreadsheet: gspread.Spreadsheet) -> None:
    rows = read_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv")
    for title, category, columns in READ_ONLY_ADMIN_TAB_CONFIG:
        filtered = [row for row in rows if row.get("category") == category]
        push_rows(spreadsheet, title, filtered, columns)
    for title in LEGACY_ADMIN_TABS:
        try:
            worksheet = spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            continue
        spreadsheet.del_worksheet(worksheet)



def push_rows(
    spreadsheet: gspread.Spreadsheet,
    title: str,
    rows: list[dict],
    columns: list[str],
) -> None:
    values = [[
        "처리상태" if title == "검토필요" and column == "status" else header_label(column)
        for column in columns
    ]]
    values.extend([[format_sheet_value(column, row.get(column, "")) for column in columns] for row in rows])


    worksheet = get_or_create_worksheet(spreadsheet, title, len(values) + 10, len(columns))
    worksheet.clear()
    worksheet.update(values, "A1", value_input_option="USER_ENTERED")
    worksheet.freeze(rows=1)
    worksheet.set_basic_filter(f"A1:{rowcol_to_a1(len(values), len(columns))}")
    worksheet.format(
        "1:1",
        {
            "backgroundColor": {"red": 0.91, "green": 0.94, "blue": 1.0},
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
        },
    )
    if title == "검토필요" and "status" in columns:
        status_column = columns.index("status")
        spreadsheet.batch_update({
            "requests": [{
                "setDataValidation": {
                    "range": {
                        "sheetId": worksheet.id,
                        "startRowIndex": 1,
                        "endRowIndex": worksheet.row_count,
                        "startColumnIndex": status_column,
                        "endColumnIndex": status_column + 1,
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": "미해결"},
                                {"userEnteredValue": "해결"},
                            ],
                        },
                        "strict": True,
                        "showCustomUi": True,
                    },
                }
            }]
        })
    print(f"[SHEET] {title}: {len(rows)}개 행 업로드", file=sys.stderr)


def _dropdown_request(worksheet: gspread.Worksheet, headers: list[str], column: str, options: list[str]) -> dict:
    column_index = headers.index(column)
    return {
        "setDataValidation": {
            "range": {
                "sheetId": worksheet.id,
                "startRowIndex": 1,
                "endRowIndex": worksheet.row_count,
                "startColumnIndex": column_index,
                "endColumnIndex": column_index + 1,
            },
            "rule": {
                "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": option} for option in options]},
                "strict": True,
                "showCustomUi": True,
            },
        }
    }


def _repeat_cell_format_request(
    worksheet: gspread.Worksheet,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
    cell_format: dict,
) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": worksheet.id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": cell_format},
            "fields": "userEnteredFormat(backgroundColor,textFormat)",
        }
    }


def _review_pending_ranges(rows: list[dict]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for index, row in enumerate(rows):
        if str(row.get("management_status") or "") == "검토대기":
            if start is None:
                start = index
        elif start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(rows)))
    return ranges


def _checkbox_request(worksheet: gspread.Worksheet, headers: list[str], column: str) -> dict:
    index = headers.index(column)
    return {
        "setDataValidation": {
            "range": {
                "sheetId": worksheet.id, "startRowIndex": 1,
                "endRowIndex": worksheet.row_count,
                "startColumnIndex": index, "endColumnIndex": index + 1,
            },
            "rule": {"condition": {"type": "BOOLEAN"}, "strict": True, "showCustomUi": True},
        }
    }


def _hide_columns_request(worksheet: gspread.Worksheet, headers: list[str], columns: list[str]) -> list[dict]:
    requests: list[dict] = []
    for column in columns:
        if column not in headers:
            continue
        index = headers.index(column)
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": worksheet.id, "dimension": "COLUMNS",
                    "startIndex": index, "endIndex": index + 1,
                },
                "properties": {"hiddenByUser": True}, "fields": "hiddenByUser",
            }
        })
    return requests


def _push_simple_table(
    spreadsheet: gspread.Spreadsheet,
    title: str,
    headers: list[str],
    rows: list[list[object]],
    checkbox_columns: list[str],
    hidden_columns: list[str] | None = None,
) -> None:
    values = [headers] + rows
    worksheet = get_or_create_worksheet(spreadsheet, title, len(values) + 30, len(headers))
    worksheet.clear()
    worksheet.update(values, "A1", value_input_option="USER_ENTERED")
    worksheet.freeze(rows=1, cols=min(2, len(headers)))
    worksheet.set_basic_filter(f"A1:{rowcol_to_a1(max(len(values), 1), len(headers))}")
    worksheet.format("1:1", {
        "backgroundColor": {"red": 0.82, "green": 0.89, "blue": 1.0},
        "textFormat": {"bold": True}, "horizontalAlignment": "CENTER",
    })
    requests = [_checkbox_request(worksheet, headers, column) for column in checkbox_columns]
    requests.extend(_hide_columns_request(worksheet, headers, hidden_columns or []))
    if requests:
        spreadsheet.batch_update({"requests": requests})
    print(f"[SHEET] {title}: {len(rows)}개 행 업로드", file=sys.stderr)


def _event_validation(row: dict) -> tuple[str, str]:
    if row.get("review_needed") == "Y":
        return "확인필요", str(row.get("parse_note") or row.get("api_reason") or row.get("memo") or "자동 검증 필요")
    if row.get("manual_lock") == "Y":
        return "수기고정", "운영자가 이 행을 고정"
    if row.get("manual_mode") == "임시":
        return "수기임시", "공식값 수집 시 자동 교체"
    return "정상", ""


def _management_stats(admin_rows: list[dict]) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for row in admin_rows:
        keys = [str(row.get("code") or ""), f"name:{norm_name(row.get('name'))}"]
        for key in keys:
            if not key or key == "name:":
                continue
            current = stats.setdefault(key, {})
            current["initial_shares"] = current.get("initial_shares") or row.get("shares") or ""
            current["current_shares"] = row.get("current_shares") or current.get("current_shares") or ""
            current["shares_date"] = row.get("shares_date") or current.get("shares_date") or ""
            current["close_price"] = row.get("close_price") or current.get("close_price") or ""
    return stats


def push_stock_management_tab(spreadsheet: gspread.Spreadsheet) -> None:
    schedule = read_schedule_data()
    rows = merge_stock_management(
        read_json_list(STOCK_MANAGEMENT_PATH), read_json_list(IPO_TARGETS_PATH), schedule,
    )
    stats = _management_stats(read_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv"))
    by_item = {item_key(item): item for item in all_schedule_items(schedule)}
    state = load_simple_sheet_state()
    state_rows: dict[str, dict] = {}
    values: list[list[object]] = []
    for row in rows:
        key = str(row.get("corp_code") or f"name:{norm_name(row.get('name'))}")
        item = by_item.get(key) or next(
            (value for value in all_schedule_items(schedule) if norm_name(value.get("name")) == norm_name(row.get("name"))), {}
        )
        metric = stats.get(str(row.get("stock_code") or "")) or stats.get(f"name:{norm_name(row.get('name'))}") or {}
        official_price = item.get("final_price") or row.get("manual_ipo_price") or ""
        row.update({field: metric.get(field) or row.get(field) or "" for field in ("initial_shares", "current_shares", "shares_date", "close_price")})
        row["manual_ipo_price"] = official_price
        if item.get("fixed_excluded") or row.get("management_status") == "제외고정":
            row["validation_status"], row["validation_reason"] = "삭제", "관리 체크 해제 + 홈페이지 비공개"
        elif item.get("review_pending"):
            row["validation_status"], row["validation_reason"] = "확인필요", str(item.get("review_reason") or "DART/API 확인 필요")
        elif item.get("provisional_fields"):
            row["validation_status"], row["validation_reason"] = "수기임시", "공식값 수집 시 자동 교체"
        else:
            row["validation_status"], row["validation_reason"] = "정상", ""
        values.append([
            row.get("management_status") != "제외고정", row.get("visibility") != "비공개",
            row.get("name", ""), row.get("corp_code", ""), row.get("stock_code", ""), row.get("market", ""),
            row.get("listing_date", ""), row.get("listing_date_locked") == "Y",
            number(row.get("manual_ipo_price")) or "", row.get("manual_ipo_price_locked") == "Y",
            number(row.get("initial_shares")) or "", number(row.get("current_shares")) or "",
            row.get("shares_date", ""), number(row.get("close_price")) or "", row.get("content_url", ""),
            row.get("validation_status", ""), row.get("validation_reason", ""), row.get("memo", ""),
        ])
        state_rows[key] = {
            "listing_date": str(row.get("listing_date") or ""),
            "manual_ipo_price": str(number(row.get("manual_ipo_price")) or ""),
        }
    STOCK_MANAGEMENT_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    state["management"] = state_rows
    SIMPLE_SHEET_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    _push_simple_table(
        spreadsheet, STOCK_MANAGEMENT_TAB, STOCK_MANAGEMENT_HEADERS, values,
        ["관리", "홈페이지노출", "상장일고정", "공모가고정"],
    )


def _schedule_validation(item: dict) -> tuple[str, str]:
    if item.get("review_pending"):
        return "확인필요", str(item.get("review_reason") or "DART 파싱 결과 확인 필요")
    if set(item.get("manual_fields") or []).intersection({
        "band_low", "band_high", "offer_shares", "forecast_start", "forecast_end",
        "sub_start", "sub_end", "demand_ratio", "sub_ratio", "underwriter",
    }):
        return "수기고정", "이 탭의 일정값 고정"
    if item.get("provisional_fields"):
        return "수기임시", "공식값 수집 시 자동 교체"
    return "정상", ""


def push_simple_schedule_tab(spreadsheet: gspread.Spreadsheet) -> None:
    schedule = read_schedule_data()
    state = load_simple_sheet_state()
    state_rows: dict[str, dict] = {}
    rows: list[list[object]] = []
    domain = {
        "band_low", "band_high", "offer_shares", "forecast_start", "forecast_end",
        "sub_start", "sub_end", "demand_ratio", "sub_ratio", "underwriter",
    }
    for item in sorted(all_schedule_items(schedule), key=lambda value: (value.get("listing_date") or "9999", value.get("name") or "")):
        if item.get("fixed_excluded"):
            continue
        snapshot = _schedule_snapshot(item)
        status, reason = _schedule_validation(item)
        key = item_key(item)
        state_rows[key] = snapshot
        rows.append([
            bool(set(item.get("manual_fields") or []).intersection(domain)), not item.get("schedule_hidden", False),
            item.get("name", ""), snapshot["band"], number(snapshot["offer_shares"]) or "",
            snapshot["forecast"], snapshot["subscription"], item.get("demand_ratio") or "",
            item.get("sub_ratio") or "", item.get("underwriter") or "", status, reason,
            item.get("corp_code", ""), f"schedule:{key}", item.get("content_url", ""),
        ])
    state["schedule"] = state_rows
    SIMPLE_SHEET_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    _push_simple_table(
        spreadsheet, IPO_SCHEDULE_TAB, IPO_SCHEDULE_VIEW_HEADERS, rows,
        ["고정", "노출"], ["DART기업코드", "이벤트ID"],
    )


def _period_order(period: object) -> int:
    try:
        return COMMIT_TIER_ORDER.index(str(period or ""))
    except ValueError:
        return len(COMMIT_TIER_ORDER)


def push_simple_event_tabs(spreadsheet: gspread.Spreadsheet) -> None:
    admin = read_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv")
    schedule = read_schedule_data()
    items = all_schedule_items(schedule)
    by_code = {str(item.get("stock_code") or ""): item for item in items if item.get("stock_code")}
    by_name = {norm_name(item.get("name")): item for item in items if norm_name(item.get("name"))}
    state = load_simple_sheet_state()

    ipo_admin = [row for row in admin if row.get("category") == "IPO기관"]
    ipo_by_key = {(str(row.get("code") or ""), str(row.get("period") or "")): row for row in ipo_admin}
    ipo_rows: list[list[object]] = []
    ipo_state: dict[str, dict] = {}
    keys: set[tuple[str, str, str]] = set()
    for item in items:
        code, name = str(item.get("stock_code") or ""), str(item.get("name") or "")
        for tier in list(item.get("commit_apply") or []) + list(item.get("commit_alloc") or []):
            if isinstance(tier, dict) and tier.get("period"):
                keys.add((code, name, str(tier["period"])))
    for row in ipo_admin:
        keys.add((str(row.get("code") or ""), str(row.get("name") or ""), str(row.get("period") or "")))
    for code, name, period in sorted(keys, key=lambda value: (value[1], _period_order(value[2]))):
        item = by_code.get(code) or by_name.get(norm_name(name)) or {}
        event = ipo_by_key.get((code, period), {})
        apply_tier = next((tier for tier in item.get("commit_apply") or [] if str(tier.get("period") or "") == period), {})
        alloc_tier = next((tier for tier in item.get("commit_alloc") or [] if str(tier.get("period") or "") == period), {})
        apply_qty = number(apply_tier.get("qty"))
        alloc_qty = number(event.get("final_qty") or event.get("planned_qty") or alloc_tier.get("qty"))
        total_alloc = sum(number(tier.get("qty")) for tier in item.get("commit_alloc") or [])
        event_id = str(event.get("event_id") or f"ipo:{item_key(item) if item else norm_name(name)}:{period}")
        status, reason = _event_validation(event) if event else ("정상" if apply_qty or alloc_qty else "확인필요", "" if apply_qty or alloc_qty else "기관 수량 미수집")
        visible = event.get("sheet_visible") != "N" and apply_tier.get("visible", True) is not False
        row_values = [
            event.get("manual_lock") == "Y" or str(apply_tier.get("source") or "") == "manual_fixed", visible,
            name or event.get("name", ""), code or event.get("code", ""), period, apply_qty or "", alloc_qty or "",
            round(alloc_qty / apply_qty * 100, 2) if apply_qty and alloc_qty else "",
            round(alloc_qty / total_alloc * 100, 2) if total_alloc and alloc_qty else "",
            event.get("final_date") or event.get("planned_date") or "", status, reason,
            event_id, item.get("corp_code", ""),
        ]
        ipo_rows.append(row_values)
        ipo_state[event_id] = dict(zip(IPO_INSTITUTION_HEADERS, [str(value) for value in row_values]))

    holder_rows: list[list[object]] = []
    holder_state: dict[str, dict] = {}
    for event in sorted((row for row in admin if row.get("category") == "구주·보호예수"), key=lambda row: (row.get("name") or "", row.get("final_date") or row.get("planned_date") or "")):
        if not event.get("event_id"):
            continue
        status, reason = _event_validation(event)
        qty = number(event.get("final_qty") or event.get("planned_qty"))
        current_shares = number(event.get("current_shares") or event.get("shares"))
        values = [
            event.get("manual_lock") == "Y", event.get("sheet_visible") != "N",
            event.get("name", ""), event.get("code", ""), event.get("period", ""),
            event.get("final_date") or event.get("planned_date") or "", qty or "",
            round(qty / current_shares * 100, 2) if qty and current_shares else "",
            status, reason, event.get("event_id", ""),
        ]
        holder_rows.append(values)
        holder_state[str(event["event_id"])] = dict(zip(HOLDER_HEADERS, [str(value) for value in values]))

    state["ipo_institution"], state["holders"] = ipo_state, holder_state
    SIMPLE_SHEET_STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    _push_simple_table(spreadsheet, "IPO기관", IPO_INSTITUTION_HEADERS, ipo_rows, ["고정", "노출"], ["이벤트ID", "DART기업코드"])
    _push_simple_table(spreadsheet, "기존주주", HOLDER_HEADERS, holder_rows, ["고정", "노출"], ["이벤트ID"])


def push_correction_tab(spreadsheet: gspread.Spreadsheet) -> None:
    rows = build_correction_tasks(
        read_json_list(CORRECTION_PATH),
        read_json_list(IPO_TARGETS_PATH),
        read_schedule_data(),
        read_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv"),
        read_json_list(MANUAL_EVENTS_PATH),
    )
    CORRECTION_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    values = [CORRECTION_HEADERS] + [[row.get(key, "") for key in CORRECTION_COLUMNS] for row in rows]
    worksheet = get_or_create_worksheet(spreadsheet, CORRECTION_TAB, len(values) + 30, len(CORRECTION_HEADERS))
    worksheet.clear()
    worksheet.update(values, "A1", value_input_option="RAW")
    worksheet.freeze(rows=1)
    worksheet.set_basic_filter(f"A1:{rowcol_to_a1(len(values), len(CORRECTION_HEADERS))}")
    worksheet.format("1:1", {
        "backgroundColor": {"red": 0.82, "green": 0.89, "blue": 1.0},
        "textFormat": {"bold": True}, "horizontalAlignment": "CENTER",
    })
    spreadsheet.batch_update({"requests": [
        _dropdown_request(worksheet, CORRECTION_HEADERS, "대상", ["IPO일정", "락업"]),
        _dropdown_request(worksheet, CORRECTION_HEADERS, "구분", ["IPO기관", "기존주주"]),
        _dropdown_request(worksheet, CORRECTION_HEADERS, "보정방식", ["임시", "고정", "자동복귀"]),
        _dropdown_request(worksheet, CORRECTION_HEADERS, "처리상태", ["대기", "적용", "검토필요", "자동해결", "취소"]),
    ]})
    print(f"[SHEET] 보정작업: {len(rows)}건 (기존 수기값·미해결 작업 보존)", file=sys.stderr)




def ensure_ipo_target_manual_price_column(spreadsheet: gspread.Spreadsheet) -> None:
    """기존 IPO종목 탭을 초기화하지 않고 선택 입력 컬럼만 보장한다."""
    try:
        worksheet = spreadsheet.worksheet(IPO_TARGET_TAB)
    except gspread.WorksheetNotFound:
        return
    headers = worksheet.row_values(1)
    if "수동공모가" in headers:
        return
    column = max(len(headers) + 1, 5)
    worksheet.update([["수동공모가"]], rowcol_to_a1(1, column), value_input_option="USER_ENTERED")
    print("[SHEET] IPO종목 탭에 수동공모가 컬럼 추가", file=sys.stderr)




def push_universe_review(spreadsheet: gspread.Spreadsheet) -> None:
    candidates = sorted((ROOT_DIR / "data").glob("review_candidates_*.json"))
    rows = json.loads(candidates[-1].read_text(encoding="utf-8")) if candidates else []
    decisions = []
    if REVIEW_DECISIONS_PATH.exists():
        decisions = json.loads(REVIEW_DECISIONS_PATH.read_text(encoding="utf-8"))
    decision_by_code = {row.get("code", ""): row for row in decisions if row.get("code")}
    # 이미 운영_락업일정에 편입되어 관리 중인 종목은 검토가 끝난 것이므로 후보 탭에서 제외
    admin_codes = {
        row.get("code", "")
        for row in read_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv")
        if row.get("code")
    }


    # 과거 검토 이력(비IPO 판정 등)은 이번 스캔의 후보 파일 유무와 무관하게 항상 탭에 유지한다
    merged_by_code: dict[str, dict] = {}
    for row in decisions:
        code = str(row.get("code") or "").strip()
        if code:
            merged_by_code[code] = {column: row.get(column, "") for column in UNIVERSE_REVIEW_COLUMNS}
    for row in rows:
        code = str(row.get("code") or "").strip()
        if not code:
            continue
        saved = decision_by_code.get(code, {})
        merged_by_code[code] = {**row, **{
            "review_decision": saved.get("review_decision", ""),
            "review_memo": saved.get("review_memo", ""),
        }}


    merged_rows = [row for code, row in merged_by_code.items() if code not in admin_codes]
    merged_rows.sort(key=lambda row: (row.get("listing_date", ""), row.get("code", "")))


    push_rows(spreadsheet, "상장후보_검토", merged_rows, UNIVERSE_REVIEW_COLUMNS)
    worksheet = spreadsheet.worksheet("상장후보_검토")
    decision_column = UNIVERSE_REVIEW_COLUMNS.index("review_decision")
    spreadsheet.batch_update({
        "requests": [{
            "setDataValidation": {
                "range": {
                    "sheetId": worksheet.id,
                    "startRowIndex": 1,
                    "endRowIndex": worksheet.row_count,
                    "startColumnIndex": decision_column,
                    "endColumnIndex": decision_column + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": "IPO"},
                            {"userEnteredValue": "비IPO"},
                        ],
                    },
                    "strict": True,
                    "showCustomUi": True,
                },
            }
        }]
    })




def _ipo_status_label(item: dict) -> str:
    """사이트 lib/ipo.ts의 상태 판정과 동일한 규칙 (시트 가독용)."""
    from datetime import date

    today = date.today().isoformat()
    if item.get("fixed_excluded"):
        return "제외고정"
    if item.get("review_pending"):
        return "검토필요"
    if item.get("withdrawn"):
        return "공모 철회"
    listing = item.get("listing_date") or ""
    if listing:
        return "상장 완료" if listing < today else "상장 예정"
    sub_start, sub_end = item.get("sub_start") or "", item.get("sub_end") or ""
    if sub_start and sub_end and sub_start <= today <= sub_end:
        return "청약 중"
    if sub_end and sub_end < today:
        return "청약 완료" if item.get("final_price") else "일정 미정"
    fc_start, fc_end = item.get("forecast_start") or "", item.get("forecast_end") or ""
    if fc_start and fc_end and fc_start <= today <= fc_end:
        return "수요예측 중"
    if fc_end and fc_end < today:
        return "청약 예정"
    if fc_start:
        return "수요예측 예정"
    return "공모 준비"


def _parse_sheet_dates(text: str) -> list[str]:
    """시트 셀의 날짜 표기(2026-07-27, 2026.7.27, ~ 구간)를 ISO 목록으로."""
    import re

    out: list[str] = []
    for m in re.finditer(r"(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", text):
        out.append(f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}")
    return out


def sync_ipo_schedule_tab(spreadsheet: gspread.Spreadsheet) -> None:
    """IPO 일정 결과를 읽기 전용 현황 탭에 적재한다.

    새 종목관리 탭이 아직 없는 최초 이관 실행에서만 구형 IPO일정 탭의 링크·수기수정·삭제를
    한 번 수거한다. 이후 입력은 종목관리/보정작업만 사용하고 이 탭은 결과 확인 전용이다.
    """
    if not IPO_SCHEDULE_PATH.exists():
        return
    try:
        data = json.loads(IPO_SCHEDULE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    items = data.get("items", [])
    past_items = data.get("past_items", [])

    def date_range(start: str, end: str) -> str:
        if not start:
            return "미정"
        return start if not end or end == start else f"{start} ~ {end}"

    def num(value: object) -> str:
        return f"{value:,}" if isinstance(value, (int, float)) and value else "미정"

    def commit_qty_map(tiers: object) -> dict[str, int]:
        """기간별 확약 수량만 뽑는다 — {"미확약": 12345, "15일": ..., ...}. 값 없으면 빈 딕셔너리."""
        out: dict[str, int] = {}
        if not isinstance(tiers, list):
            return out
        for t in tiers:
            if isinstance(t, dict) and t.get("period") in COMMIT_TIER_ORDER:
                qty = t.get("qty")
                if isinstance(qty, (int, float)):
                    out[t["period"]] = int(qty)
        return out

    def commit_cell(qty_map: dict[str, int], tier: str) -> str:
        return str(qty_map[tier]) if tier in qty_map else "미정"

    def auto_cell(item: dict, column: str) -> str:
        if column == "확정공모가":
            return num(item.get("final_price"))
        if column == "수요예측일":
            return date_range(item.get("forecast_start") or "", item.get("forecast_end") or "")
        if column == "청약일":
            return date_range(item.get("sub_start") or "", item.get("sub_end") or "")
        if column == "상장일":
            return item.get("listing_date") or "미정"
        return ""

    # 배치가 마지막으로 쓴 값 스냅샷 (사용자 수정 판정 기준)
    written: dict[str, dict[str, str]] = {}
    if IPO_SCHEDULE_WRITTEN_PATH.exists():
        try:
            written = json.loads(IPO_SCHEDULE_WRITTEN_PATH.read_text(encoding="utf-8"))
        except Exception:
            written = {}

    # 1) 기존 탭 백업 + 운영자 입력 수거
    links: dict[str, str] = {}
    sheet_cells: dict[str, dict[str, str]] = {}  # 기업명 → {열: 값}
    use_legacy_inputs = True
    try:
        spreadsheet.worksheet(STOCK_MANAGEMENT_TAB)
        use_legacy_inputs = False
    except gspread.WorksheetNotFound:
        pass
    try:
        worksheet = spreadsheet.worksheet(IPO_SCHEDULE_TAB) if use_legacy_inputs else None
        values = worksheet.get_all_values() if worksheet else []
        if values:
            IPO_SCHEDULE_BACKUP_PATH.write_text(
                json.dumps({"values": values}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            headers = [h.strip() for h in values[0]]
            if "기업명" in headers:
                name_at = headers.index("기업명")
                col_at = {
                    col: headers.index(col)
                    for col in list(IPO_EDITABLE_COLUMNS) + ["콘텐츠링크", "IPO취소", "검토"]
                    if col in headers
                }
                for row in values[1:]:
                    if len(row) <= name_at or not row[name_at].strip():
                        continue
                    name = row[name_at].strip()
                    cells = {col: (row[at].strip() if len(row) > at else "") for col, at in col_at.items()}
                    sheet_cells[name] = cells
                    if cells.get("콘텐츠링크"):
                        links[name] = cells["콘텐츠링크"]
    except gspread.WorksheetNotFound:
        pass

    # 1-1) 이름만 적힌 새 행(기존 항목과 매칭 안 됨) → 다음 배치가 DART에서 직접 찾도록 요청 파일에 적재
    if use_legacy_inputs:
        existing_names = {(i.get("name") or "").strip() for i in items + past_items}
        seed_names = [name for name in sheet_cells if name not in existing_names]
        ipo_seed_path = ROOT_DIR / "data" / "ipo_seed_names.json"
        if seed_names:
            ipo_seed_path.write_text(json.dumps(seed_names, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[SHEET] IPO일정 수동추가 요청 {len(seed_names)}건 저장 (다음 배치에 반영): {', '.join(seed_names)}", file=sys.stderr)
        elif ipo_seed_path.exists():
            ipo_seed_path.write_text("[]", encoding="utf-8")

    # 1-2) IPO취소 컬럼에서 "삭제" 선택된 종목 → items에서 제거 + 톰스톤 등록
    #      IPO종목/락업 캘린더는 독립 파이프라인이라 여기서 안 건드림. 새 신고서 나오면 자동 부활.
    deleted_corps: dict[str, dict[str, str]] = dict(data.get("deleted_corps") or {})
    kept_items: list[dict] = []
    for item in items:
        name = (item.get("name") or "").strip()
        cancel = (sheet_cells.get(name) or {}).get("IPO취소", "").strip()
        if cancel == "삭제":
            from datetime import date as _date

            data.setdefault("history", []).append({
                "date": _date.today().isoformat(),
                "name": name, "type": "삭제", "field": "IPO취소",
                "old": "게시 중", "new": "삭제",
            })
            deleted_corps[item.get("corp_code", "")] = {
                "name": name,
                "last_rcept_no": item.get("last_rcept_no") or "",
                "deleted_at": _date.today().isoformat(),
            }
            print(f"[SHEET] IPO일정 삭제: {name} (마지막 신고서 {item.get('last_rcept_no')})", file=sys.stderr)
        else:
            kept_items.append(item)
    data["items"] = kept_items
    data["deleted_corps"] = deleted_corps
    items = kept_items

    # 2) 운영자 입력을 사이트 데이터에 반영 (링크 + 수동수정 잠금)
    changed = False
    overrides = 0
    for item in items:
        name = (item.get("name") or "").strip()
        url = links.get(name, "")
        if url and url != (item.get("content_url") or ""):
            item["content_url"] = url
            changed = True

        cells = sheet_cells.get(name) or {}
        last = written.get(name) or {}

        # 검토 컬럼 "승인" → 검토대기 항목을 사이트에 노출(잠금). IPO 신호 약해도 사용자가 보증.
        if cells.get("검토", "").strip() == "승인" and not item.get("review_approved"):
            item["review_approved"] = True
            item["review_pending"] = False
            changed = True
            from datetime import date as _date

            data.setdefault("history", []).append({
                "date": _date.today().isoformat(),
                "name": name, "type": "검토승인", "field": "노출",
                "old": "검토필요(비공개)", "new": "노출",
            })

        manual_fields = list(item.get("manual_fields") or [])
        for column, fields in IPO_EDITABLE_COLUMNS.items():
            cell = cells.get(column, "")
            if not cell or cell == "미정":
                continue
            # 배치가 마지막으로 쓴 값과 같으면 사용자 수정이 아님
            if cell == last.get(column, "") or cell == auto_cell(item, column):
                continue
            if column == "확정공모가":
                digits = "".join(ch for ch in cell if ch.isdigit())
                if not digits:
                    continue
                item["final_price"] = int(digits)
            else:
                dates = _parse_sheet_dates(cell)
                if not dates:
                    continue
                if column == "상장일":
                    item["listing_date"] = dates[0]
                else:
                    start, end = dates[0], dates[-1]
                    item[fields[0]], item[fields[1]] = start, end
            # 상장일은 KRX가 진실 소스라 잠금하지 않는다 — 다음 배치 KRX 감지가 오타 자동복구
            # 확정공모가·수요예측·청약일은 KRX가 안 주는 값이라 사용자 잠금 유지
            if column != "상장일":
                for field in fields:
                    if field not in manual_fields:
                        manual_fields.append(field)
            overrides += 1
            changed = True
            from datetime import date as _date

            data.setdefault("history", []).append({
                "date": _date.today().isoformat(),
                "name": name,
                "type": "수기변경",
                "field": column,
                "old": last.get(column, "") or auto_cell(item, column),
                "new": cell,
            })
        # 취소/연기로 잠금이 풀린 경우 빈 리스트가 될 수 있어 무조건 덮어쓴다
        if manual_fields:
            item["manual_fields"] = manual_fields
        elif "manual_fields" in item:
            del item["manual_fields"]

    if changed:
        IPO_SCHEDULE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[SHEET] IPO일정: 운영자 입력 반영 (수동수정 {overrides}건, 링크 {len(links)}건)", file=sys.stderr)

    # 3) 읽기 전용 현황 탭 재작성 + 쓴 값 스냅샷 저장
    rows: list[list[str]] = []
    new_written: dict[str, dict[str, str]] = {}
    # 진행 종목을 먼저, 상장 완료 이력을 그 아래에 함께 유지한다. 상태 열의
    # '상장 완료' 필터로 과거 데이터만 따로 볼 수 있고 홈페이지 노출에는 영향이 없다.
    view_items = items + past_items
    for item in view_items:
        if item.get("fixed_excluded"):
            continue
        name = item.get("name") or ""
        band_low, band_high = item.get("band_low") or 0, item.get("band_high") or 0
        apply_map = commit_qty_map(item.get("commit_apply"))
        alloc_map = commit_qty_map(item.get("commit_alloc"))
        row = [
            name,
            _ipo_status_label(item),
            item.get("management_status") or ("수동편입" if item.get("manual_entry") else "자동"),
            item.get("market") or "미정",
            item.get("underwriter") or "미정",
            f"{band_low:,} ~ {band_high:,}" if band_low else "미정",
            auto_cell(item, "확정공모가"),
            num(item.get("offer_shares")),
            auto_cell(item, "수요예측일"),
            auto_cell(item, "청약일"),
            auto_cell(item, "상장일"),
            f"{item.get('demand_ratio'):,.2f}:1" if item.get("demand_ratio") else "미정",
            f"{item.get('sub_ratio'):,.2f}:1" if item.get("sub_ratio") else "미정",
            *[commit_cell(apply_map, tier) for tier in COMMIT_TIER_ORDER],
            *[commit_cell(alloc_map, tier) for tier in COMMIT_TIER_ORDER],
            item.get("content_url") or "",
        ]
        rows.append(row)
        new_written[name] = {col: auto_cell(item, col) for col in IPO_EDITABLE_COLUMNS}

    sheet_values = [IPO_SCHEDULE_VIEW_HEADERS] + rows
    worksheet = get_or_create_worksheet(spreadsheet, IPO_SCHEDULE_VIEW_TAB, len(sheet_values) + 10, len(IPO_SCHEDULE_VIEW_HEADERS))
    worksheet.clear()
    worksheet.update(sheet_values, "A1", value_input_option="USER_ENTERED")
    worksheet.freeze(rows=1)
    worksheet.set_basic_filter(f"A1:{rowcol_to_a1(len(sheet_values), len(IPO_SCHEDULE_VIEW_HEADERS))}")
    worksheet.format(
        "1:1",
        {
            "backgroundColor": {"red": 0.91, "green": 0.94, "blue": 1.0},
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
        },
    )
    IPO_SCHEDULE_WRITTEN_PATH.write_text(json.dumps(new_written, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[SHEET] IPO일정_현황: {len(rows)}개 종목 읽기 전용 적재 "
        f"(진행 {len(items)} / 과거 {len(past_items)})",
        file=sys.stderr,
    )

    # 정정이력 탭 — 정정공시·수기변경·KRX 자동수정·삭제·부활·IPO종목 삭제 크로스기록까지 최신순.
    # 운영자가 IPO일정·락업 둘 다 한 곳에서 감사할 수 있게 크로스 로그를 모아둔다.
    from collections import Counter as _Counter

    hist = data.get("history") or []
    if hist:
        recent = list(reversed(hist[-500:]))
        # 자동필터 사용을 위해 컬럼 순서: 일자·구분·기업명·항목·이전값·새값
        hist_values = [["일자", "구분", "기업명", "항목", "이전값", "새값"]] + [
            [h.get("date", ""), h.get("type", ""), h.get("name", ""), h.get("field", ""), str(h.get("old", "")), str(h.get("new", ""))]
            for h in recent
        ]
        hist_ws = get_or_create_worksheet(spreadsheet, "정정이력", len(hist_values) + 10, 6)
        hist_ws.clear()
        hist_ws.update(hist_values, "A1", value_input_option="RAW")
        hist_ws.freeze(rows=1)
        # 자동필터 활성 (구분/기업명별로 즉시 필터링 가능)
        hist_ws.set_basic_filter(f"A1:{rowcol_to_a1(len(hist_values), 6)}")
        hist_ws.format("1:1", {"backgroundColor": {"red": 0.91, "green": 0.94, "blue": 1.0}, "textFormat": {"bold": True}, "horizontalAlignment": "CENTER"})

        # 최근 7일 요약을 헤더 아래 별도 영역이 아니라 로그 자체로 유지하고, 콘솔에만 카운트 출력
        from datetime import date as _date, timedelta as _td

        cutoff = (_date.today() - _td(days=7)).isoformat()
        recent7 = [h for h in recent if (h.get("date") or "") >= cutoff]
        type_counts = _Counter(h.get("type", "") for h in recent7)
        summary = " · ".join(f"{k} {v}건" for k, v in type_counts.most_common())
        print(f"[SHEET] 정정이력: {len(hist_values) - 1}건 적재 (최근 7일 {len(recent7)}건 — {summary or '없음'})", file=sys.stderr)


def append_missing_ipo_targets(spreadsheet: gspread.Spreadsheet) -> None:
    """IPO일정 → IPO종목 탭 upsert.

    - 없는 기업: 새 행 추가
    - 이미 있는 기업 중 종목코드 공란: KRX가 감지한 stock_code로 자동 채움
    - 사용자가 넣은 수동공모가 등 다른 컬럼은 절대 안 건드림
    - append_rows/batch_update 전 탭 전체 백업 저장
    """
    import re

    if not IPO_SCHEDULE_PATH.exists():
        return
    try:
        data = json.loads(IPO_SCHEDULE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    candidates = [i for i in data.get("items", []) if i.get("listing_date") and not i.get("withdrawn")]
    if not candidates:
        return
    try:
        worksheet = spreadsheet.worksheet(IPO_TARGET_TAB)
    except gspread.WorksheetNotFound:
        return
    values = worksheet.get_all_values()
    if not values:
        return
    (ROOT_DIR / "data" / "ipo_targets_sheet_backup.json").write_text(
        json.dumps({"values": values}, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    def norm(s: str) -> str:
        return re.sub(r"[\s㈜()]|주식회사", "", s or "")

    headers = [c.strip() for c in values[0]]
    name_at = headers.index("회사명") if "회사명" in headers else 1
    code_at = headers.index("종목코드") if "종목코드" in headers else 3
    existing_by_name: dict[str, int] = {}  # 정규화명 → 시트 행번호(1-based, 헤더 포함)
    for idx, row in enumerate(values[1:], start=2):
        if len(row) > name_at and row[name_at].strip():
            existing_by_name[norm(row[name_at])] = idx

    new_rows: list[list[str]] = []
    code_updates: list[dict] = []  # {"range": "D5", "values": [["01501764"]]}
    for item in candidates:
        key = norm(item.get("name") or "")
        item_code = str(item.get("stock_code") or "").strip()
        item_code_padded = item_code.zfill(6) if item_code.isdigit() and len(item_code) < 6 else item_code

        row_at = existing_by_name.get(key)
        if row_at is None:
            new_rows.append([
                item.get("market") or "코스닥",
                item.get("name") or "",
                item.get("listing_date") or "",
                item_code_padded,
                "",
            ])
            continue
        # upsert: 종목코드가 공란이고 KRX에서 발견됐으면 자동 채움
        row = values[row_at - 1]
        current_code = (row[code_at] if len(row) > code_at else "").strip()
        if not current_code and item_code_padded:
            cell = rowcol_to_a1(row_at, code_at + 1)
            code_updates.append({"range": cell, "values": [[item_code_padded]]})

    if new_rows:
        worksheet.append_rows(new_rows, value_input_option="RAW")
        names = ", ".join(row[1] for row in new_rows)
        print(f"[SHEET] IPO종목 자동 추가: {len(new_rows)}건 ({names})", file=sys.stderr)
    if code_updates:
        worksheet.batch_update(code_updates, value_input_option="RAW")
        print(f"[SHEET] IPO종목 종목코드 자동 기입: {len(code_updates)}건", file=sys.stderr)


# 운영자 입력은 도메인별 네 탭과 휴장일에서만 받는다.
MANUAL_TABS_ORDER = [STOCK_MANAGEMENT_TAB, IPO_SCHEDULE_TAB, "IPO기관", "기존주주", HOLIDAY_TAB, "로그"]
MANUAL_COLOR_ONLY_TABS: list[str] = []
MANUAL_TAB_COLOR = {"red": 0.26, "green": 0.52, "blue": 0.96}
LEGACY_INPUT_TABS = ["IPO종목", "작업목록", "수기입력"]
OBSOLETE_TABS = tuple(dict.fromkeys([
    *LEGACY_INPUT_TABS,
    *LEGACY_ADMIN_TABS,
    "검토필요",
    "상장후보_검토",
    CORRECTION_TAB,
    "IPO일정_현황",
    "IPO기관_현황",
    "기존주주_현황",
    "정정이력",
    "변경로그",
]))


def cleanup_obsolete_tabs(spreadsheet: gspread.Spreadsheet) -> list[str]:
    """첫 마이그레이션이 끝난 구형 운영 탭만 명시적으로 삭제한다."""
    worksheets = {worksheet.title: worksheet for worksheet in spreadsheet.worksheets()}
    removed: list[str] = []
    for title in OBSOLETE_TABS:
        worksheet = worksheets.get(title)
        if not worksheet:
            continue
        spreadsheet.del_worksheet(worksheet)
        removed.append(title)
    if removed:
        print(f"[SHEET] 구형 탭 삭제: {', '.join(removed)}", file=sys.stderr)
    return removed


def arrange_sheet_tabs(spreadsheet: gspread.Spreadsheet) -> None:
    """수기 관리 탭을 왼쪽으로 정렬하고 파란 탭 색을 입힌다. 실패해도 동기화에는 영향 없음."""
    try:
        worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}
        requests = []
        position = 0
        for title in MANUAL_TABS_ORDER:
            ws = worksheets.get(title)
            if not ws:
                continue
            requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "index": position, "tabColor": MANUAL_TAB_COLOR},
                    "fields": "index,tabColor",
                }
            })
            position += 1
        for title in MANUAL_COLOR_ONLY_TABS:
            ws = worksheets.get(title)
            if not ws:
                continue
            requests.append({
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "tabColor": MANUAL_TAB_COLOR},
                    "fields": "tabColor",
                }
            })
        if requests:
            spreadsheet.batch_update({"requests": requests})
            print(f"[SHEET] 수기 관리 탭 {len(requests)}개 파란색 적용(왼쪽 정렬 {position}개)", file=sys.stderr)
    except Exception as exc:
        print(f"[SHEET] 탭 정렬 실패(무시): {exc}", file=sys.stderr)


def push_all(spreadsheet: gspread.Spreadsheet, reset: bool) -> None:
    if reset:
        reset_worksheets(spreadsheet)
    push_stock_management_tab(spreadsheet)
    push_simple_schedule_tab(spreadsheet)
    push_simple_event_tabs(spreadsheet)
    for title, filename, columns in TAB_CONFIG:
        push_tab(spreadsheet, title, filename, columns)
    cleanup_obsolete_tabs(spreadsheet)
    arrange_sheet_tabs(spreadsheet)  # 수기 관리 탭 왼쪽 정렬 + 파란 탭 색




def main() -> None:
    args = parse_args()
    spreadsheet = build_client().open_by_key(sheet_id())


    if args.command == "pull-admin":
        pull_admin(spreadsheet)
    elif args.command == "push-all":
        push_all(spreadsheet, reset=False)
    else:
        push_all(spreadsheet, reset=True)


    print("[SHEET] 동기화 완료", file=sys.stderr)




if __name__ == "__main__":
    main()
