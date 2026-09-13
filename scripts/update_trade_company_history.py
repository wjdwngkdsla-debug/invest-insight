"""Local trade overlays: monthly official closes and standalone DART quarters."""
from __future__ import annotations
import argparse
import calendar
import json
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote
import requests
from scripts.config import ROOT_DIR, DATA_GO_KR_API_KEY, DART_API_KEY, KRX_HEADERS, KRX_URLS
from scripts.sources.dart_api import get_corp_code

PRICE_URL = "https://apis.data.go.kr/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo"
DART_URL = "https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json"
REPORTS = {1: "11013", 2: "11012", 3: "11014", 4: "11011"}
STARTED = time.monotonic()

def fetch(url, params):
    if time.monotonic() - STARTED > 300:
        raise RuntimeError("Five-minute collection limit reached")
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError):
        # Never expose request URLs containing API credentials.
        raise RuntimeError("Source request failed or returned non-JSON data") from None

def amount(value):
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-"}:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        number = Decimal(text)
        return int(number) if number.is_finite() and number == number.to_integral_value() else None
    except InvalidOperation:
        return None

def account(rows, metric, field="thstrm_amount"):
    ids = {"revenue": {"ifrs-full_Revenue", "ifrs_Revenue"}, "operatingProfit": {"dart_OperatingIncomeLoss"}}[metric]
    names = {"revenue": {"매출액", "영업수익", "수익(매출액)"}, "operatingProfit": {"영업이익", "영업이익(손실)", "영업손실"}}[metric]
    rows = [r for r in rows if r.get("sj_div") in {"IS", "CIS"} and r.get("currency", "KRW") == "KRW"]
    for matches in ([r for r in rows if r.get("account_id") in ids], [r for r in rows if r.get("account_nm", "").replace(" ", "") in names]):
        for row in matches:
            value = amount(row.get(field))
            if value is not None:
                return value
    return None

def prices(ticker, start, end):
    if not DATA_GO_KR_API_KEY:
        raise RuntimeError("DATA_GO_KR_API_KEY missing")
    daily = {}
    count = None
    for page in range(1, 6):
        data = fetch(PRICE_URL, {"serviceKey": unquote(DATA_GO_KR_API_KEY), "resultType": "json", "numOfRows": 1000,
            "pageNo": page, "beginBasDt": start.replace("-", "") + "01", "endBasDt": end.replace("-", "") + str(calendar.monthrange(int(end[:4]), int(end[5:]))[1]), "likeSrtnCd": ticker})
        response = data.get("response", {})
        code = str(response.get("header", {}).get("resultCode"))
        if code not in {"00", "0"}:
            raise RuntimeError("Stock API authorization or response error")
        body = response.get("body", {})
        count = int(body.get("totalCount", 0))
        items = body.get("items", {}).get("item", []) or []
        if isinstance(items, dict):
            items = [items]
        for row in items:
            if str(row.get("srtnCd", "")).removeprefix("A") != ticker:
                raise RuntimeError("Unexpected stock code")
            date = datetime.strptime(str(row["basDt"]), "%Y%m%d").strftime("%Y-%m-%d")
            close = amount(row.get("clpr"))
            if date in daily or close is None or close <= 0 or not start <= date[:7] <= end:
                raise RuntimeError("Invalid stock observation")
            daily[date] = close
        if len(daily) >= count:
            break
    if len(daily) != count or not daily:
        raise RuntimeError("Incomplete stock history")
    monthly = {}
    for date in sorted(daily):
        monthly[date[:7]] = {"month": date[:7], "date": date, "close": daily[date]}
    return list(monthly.values())

def quarters(ticker, name, start, end):
    if not DART_API_KEY:
        raise RuntimeError("DART_API_KEY missing")
    try:
        corp = get_corp_code(name, stock_code=ticker)
    except (requests.RequestException, ValueError):
        raise RuntimeError("DART company registry unavailable") from None
    if not corp or corp["stock_code"] != ticker:
        raise RuntimeError("DART company mapping missing")
    result = []
    for year in range(int(start[:4]), int(end[:4]) + 1):
        prior_ytd = None
        for quarter in range(1, 5):
            month = f"{year}-{quarter * 3:02d}"
            if month > end:
                break
            data = fetch(DART_URL, {"crtfc_key": DART_API_KEY, "corp_code": corp["corp_code"], "bsns_year": year, "reprt_code": REPORTS[quarter], "fs_div": "CFS"})
            if data.get("status") == "013":
                prior_ytd = None
                continue
            if data.get("status") != "000":
                raise RuntimeError("DART response rejected")
            rows = data.get("list", [])
            values = {key: account(rows, key) for key in ("revenue", "operatingProfit")}
            ytd = {key: account(rows, key, "thstrm_add_amount") for key in values}
            # Q1-Q3 thstrm_amount is a standalone three-month IS/CIS amount.
            # Q4 must be derived from annual amount less the Q3 cumulative amount.
            if quarter == 4:
                values = {key: values[key] - prior_ytd[key] if values[key] is not None and prior_ytd and prior_ytd[key] is not None else None for key in values}
            prior_ytd = ytd
            receipt = next((r.get("rcept_no") for r in rows if r.get("rcept_no")), "")
            if month >= start and any(v is not None for v in values.values()):
                result.append({"month": month, "period": f"{year}.{quarter}Q", **values, "basis": "CFS", "receipt": receipt,
                    "filedAt": f"{receipt[:4]}-{receipt[4:6]}-{receipt[6:8]}" if len(receipt) >= 8 else None})
    return result

def krx_prices(links, months):
    result = {link["ticker"]: [] for link in links}
    for month in months:
        year, m = map(int, month.split("-"))
        last = date(year, m, calendar.monthrange(year, m)[1])
        for back in range(8):
            day = last - timedelta(days=back)
            if day.weekday() >= 5:
                continue
            if time.monotonic() - STARTED > 300:
                raise RuntimeError("Five-minute collection limit reached")
            rows, complete = [], True
            for url, _ in KRX_URLS:
                try:
                    response = requests.post(url, headers=KRX_HEADERS, json={"basDd": day.strftime("%Y%m%d")}, timeout=10)
                    response.raise_for_status()
                    items = response.json().get("OutBlock_1", [])
                except (requests.RequestException, ValueError):
                    raise RuntimeError("KRX monthly history unavailable") from None
                rows.extend(items)
                complete = complete and bool(items)
            if not complete:
                continue
            for row in rows:
                ticker = str(row.get("ISU_CD", ""))
                close = amount(row.get("TDD_CLSPRC"))
                if ticker in result and close is not None and close > 0:
                    result[ticker].append({"month": month, "date": day.isoformat(), "close": close})
            break
        print(f"KRX {month}: monthly close checked", flush=True)
    return result

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--price-source", choices=["krx", "data-go"], default="krx")
    args = parser.parse_args()
    folder = ROOT_DIR / "data/trade"
    products = [json.loads((folder / f"{p}.json").read_text(encoding="utf8")) for p in ("dram", "beauty", "transformer")]
    months = sorted({r["month"] for p in products for r in p["rows"]})
    links = json.loads((folder / "company-links.json").read_text(encoding="utf8"))
    output = folder / "company-history.json"
    old = {c["id"]: c for c in json.loads(output.read_text(encoding="utf8")).get("companies", [])} if output.exists() else {}
    companies = []
    for link in links:
        entry = {**link, "prices": [], "quarters": [], **old.get(link["id"], {}), "errors": []}
        collectors = [("quarters", lambda: quarters(link["ticker"], link["name"], months[0], months[-1]))]
        if args.price_source == "data-go":
            collectors.append(("prices", lambda: prices(link["ticker"], months[0], months[-1])))
        for field, collect in collectors:
            try:
                entry[field] = collect()
                entry[field + "RetrievedAt"] = datetime.now(timezone.utc).isoformat()
                print(f"{link['name']} {field}: {len(entry[field])} observations", flush=True)
            except (RuntimeError, ValueError, KeyError) as error:
                entry["errors"].append(f"{field}: {error}")
                print(f"{link['name']} {field}: unavailable ({error})", flush=True)
        companies.append(entry)
    price_source = "https://www.data.go.kr/data/15094808/openapi.do"
    if args.price_source == "krx":
        try:
            fallback = krx_prices(links, months)
            for entry in companies:
                if fallback.get(entry["ticker"]):
                    entry["prices"] = fallback[entry["ticker"]]
                    entry["pricesRetrievedAt"] = datetime.now(timezone.utc).isoformat()
                    entry["errors"] = [e for e in entry["errors"] if not e.startswith("prices:")]
            price_source = "https://openapi.krx.co.kr/"
        except RuntimeError as error:
            print(str(error), flush=True)
            for entry in companies:
                entry["errors"].append(f"prices: {error}")
    payload = {"version": 1, "priceSource": price_source, "financialSource": "https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020",
        "priceBasis": "unadjusted-month-end-close", "pricePublicUse": "requires-license", "companies": companies}
    temp = output.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    temp.replace(output)

if __name__ == "__main__":
    main()
