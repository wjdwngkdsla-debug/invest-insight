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
from pathlib import Path


import gspread
from gspread.utils import rowcol_to_a1


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SHEET_ID = "1THcCbn5n9NQesOa0JHV3B-pdCeab8sRqMZhxOIWI-pg"


ADMIN_COLUMNS = [
    "event_id", "code", "name", "market", "listing_date", "shares", "current_shares", "shares_date",
    "close_price", "ipo_price",
    "category", "type", "period",
    "planned_date", "planned_tradable_date", "planned_date_display", "planned_qty", "planned_pct",
    "dart_rcp", "dart_source", "parse_note",
    "api_return_date", "api_return_qty", "api_reason",
    "manual_date", "manual_qty", "manual_lock",
    "final_date", "final_tradable_date", "final_date_display", "final_qty", "final_pct",
    "status", "review_needed", "memo", "updated_at",
]


ADMIN_SHEET_COLUMNS = [
    "name", "code", "market", "category", "period",
    "listing_date", "close_price", "ipo_price", "shares", "current_shares",
    "planned_date", "planned_qty", "planned_pct",
    "api_return_date", "api_return_qty", "api_reason",
    "manual_lock", "manual_date", "manual_qty", "memo",
    "final_date", "final_tradable_date", "final_qty", "final_pct",
    "status", "review_needed",
    "event_id", "type", "planned_tradable_date", "planned_date_display",
    "dart_rcp", "dart_source", "parse_note", "final_date_display", "updated_at",
]


IPO_ADMIN_SHEET_COLUMNS = [
    "name", "code", "market", "period",
    "listing_date", "close_price", "ipo_price", "shares", "current_shares",
    "planned_date", "planned_qty", "planned_pct",
    "manual_lock", "manual_date", "manual_qty", "memo",
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
    "manual_lock", "manual_date", "manual_qty", "memo",
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


# 작업목록 탭 — 운영자 보완 입력의 단일 창구. 배치가 "다 채운 행"만 수거해 표준
# 통로(IPO종목 수동공모가 / 수기입력)로 옮기고, 남은 갭만 다시 나열한다.
# 규칙: 빈칸 = 무시(다음 목록에 유지), 전부 채움 = 반영, 일부만 채움 = 값 보존.
WORKLIST_TAB = "작업목록"
WORKLIST_BACKUP_PATH = ROOT_DIR / "data" / "worklist_backup.json"


IPO_SCHEDULE_PATH = ROOT_DIR / "data" / "ipo_schedule.json"
IPO_SCHEDULE_TAB = "IPO일정"
IPO_SCHEDULE_BACKUP_PATH = ROOT_DIR / "data" / "ipo_schedule_sheet_backup.json"
# 배치가 마지막으로 쓴 값 스냅샷 — 시트 값과 이게 다르면 "사용자 수정"으로 판정한다
IPO_SCHEDULE_WRITTEN_PATH = ROOT_DIR / "data" / "ipo_sheet_written.json"
COMMIT_TIER_ORDER = ["미확약", "15일", "1개월", "3개월", "6개월"]
IPO_SCHEDULE_HEADERS = [
    "기업명", "상태", "시장", "주관사", "희망가액", "확정공모가", "공모주식수",
    "수요예측일", "청약일", "상장일", "수요예측경쟁률", "개인청약경쟁률",
    "신청_미확약", "신청_15일", "신청_1개월", "신청_3개월", "신청_6개월",
    "배정_미확약", "배정_15일", "배정_1개월", "배정_3개월", "배정_6개월",
    "콘텐츠링크",
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
TAB_CONFIG = [
    ("변경로그", "lockup_log.csv", LOG_COLUMNS),
]


ADMIN_TAB_CONFIG = [
    ("IPO기관", "IPO기관", IPO_ADMIN_SHEET_COLUMNS),
    ("기존주주", "구주·보호예수", FLOAT_ADMIN_SHEET_COLUMNS),
]
LEGACY_ADMIN_TABS = ("운영_락업일정", "락업이벤트", "lockup_admin")


MANUAL_COLUMNS = ("manual_lock", "manual_date", "manual_qty", "memo")
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




def pull_admin(spreadsheet: gspread.Spreadsheet) -> None:
    csv_path = ROOT_DIR / "data" / "lockup_admin.csv"
    local_rows = read_csv_dicts(csv_path)
    if not local_rows:
        print("[SHEET] 로컬 lockup_admin.csv가 없어 내려받기를 건너뜁니다.", file=sys.stderr)
        return


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
    print(f"[SHEET] 수동 수정값 내려받기 완료: {updated}개 행", file=sys.stderr)
    pull_worklist(spreadsheet)  # 작업목록의 완성 행을 수동공모가/수기입력으로 이관 (백업 포함)
    pull_ipo_targets(spreadsheet)
    pull_manual_events(spreadsheet)
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
        if not name or not code or not match:
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
    tmap = {t["code"]: t for t in targets}


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


    worksheet = spreadsheet.add_worksheet(title=WORKLIST_TAB, rows=len(out) + 30, cols=8)
    worksheet.update(out, "A1", value_input_option="USER_ENTERED")
    for line_no, row in enumerate(out, start=1):
        if row[0].startswith("[") or row[0] == "종목코드":
            worksheet.format(f"{line_no}:{line_no}", {"textFormat": {"bold": True}})
    print(f"[SHEET] 작업목록 재생성: 공모가 {len(no_price)} / 구주 {len(no_float)} / IPO확약 {len(no_ipo)}종목", file=sys.stderr)




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
    first_title = ADMIN_TAB_CONFIG[0][0]
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
    push_rows(spreadsheet, title, rows, columns)



def push_admin_tabs(spreadsheet: gspread.Spreadsheet) -> None:
    rows = read_csv_dicts(ROOT_DIR / "data" / "lockup_admin.csv")
    for title, category, columns in ADMIN_TAB_CONFIG:
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
    """IPO 일정 현황을 IPO일정 탭에 적재하고, 운영자 입력을 수거한다.

    - 콘텐츠링크: 운영자 입력 열. 기업명 기준으로 수거해 content_url로 연결.
    - 확정공모가/수요예측일/청약일/상장일: 운영자가 고치면(마지막으로 배치가 쓴 값과
      다르면) 그 값을 채택하고 manual_fields로 잠궈 이후 공시 파싱이 덮어쓰지 않는다.
    - 나머지 열은 공시 기준으로 매번 덮어쓴다. 덮어쓰기 전 탭 전체 값을 백업한다.
    """
    if not IPO_SCHEDULE_PATH.exists():
        return
    try:
        data = json.loads(IPO_SCHEDULE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    items = data.get("items", [])

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
    try:
        worksheet = spreadsheet.worksheet(IPO_SCHEDULE_TAB)
        values = worksheet.get_all_values()
        if values:
            IPO_SCHEDULE_BACKUP_PATH.write_text(
                json.dumps({"values": values}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            headers = [h.strip() for h in values[0]]
            if "기업명" in headers:
                name_at = headers.index("기업명")
                col_at = {col: headers.index(col) for col in list(IPO_EDITABLE_COLUMNS) + ["콘텐츠링크"] if col in headers}
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
        if manual_fields:
            item["manual_fields"] = manual_fields

    if changed:
        IPO_SCHEDULE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[SHEET] IPO일정: 운영자 입력 반영 (수동수정 {overrides}건, 링크 {len(links)}건)", file=sys.stderr)

    # 3) 탭 재작성 + 쓴 값 스냅샷 저장
    rows: list[list[str]] = []
    new_written: dict[str, dict[str, str]] = {}
    for item in items:
        name = item.get("name") or ""
        band_low, band_high = item.get("band_low") or 0, item.get("band_high") or 0
        apply_map = commit_qty_map(item.get("commit_apply"))
        alloc_map = commit_qty_map(item.get("commit_alloc"))
        row = [
            name,
            _ipo_status_label(item),
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

    sheet_values = [IPO_SCHEDULE_HEADERS] + rows
    worksheet = get_or_create_worksheet(spreadsheet, IPO_SCHEDULE_TAB, len(sheet_values) + 10, len(IPO_SCHEDULE_HEADERS))
    worksheet.clear()
    worksheet.update(sheet_values, "A1", value_input_option="USER_ENTERED")
    worksheet.freeze(rows=1)
    worksheet.format(
        "1:1",
        {
            "backgroundColor": {"red": 0.91, "green": 0.94, "blue": 1.0},
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
        },
    )
    IPO_SCHEDULE_WRITTEN_PATH.write_text(json.dumps(new_written, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SHEET] IPO일정: {len(rows)}개 종목 적재 (콘텐츠링크 {len(links)}건 보존)", file=sys.stderr)

    # 정정이력 탭 — 정정공시·수기변경으로 값이 바뀐 내역 (최신순)
    hist = data.get("history") or []
    if hist:
        hist_values = [["일자", "기업명", "구분", "항목", "이전값", "새값"]] + [
            [h.get("date", ""), h.get("name", ""), h.get("type", ""), h.get("field", ""), str(h.get("old", "")), str(h.get("new", ""))]
            for h in reversed(hist[-300:])
        ]
        hist_ws = get_or_create_worksheet(spreadsheet, "정정이력", len(hist_values) + 10, 6)
        hist_ws.clear()
        hist_ws.update(hist_values, "A1", value_input_option="RAW")
        hist_ws.freeze(rows=1)
        hist_ws.format("1:1", {"backgroundColor": {"red": 0.91, "green": 0.94, "blue": 1.0}, "textFormat": {"bold": True}})
        print(f"[SHEET] 정정이력: {len(hist_values) - 1}건 적재", file=sys.stderr)


def append_missing_ipo_targets(spreadsheet: gspread.Spreadsheet) -> None:
    """IPO일정에 상장일이 채워졌는데 IPO종목 탭에 없는 기업을 자동 추가한다.

    append-only: 기존 행은 절대 수정하지 않고 없는 기업만 뒤에 붙인다. 추가 전 탭 전체 백업.
    종목코드는 RAW로 써서 앞자리 0이 잘리지 않게 한다 (064400 → 64400 사고 방지).
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
    existing = {norm(row[name_at]) for row in values[1:] if len(row) > name_at and row[name_at].strip()}

    new_rows: list[list[str]] = []
    for item in candidates:
        if norm(item.get("name") or "") in existing:
            continue
        code = str(item.get("stock_code") or "").strip()
        new_rows.append([
            item.get("market") or "코스닥",
            item.get("name") or "",
            item.get("listing_date") or "",
            code.zfill(6) if code else "",
            "",
        ])
    if new_rows:
        worksheet.append_rows(new_rows, value_input_option="RAW")
        names = ", ".join(row[1] for row in new_rows)
        print(f"[SHEET] IPO종목: IPO일정 상장일 기반 자동 추가 {len(new_rows)}건 ({names})", file=sys.stderr)


# 운영자가 직접 입력·관리하는 탭 — 왼쪽에 몰아서 파란 탭 색으로 구분한다
MANUAL_TABS_ORDER = ["작업목록", "수기입력", "IPO종목", "IPO일정", "휴장일"]
# IPO기관·기존주주는 위치는 그대로 두되(핵심 원장), 수동 보정 컬럼(수동공모가/수동확정일수량/메모)이
# 있어 운영자가 직접 만지는 탭이므로 같은 파란 탭 색만 입힌다.
MANUAL_COLOR_ONLY_TABS = ["IPO기관", "기존주주"]
MANUAL_TAB_COLOR = {"red": 0.26, "green": 0.52, "blue": 0.96}


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
    push_admin_tabs(spreadsheet)
    for title, filename, columns in TAB_CONFIG:
        push_tab(spreadsheet, title, filename, columns)
    ensure_ipo_target_manual_price_column(spreadsheet)
    ensure_manual_event_tab(spreadsheet)  # 수기입력 탭은 항상 존재하되 내용은 보존
    sync_ipo_schedule_tab(spreadsheet)  # IPO 일정 적재 + 콘텐츠링크·수동수정 수거 + 정정이력
    append_missing_ipo_targets(spreadsheet)  # IPO일정 상장일 입력 → IPO종목 자동 행 추가 (append-only)
    regenerate_worklist(spreadsheet)  # 남은 갭만 다시 나열 (미반영 입력값은 보존)
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
