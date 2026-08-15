"""[사용 중단] 맥북 고정 IP에서 토스 수정주가를 확인해 종목관리 시트에 기록한다.

scripts/price_adjustments.py가 KRX 등락률만으로 같은 조정계수를 계산한다.
18종목 전부 토스 값과 일치했고(최대 차이 0.006%) 허용 IP 등록이 필요 없어
GitHub Actions에서 그대로 돈다. 배치는 이제 KRX 값을 쓴다.

이 스크립트는 교차검증용으로만 남겨 둔다. 토스 키가 만료돼도 사이트에는 영향이 없다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import gspread
import requests
from gspread import Cell

from scripts.sheets_sync import DEFAULT_SHEET_ID, build_client
from scripts.utils.redaction import redact_sensitive_text


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_TOSS_ENV = ROOT_DIR.parent / "toss-market-demo" / ".env"
TAB_NAME = "종목관리"
LISTING_DAY_PATH = ROOT_DIR / "data" / "listing_day.json"
ADJUSTMENT_HEADERS = ["수정공모가", "공모가조정계수", "수정주가확인일", "수정주가상태"]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def number(value: object) -> Decimal:
    text = str(value or "").replace(",", "").strip()
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal(0)


def normalize_symbol(value: object) -> str:
    symbol = re.sub(r"[^A-Za-z0-9.\-]", "", str(value or "")).upper()
    return symbol.zfill(6) if symbol.isdigit() and len(symbol) < 6 else symbol


def adjusted_offer_price(offer_price: object, raw_close: object, adjusted_close: object) -> tuple[Decimal, Decimal]:
    offer = number(offer_price)
    raw = number(raw_close)
    adjusted = number(adjusted_close)
    if offer <= 0 or raw <= 0 or adjusted <= 0:
        raise ValueError("공모가 또는 상장일 종가가 0입니다")
    factor = adjusted / raw
    price = (offer * factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return price, factor.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


class TossClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("TOSS_API_BASE_URL", "https://openapi.tossinvest.com").rstrip("/")
        self.client_id = os.getenv("TOSS_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("TOSS_CLIENT_SECRET", "").strip()
        self.chart_delay = float(os.getenv("TOSS_CHART_DELAY_SECONDS", "1.1"))
        self.session = requests.Session()
        self.token = ""
        self.last_chart_call = 0.0
        if not self.client_id or not self.client_secret:
            raise RuntimeError("TOSS_CLIENT_ID/TOSS_CLIENT_SECRET이 없습니다")

    def authenticate(self) -> None:
        response = self.session.post(
            f"{self.base_url}/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=20,
        )
        payload = response.json()
        if not response.ok:
            message = payload.get("error_description") or payload.get("error") or response.status_code
            raise RuntimeError(f"토스 인증 실패: {message}")
        self.token = str(payload.get("access_token") or "")
        if not self.token:
            raise RuntimeError("토스 인증 응답에 access_token이 없습니다")

    def _pace_chart(self) -> None:
        remaining = self.chart_delay - (time.monotonic() - self.last_chart_call)
        if remaining > 0:
            time.sleep(remaining)

    def candle(self, symbol: str, listing_date: str, adjusted: bool) -> dict[str, Any]:
        params = {
            "symbol": symbol,
            "interval": "1d",
            "count": 5,
            "before": f"{listing_date}T23:59:59+09:00",
            "adjusted": "true" if adjusted else "false",
        }
        for attempt in range(5):
            self._pace_chart()
            response = self.session.get(
                f"{self.base_url}/api/v1/candles",
                params=params,
                headers={"authorization": f"Bearer {self.token}"},
                timeout=30,
            )
            self.last_chart_call = time.monotonic()
            payload = response.json()
            if response.status_code == 429:
                retry_after = float(response.headers.get("retry-after") or (2 ** attempt))
                time.sleep(retry_after + 0.2)
                continue
            if not response.ok:
                error = payload.get("error") or {}
                raise RuntimeError(str(error.get("message") or error.get("code") or response.status_code))
            candles = ((payload.get("result") or {}).get("candles") or [])
            found = next((item for item in candles if str(item.get("timestamp") or "")[:10] == listing_date), None)
            if not found:
                raise RuntimeError("상장일 일봉 없음")
            return found
        raise RuntimeError("토스 호출 한도 재시도 초과")


def ensure_headers(spreadsheet: gspread.Spreadsheet, worksheet: gspread.Worksheet) -> list[str]:
    headers = [str(value).strip() for value in worksheet.row_values(1)]
    missing = [header for header in ADJUSTMENT_HEADERS if header not in headers]
    if not missing:
        return headers
    start = len(headers) + 1
    if worksheet.col_count < len(headers) + len(missing):
        worksheet.add_cols(len(headers) + len(missing) - worksheet.col_count)
    worksheet.update([missing], f"{gspread.utils.rowcol_to_a1(1, start)}", value_input_option="USER_ENTERED")
    worksheet.format(
        f"{gspread.utils.rowcol_to_a1(1, start)}:{gspread.utils.rowcol_to_a1(1, start + len(missing) - 1)}",
        {
            "backgroundColor": {"red": 0.82, "green": 0.89, "blue": 1.0},
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER",
        },
    )
    requests_payload = []
    for offset in range(len(missing)):
        requests_payload.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": worksheet.id,
                    "dimension": "COLUMNS",
                    "startIndex": start - 1 + offset,
                    "endIndex": start + offset,
                },
                "properties": {"hiddenByUser": True},
                "fields": "hiddenByUser",
            }
        })
    spreadsheet.batch_update({"requests": requests_payload})
    return [str(value).strip() for value in worksheet.row_values(1)]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="토스 수정주가 주간 확인 → 종목관리 시트 기록")
    parser.add_argument("--dry-run", action="store_true", help="조회만 하고 시트에는 쓰지 않음")
    parser.add_argument("--limit", type=int, default=0, help="테스트용 최대 종목 수(0=전체)")
    parser.add_argument("--codes", default="", help="쉼표로 구분한 특정 종목코드만 확인")
    parser.add_argument("--toss-env", default="", help="토스 키가 저장된 env 파일")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env_file(ROOT_DIR / ".env.local")
    load_env_file(ROOT_DIR / ".env")
    toss_env = Path(args.toss_env or os.getenv("TOSS_ENV_FILE") or DEFAULT_TOSS_ENV).expanduser()
    load_env_file(toss_env)

    spreadsheet = build_client().open_by_key(os.getenv("GOOGLE_SHEET_ID", DEFAULT_SHEET_ID))
    worksheet = spreadsheet.worksheet(TAB_NAME)
    headers = ensure_headers(spreadsheet, worksheet) if not args.dry_run else [str(v).strip() for v in worksheet.row_values(1)]
    missing = [header for header in ["관리", "기업명", "종목코드", "상장일", "공모가"] if header not in headers]
    if missing:
        raise RuntimeError(f"종목관리 필수 컬럼 없음: {', '.join(missing)}")
    if args.dry_run:
        headers.extend(header for header in ADJUSTMENT_HEADERS if header not in headers)

    values = worksheet.get_all_values()
    try:
        listing_day = json.loads(LISTING_DAY_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        listing_day = {}
    selected_codes = {normalize_symbol(code) for code in args.codes.split(",") if code.strip()}
    targets: list[tuple[int, dict[str, str]]] = []
    for row_number, cells in enumerate(values[1:], start=2):
        padded = cells + [""] * (len(headers) - len(cells))
        row = dict(zip(headers, padded))
        code = normalize_symbol(row.get("종목코드", ""))
        listing_date = str(row.get("상장일") or "").strip()
        managed = str(row.get("관리") or "").strip().upper()
        if managed in {"FALSE", "N", "0"} or not re.fullmatch(r"[A-Z0-9.\-]{6,12}", code):
            continue
        if selected_codes and code not in selected_codes:
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", listing_date) or listing_date > date.today().isoformat():
            continue
        if number(row.get("공모가")) <= 0:
            continue
        targets.append((row_number, row))
    if args.limit > 0:
        targets = targets[:args.limit]
    if not targets:
        print("[TOSS] 확인할 상장 종목이 없습니다")
        return

    client = TossClient()
    client.authenticate()
    checked_at = date.today().isoformat()
    column = {header: headers.index(header) + 1 for header in ADJUSTMENT_HEADERS}
    pending_cells: list[Cell] = []
    success = adjusted_count = failed = 0

    def flush() -> None:
        nonlocal pending_cells
        if pending_cells and not args.dry_run:
            worksheet.update_cells(pending_cells, value_input_option="USER_ENTERED")
        pending_cells = []

    print(f"[TOSS] 수정주가 확인 시작: {len(targets)}종목")
    for index, (row_number, row) in enumerate(targets, start=1):
        code = normalize_symbol(row["종목코드"])
        name = row.get("기업명") or code
        try:
            adjusted = client.candle(code, row["상장일"], adjusted=True)
            cached = listing_day.get(code) or {}
            raw_close = cached.get("close_price") if cached.get("listing_date") == row["상장일"] else None
            if not number(raw_close):
                # KRX 상장일 캐시가 없는 예외 종목만 토스 원주가를 한 번 더 조회한다.
                raw_close = client.candle(code, row["상장일"], adjusted=False).get("closePrice")
            adjusted_price, factor = adjusted_offer_price(row["공모가"], raw_close, adjusted.get("closePrice"))
            status = "조정적용" if abs(factor - Decimal(1)) > Decimal("0.00000001") else "미조정"
            pending_cells.extend([
                Cell(row_number, column["수정공모가"], float(adjusted_price)),
                Cell(row_number, column["공모가조정계수"], float(factor)),
                Cell(row_number, column["수정주가확인일"], checked_at),
                Cell(row_number, column["수정주가상태"], status),
            ])
            success += 1
            adjusted_count += status == "조정적용"
            print(f"  [{index}/{len(targets)}] {name}: {status} (계수 {factor})")
        except Exception as exc:
            failed += 1
            print(
                f"  [{index}/{len(targets)}] {name}: 실패 - {redact_sensitive_text(exc)}",
                file=sys.stderr,
            )
        if index % 10 == 0:
            flush()
    flush()
    mode = "DRY-RUN" if args.dry_run else "시트 기록"
    print(f"[TOSS] 완료({mode}): 성공 {success} / 조정 {adjusted_count} / 실패 {failed}")


if __name__ == "__main__":
    main()
