"""Complete monthly Customs exports, reconciled against API totals."""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from decimal import Decimal
from datetime import date, datetime, timezone
from urllib.parse import urlencode, unquote
from urllib.request import urlopen
from xml.etree import ElementTree as ET
from scripts.config import DATA_GO_KR_API_KEY, ROOT_DIR

ENDPOINT = "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList"
HS = "8542321010"
PRODUCTS = {"dram": HS, "beauty": "3304999000", "transformer": "8504230000"}

def shift(month: str, offset: int) -> str:
    year, m = map(int, month.split("-"))
    n = year * 12 + m - 1 + offset
    return f"{n // 12:04d}-{n % 12 + 1:02d}"

def parse_all(raw: bytes, month: str, hs: str) -> tuple[list[dict], int, float]:
    root = ET.fromstring(raw)
    code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
    if code not in {"00", "0"}:
        raise ValueError(f"Customs API rejected request (code {code or 'unknown'}).")
    rows, totals, weights, seen = [], [], [], set()
    for item in root.findall(".//item"):
        country = (item.findtext("statCd") or "").strip()
        amount = (item.findtext("expDlr") or "").replace(",", "")
        if not re.fullmatch(r"\d+", amount):
            raise ValueError("Invalid export amount; cache unchanged.")
        value = int(amount)
        weight = (item.findtext("expWgt") or "").replace(",", "")
        if not re.fullmatch(r"\d+(\.\d+)?", weight):
            raise ValueError("Invalid export weight; cache unchanged.")
        kg = Decimal(weight)
        if country == "-":
            totals.append(value)
            weights.append(kg)
            continue
        period = (item.findtext("year") or "").replace(".", "-").strip()
        if period != month or (item.findtext("hsCd") or "").strip() != hs:
            raise ValueError("Unexpected period or HS code; cache unchanged.")
        if not re.fullmatch(r"[A-Z0-9]{2}", country) or country in seen:
            raise ValueError("Invalid or duplicate country code; cache unchanged.")
        seen.add(country)
        rows.append({"month": month, "country": country, "usd": value, "kg": float(kg)})
    if len(totals) != 1 or sum(r["usd"] for r in rows) != totals[0]:
        raise ValueError("Country sum differs from API total; possible truncated response. Cache unchanged.")
    weight_sum = sum(Decimal(str(r["kg"])) for r in rows)
    # Integer-kg response rows can round independently from the official total.
    tolerance = Decimal(len(rows) + 1) / 2
    if len(weights) != 1 or abs(weight_sum - weights[0]) > tolerance:
        raise ValueError(f"Country weight differs from API total ({month}: {weight_sum} vs {weights}); cache unchanged.")
    return rows, totals[0], float(weights[0])

def fetch_all(month: str, hs: str) -> tuple[list[dict], int, float]:
    # Omit cntyCd: the API returns every destination for the specified HS code.
    query = urlencode({"serviceKey": unquote(DATA_GO_KR_API_KEY or ""),
                       "strtYymm": month.replace("-", ""), "endYymm": month.replace("-", ""), "hsSgn": hs})
    for attempt in range(3):
        try:
            with urlopen(f"{ENDPOINT}?{query}", timeout=30) as response:
                raw = response.read()
            return parse_all(raw, month, hs)
        except (ValueError, ET.ParseError):
            raise
        except Exception as error:
            if attempt == 2:
                raise RuntimeError(f"Customs connection failed ({type(error).__name__}); no cache changes.") from None
            time.sleep(attempt + 1)
    raise RuntimeError("Customs response unavailable.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--product", choices=[*PRODUCTS, "all"], default="all")
    parser.add_argument("--end", default=shift(date.today().strftime("%Y-%m"), -2))
    args = parser.parse_args()
    if not DATA_GO_KR_API_KEY:
        raise ValueError("DATA_GO_KR_API_KEY is missing.")
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.end):
        raise ValueError("--end must be YYYY-MM")
    for product in PRODUCTS if args.product == "all" else [args.product]:
        hs = PRODUCTS[product]
        if args.probe:
            rows, total, kg = fetch_all(args.end, hs)
            print(f"{product}: {len(rows)} countries, USD {total}, kg {kg}; totals reconciled.")
            continue
        rows, totals, weight_totals = [], {}, {}
        for i in range(35, -1, -1):
            month = shift(args.end, -i)
            monthly, total, kg = fetch_all(month, hs)
            rows.extend(monthly)
            totals[month] = total
            weight_totals[month] = kg
            if i % 6 == 0:
                print(f"{product} {month}: {len(monthly)} countries; total reconciled.", flush=True)
        codes = sorted({r["country"] for r in rows})
        output = ROOT_DIR / f"data/trade/{product}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        temp = output.with_suffix(".tmp")
        temp.write_text(json.dumps({"mode": "live", "hs": hs, "countryCodes": codes, "scope": "all-countries",
            "monthlyTotals": totals, "monthlyWeightTotals": weight_totals, "source": "https://www.data.go.kr/data/15100475/openapi.do",
            "retrievedAt": datetime.now(timezone.utc).isoformat(), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf8")
        temp.replace(output)
        print(f"Saved {product}: {len(rows)} rows, {len(codes)} countries/territories, 36 verified monthly totals.", flush=True)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, ET.ParseError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
