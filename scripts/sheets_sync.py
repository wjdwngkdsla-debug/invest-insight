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
    "event_id", "code", "name", "market", "listing_date", "shares", "close_price",
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
    "listing_date", "close_price", "shares",
    "planned_date", "planned_qty", "planned_pct",
    "api_return_date", "api_return_qty", "api_reason",
    "manual_lock", "manual_date", "manual_qty", "memo",
    "final_date", "final_tradable_date", "final_qty", "final_pct",
    "status", "review_needed",
    "event_id", "type", "planned_tradable_date", "planned_date_display",
    "dart_rcp", "dart_source", "parse_note", "final_date_display", "updated_at",
]

REVIEW_COLUMNS = [
    "detected_at", "event_id", "code", "name", "category", "period", "issue",
    "planned_date", "planned_qty", "api_return_date", "api_return_qty",
    "manual_date", "manual_qty", "memo",
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

HEADER_KO = {
    "event_id": "이벤트ID",
    "code": "종목코드",
    "name": "종목명",
    "market": "시장",
    "listing_date": "상장일",
    "shares": "상장주식수",
    "close_price": "종가",
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

TAB_CONFIG = [
    ("운영_락업일정", "lockup_admin.csv", ADMIN_SHEET_COLUMNS),
    ("검토필요", "review_needed.csv", REVIEW_COLUMNS),
    ("변경로그", "lockup_log.csv", LOG_COLUMNS),
]

MANUAL_COLUMNS = ("manual_lock", "manual_date", "manual_qty", "memo")


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
    return label


def internal_header(value: str) -> str:
    cleaned = value.strip()
    if cleaned in HEADER_INTERNAL:
        return HEADER_INTERNAL[cleaned]
    # "종가(26-07-08)"처럼 기준일이 붙은 종가 헤더도 인식
    if cleaned.startswith("종가("):
        return "close_price"
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


def admin_worksheet(spreadsheet: gspread.Spreadsheet) -> gspread.Worksheet:
    for title in ("운영_락업일정", "락업이벤트", "lockup_admin"):
        try:
            return spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            pass
    return spreadsheet.get_worksheet(0)


def pull_admin(spreadsheet: gspread.Spreadsheet) -> None:
    csv_path = ROOT_DIR / "data" / "lockup_admin.csv"
    local_rows = read_csv_dicts(csv_path)
    if not local_rows:
        print("[SHEET] 로컬 lockup_admin.csv가 없어 내려받기를 건너뜁니다.", file=sys.stderr)
        return

    sheet_rows = worksheet_records(admin_worksheet(spreadsheet))
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
    pull_review_decisions(spreadsheet)


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


def reset_worksheets(spreadsheet: gspread.Spreadsheet) -> None:
    worksheets = spreadsheet.worksheets()
    first_title = TAB_CONFIG[0][0]
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


def push_rows(
    spreadsheet: gspread.Spreadsheet,
    title: str,
    rows: list[dict],
    columns: list[str],
) -> None:
    values = [[header_label(column) for column in columns]]
    values.extend([[row.get(column, "") for column in columns] for row in rows])

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
    print(f"[SHEET] {title}: {len(rows)}개 행 업로드", file=sys.stderr)


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

    merged_rows = []
    for row in rows:
        saved = decision_by_code.get(row.get("code", ""), {})
        merged = {**row, **{
            "review_decision": saved.get("review_decision", ""),
            "review_memo": saved.get("review_memo", ""),
        }}
        if merged.get("code") in admin_codes:
            continue
        merged_rows.append(merged)

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


def push_all(spreadsheet: gspread.Spreadsheet, reset: bool) -> None:
    if reset:
        reset_worksheets(spreadsheet)
    for title, filename, columns in TAB_CONFIG:
        push_tab(spreadsheet, title, filename, columns)
    push_universe_review(spreadsheet)


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
