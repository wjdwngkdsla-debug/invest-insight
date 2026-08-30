from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "value-chain"
KRW_EOK = 100_000_000
DART_BASE = "https://opendart.fss.or.kr/api"

ANNUAL_REPORT = "11011"
QUARTER_REPORTS = ["11012", "11014", "11013"]
SALES_NAMES = ("매출액", "영업수익", "수익(매출액)", "영업수익(매출액)")
OPERATING_PROFIT_NAMES = ("영업이익", "영업손실")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_json(name: str):
    with (DATA_DIR / name).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(name: str, data) -> None:
    with (DATA_DIR / name).open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def clean_amount(value: object) -> int | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"-", "—"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    try:
        amount = int(float(text))
    except ValueError:
        return None
    return -amount if negative else amount


def to_eok(value: int | None) -> int:
    if value is None:
        return 0
    return round(value / KRW_EOK)


def fetch_single_accounts(corp_code: str, year: int, reprt_code: str) -> list[dict]:
    api_key = os.getenv("DART_API_KEY", "")
    if not api_key:
        return []
    for fs_div in ("CFS", "OFS"):
        res = requests.get(
            f"{DART_BASE}/fnlttSinglAcnt.json",
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": reprt_code,
                "fs_div": fs_div,
            },
            timeout=30,
        )
        res.raise_for_status()
        payload = res.json()
        if payload.get("status") == "000" and payload.get("list"):
            return payload["list"]
    return []


def find_account_value(rows: list[dict], names: tuple[str, ...], field: str = "thstrm_amount") -> int | None:
    for name in names:
        matched = [row for row in rows if str(row.get("account_nm") or "").strip() == name]
        if not matched:
            matched = [row for row in rows if name in str(row.get("account_nm") or "")]
        for row in matched:
            value = clean_amount(row.get(field))
            if value is not None:
                return value
    return None


def latest_annual_series(corp_code: str, base_year: int) -> tuple[list[int], list[int], int | None]:
    annual_sales: list[int] = []
    annual_op: list[int] = []
    latest_op_margin: int | None = None
    for year in range(base_year - 2, base_year + 1):
        rows = fetch_single_accounts(corp_code, year, ANNUAL_REPORT)
        sales = find_account_value(rows, SALES_NAMES)
        op = find_account_value(rows, OPERATING_PROFIT_NAMES)
        annual_sales.append(to_eok(sales))
        annual_op.append(to_eok(op))
        if year == base_year and sales and op is not None:
            latest_op_margin = round((op / sales) * 100, 1)
    return annual_sales, annual_op, latest_op_margin


def latest_quarter(corp_code: str, base_year: int) -> tuple[int, int]:
    for year in (base_year + 1, base_year):
        for reprt_code in QUARTER_REPORTS:
            rows = fetch_single_accounts(corp_code, year, reprt_code)
            sales = find_account_value(rows, SALES_NAMES)
            op = find_account_value(rows, OPERATING_PROFIT_NAMES)
            if sales is not None or op is not None:
                return to_eok(sales), to_eok(op)
    return 0, 0


def main() -> None:
    load_env_file(ROOT / ".env.local")
    load_env_file(ROOT / ".env")
    if not os.getenv("DART_API_KEY"):
        print("[value-chain-financials] DART_API_KEY missing; skipped financial cache update")
        return

    import scripts.config as config
    import scripts.sources.dart_api as dart_api

    config.DART_API_KEY = os.getenv("DART_API_KEY", "")
    dart_api.DART_API_KEY = os.getenv("DART_API_KEY", "")

    companies = read_json("companies.json")
    financials = read_json("financials.json")
    financials_by_id = {item["companyId"]: item for item in financials}
    current_year = datetime.now(ZoneInfo("Asia/Seoul")).year
    base_year = current_year - 1
    updated = 0
    skipped = 0

    for company in companies:
        if company.get("region") != "domestic" or company.get("listing") != "listed":
            skipped += 1
            continue
        ticker = str(company.get("ticker") or "").strip()
        if not ticker:
            skipped += 1
            continue
        corp = dart_api.get_corp_code(company.get("name") or "", stock_code=ticker)
        if not corp:
            skipped += 1
            continue
        sales, op, margin = latest_annual_series(corp["corp_code"], base_year)
        quarter_sales, quarter_op = latest_quarter(corp["corp_code"], base_year)
        if not any(sales) and not any(op) and not quarter_sales and not quarter_op:
            skipped += 1
            continue

        item = financials_by_id.setdefault(
            company["id"],
            {
                "companyId": company["id"],
                "asOf": "",
                "status": "needsReview",
                "sourceIds": [],
                "marketCap": None,
                "annual": {"sales": [0, 0, 0], "operatingProfit": [0, 0, 0], "opMargin": 0, "per": None},
                "recentQuarter": {"sales": 0, "operatingProfit": 0},
            },
        )
        item["asOf"] = f"DART {base_year} 사업보고서 / KRX 시총 별도"
        item["status"] = "needsReview"
        item["sourceIds"] = sorted(set([*(item.get("sourceIds") or []), "dart-financials"]))
        item["annual"]["sales"] = sales
        item["annual"]["operatingProfit"] = op
        if margin is not None:
            item["annual"]["opMargin"] = margin
        item["recentQuarter"]["sales"] = quarter_sales
        item["recentQuarter"]["operatingProfit"] = quarter_op
        updated += 1

    ordered = [financials_by_id.get(company["id"]) for company in companies if financials_by_id.get(company["id"])]
    write_json("financials.json", ordered)
    print(f"[value-chain-financials] updated {updated} financial rows, skipped {skipped}")


if __name__ == "__main__":
    main()
