from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "value-chain"
KRW_EOK = 100_000_000


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


def latest_cached_date(metrics: dict) -> date | None:
    dates: list[str] = []
    for issue in metrics.get("issues", []):
        for company in issue.get("companies", []):
            for period in ("day", "week", "month", "quarter", "half"):
                for point in company.get(period, {}).get("tradingValueIndex", []):
                    if point.get("date"):
                        dates.append(point["date"])
    if not dates:
        return None
    try:
        return date.fromisoformat(max(dates))
    except ValueError:
        return None


def find_anchor_date(krx_snapshot, metrics: dict, lookback_days: int = 12) -> date:
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    cached = latest_cached_date(metrics)
    if cached and 0 <= (today - cached).days <= lookback_days:
        return cached
    for back in range(lookback_days + 1):
        target = today - timedelta(days=back)
        snap = krx_snapshot(target.strftime("%Y%m%d"))
        if snap:
            return target
    if cached:
        return cached
    raise RuntimeError("KRX snapshots not available")


def trading_days(krx_snapshot, metrics: dict, days: int | None = None) -> list[tuple[str, dict]]:
    if days is None:
        days = int(os.getenv("VALUE_CHAIN_KRX_LOOKBACK_DAYS", "70"))
    anchor = find_anchor_date(krx_snapshot, metrics)
    out: list[tuple[str, dict]] = []
    for back in range(days):
        bas_dd = (anchor - timedelta(days=back)).strftime("%Y%m%d")
        snap = krx_snapshot(bas_dd)
        if snap:
            out.append((f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}", snap))
    return list(reversed(out))


def period_points(days: list[tuple[str, dict]], period: str) -> list[tuple[str, dict]]:
    if period == "day":
        return days[-2:]
    if period == "week":
        return days[-7:]
    if period == "month":
        return days[-22:]
    if period == "quarter":
        return days[-66:]
    if period == "half":
        return days[-132:]
    return days[-22:]


def pct_change(first: int, last: int) -> float:
    if not first:
        return 0.0
    return round(((last - first) / first) * 100, 1)


def build_company_market_series(ticker: str, days: list[tuple[str, dict]], period: str):
    points = period_points(days, period)
    values = []
    closes = []
    market_caps = []
    for date, snap in points:
        row = snap.get(ticker)
        if not row:
            continue
        close = int(row.get("close_price") or 0)
        trading_value = int(row.get("trading_value") or 0)
        market_cap = int(row.get("market_cap") or 0)
        if close:
            closes.append(close)
        if market_cap:
            market_caps.append(market_cap)
        values.append(
            {
                "date": date,
                "value": round(trading_value / KRW_EOK, 1),
            }
        )
    return {
        "tradingValueIndex": values,
        "returnPct": pct_change(closes[0], closes[-1]) if len(closes) >= 2 else 0.0,
        "currentPrice": closes[-1] if closes else None,
        "marketCap": market_caps[-1] if market_caps else None,
    }


def ensure_metric_groups(metrics: dict, issues: list[dict], companies_by_id: dict[str, dict]) -> None:
    metric_groups_by_id = {item.get("issueId"): item for item in metrics.get("issues", [])}
    for issue in issues:
        issue_id = issue.get("id")
        if not issue_id:
            continue
        group = metric_groups_by_id.get(issue_id)
        if not group:
            group = {
                "issueId": issue_id,
                "topicId": issue.get("topicId"),
                "score": {
                    "composite": issue.get("composite", 0),
                    "returnScore": issue.get("returnScore", 0),
                    "searchScore": issue.get("searchScore", 0),
                    "tradingValueScore": issue.get("volumeScore", 0),
                },
                "summary": {
                    "avgReturnPct": issue.get("avgReturnPct", 0),
                    "searchChangePct": issue.get("searchChangePct", 0),
                    "tradingValueChangePct": issue.get("volumeChangePct", 0),
                },
                "companies": [],
            }
            metrics.setdefault("issues", []).append(group)
            metric_groups_by_id[issue_id] = group

        metrics_by_company = {item.get("companyId"): item for item in group.get("companies", [])}
        valid_company_ids = [company_id for company_id in issue.get("companyIds", []) if company_id in companies_by_id]
        group["companies"] = [item for item in group.get("companies", []) if item.get("companyId") in valid_company_ids]
        metrics_by_company = {item.get("companyId"): item for item in group.get("companies", [])}
        for company_id in valid_company_ids:
            company = companies_by_id.get(company_id)
            if not company or company_id in metrics_by_company:
                continue
            group.setdefault("companies", []).append(
                {
                    "companyId": company_id,
                    "issueId": issue_id,
                    "role": company.get("role", ""),
                    "relation": company.get("roleDetail", ""),
                    "score": 60,
                    "week": {
                        "searchIndex": [],
                        "tradingValueIndex": [],
                        "returnPct": 0,
                    },
                    "month": {
                        "searchIndex": [],
                        "tradingValueIndex": [],
                        "returnPct": 0,
                    },
                    "day": {
                        "searchIndex": [],
                        "tradingValueIndex": [],
                        "returnPct": 0,
                    },
                    "quarter": {
                        "searchIndex": [],
                        "tradingValueIndex": [],
                        "returnPct": 0,
                    },
                    "half": {
                        "searchIndex": [],
                        "tradingValueIndex": [],
                        "returnPct": 0,
                    },
                }
            )


def main() -> None:
    load_env_file(ROOT / ".env.local")
    load_env_file(ROOT / ".env")
    if not os.getenv("KRX_API_KEY"):
        raise RuntimeError("KRX_API_KEY is required for value-chain trading value and return cache updates")

    from scripts.sources.krx import krx_snapshot

    companies = read_json("companies.json")
    issues = read_json("issues.json")
    financials = read_json("financials.json")
    metrics = read_json("market-metrics.json")
    companies_by_id = {item["id"]: item for item in companies}
    financials_by_id = {item["companyId"]: item for item in financials}
    ensure_metric_groups(metrics, issues, companies_by_id)
    days = trading_days(krx_snapshot, metrics)
    if not days:
        raise RuntimeError("KRX snapshots not available")

    updated_market_caps = 0
    updated_metric_rows = 0
    as_of = days[-1][0]

    for issue in metrics.get("issues", []):
        for metric in issue.get("companies", []):
            company = companies_by_id.get(metric.get("companyId"))
            ticker = company.get("ticker") if company else None
            if not ticker:
                continue
            for period in ("day", "week", "month", "quarter", "half"):
                metric.setdefault(period, {"searchIndex": [], "tradingValueIndex": [], "returnPct": 0})
                market = build_company_market_series(ticker, days, period)
                if market["tradingValueIndex"]:
                    metric[period]["tradingValueIndex"] = market["tradingValueIndex"]
                    metric[period]["returnPct"] = market["returnPct"]
                    if market["currentPrice"]:
                        metric[period]["currentPrice"] = market["currentPrice"]
                    updated_metric_rows += 1
                if market["marketCap"] and company["id"] in financials_by_id:
                    financials_by_id[company["id"]]["marketCap"] = round(market["marketCap"] / KRW_EOK)
                    financials_by_id[company["id"]]["asOf"] = f"KRX {as_of}"
                    updated_market_caps += 1

    metrics["generatedAt"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    metrics["status"] = "live-cache"
    metrics["note"] = "검색량은 네이버 검색어트렌드 상대지수, 거래대금은 KRX 일별 거래대금(억원), 수익률은 기간 첫 종가 대비 마지막 종가 등락률입니다."

    write_json("market-metrics.json", metrics)
    write_json("financials.json", financials)
    print(f"[value-chain-market] updated {updated_metric_rows} metric rows, {updated_market_caps} market caps, as of {as_of}")


if __name__ == "__main__":
    main()
