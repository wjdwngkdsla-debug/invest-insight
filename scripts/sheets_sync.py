"""운영 CSV(lockup_admin/review_needed/lockup_log)를 구글시트로 업로드한다.

- 시트가 엑셀 대신 운영자 검증용 서버 역할을 한다.
- 인증: 프로젝트 루트의 구글 서비스계정 키(project-*.json). 시트에 해당
  서비스계정 이메일이 편집자로 공유되어 있어야 한다.
- 실행: python -m scripts.sheets_sync  (scripts.build 실행 후)
"""
from __future__ import annotations

import csv
import glob
import sys
from pathlib import Path

import gspread

ROOT_DIR = Path(__file__).resolve().parents[1]

SHEET_ID = "1THcCbn5n9NQesOa0JHV3B-pdCeab8sRqMZhxOIWI-pg"

# (시트 탭 이름, data/ 아래 CSV 파일명)
TAB_FILES = [
    ("락업이벤트", "lockup_admin.csv"),
    ("검토필요", "review_needed.csv"),
    ("로그", "lockup_log.csv"),
]


def find_service_account() -> str:
    hits = sorted(glob.glob(str(ROOT_DIR / "project-*.json")))
    if not hits:
        raise FileNotFoundError("구글 서비스계정 키(project-*.json)가 프로젝트 루트에 없습니다.")
    return hits[0]


def read_rows(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def main() -> None:
    gc = gspread.service_account(filename=find_service_account())
    sh = gc.open_by_key(SHEET_ID)

    for tab, fname in TAB_FILES:
        rows = read_rows(ROOT_DIR / "data" / fname)
        try:
            ws = sh.worksheet(tab)
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(title=tab, rows=max(len(rows) + 10, 100), cols=40)
        ws.clear()
        if rows:
            ws.update(rows, "A1", value_input_option="USER_ENTERED")
        print(f"[SHEET] {tab}: {len(rows)}행 업로드", file=sys.stderr)

    print("[SHEET] 업로드 완료", file=sys.stderr)


if __name__ == "__main__":
    main()
