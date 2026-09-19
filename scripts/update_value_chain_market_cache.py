from __future__ import annotations

import json
import os
import calendar
import time
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
    target = DATA_DIR / name
    temp = target.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    temp.replace(target)


def latest_cached_date(metrics: dict) -> date | None:
    dates: list[date] = []
    for issue in metrics.get("issues", []):
        for company in issue.get("companies", []):
            for period in ("day", "week", "month", "quarter", "half"):
                for point in company.get(period, {}).get("tradingValueIndex", []):
                    try:
                        dates.append(date.fromisoformat(point.get("date", "")))
                    except (ValueError, TypeError):
                        continue
    return max(dates) if dates else None


def find_anchor_date(krx_snapshot, metrics: dict, lookback_days: int = 12, *, today: date | None = None) -> date:
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date()
    cached = latest_cached_date(metrics)
    if cached and cached > today:
        cached = None
    for back in range(lookback_days + 1):
        target = today - timedelta(days=back)
        # Reuse the cache only after checking every newer business day.
        if cached and target <= cached:
            return cached
        if target.weekday() >= 5:
            continue
        snap = krx_snapshot(target.strftime("%Y%m%d"))
        if snap:
            return target
    if cached:
        return cached
    raise RuntimeError("KRX snapshots not available")


def trading_days(krx_snapshot, metrics: dict, days: int | None = None, *, history: dict | None = None, tickers: set[str] | None = None, checkpoint=None) -> list[tuple[str, dict]]:
    if days is None:
        days = int(os.getenv("VALUE_CHAIN_KRX_LOOKBACK_DAYS", "220"))
    anchor = find_anchor_date(krx_snapshot, metrics)
    history = history if history is not None else {}
    started = time.monotonic()
    out: list[tuple[str, dict]] = []
    for back in range(days):
        target = anchor - timedelta(days=back)
        if target.weekday() >= 5:
            continue
        if time.monotonic() - started > 720:
            raise RuntimeError("KRX history refresh exceeded 12 minutes; existing cache retained")
        bas_dd = target.strftime("%Y%m%d")
        cached = history.get(bas_dd)
        snap = cached if cached and back >= 7 and (not tickers or tickers <= set(cached)) else krx_snapshot(bas_dd)
        if not snap:
            snap = cached
        if snap:
            if tickers:
                snap = {key: {field: snap[key].get(field) for field in ("close_price", "trading_value", "market_cap")} if snap.get(key) else None for key in sorted(tickers)}
            history[bas_dd] = snap
            out.append((f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}", snap))
        if back % 20 == 0:
            if checkpoint:
                checkpoint(history)
            print(f"[value-chain-market] history {bas_dd}: {len(out)} trading dates", flush=True)
    cutoff = (anchor - timedelta(days=days)).strftime("%Y%m%d")
    for key in list(history):
        if key < cutoff:
            del history[key]
    return list(reversed(out))


def period_start(anchor: date, period: str) -> date:
    if period == "week":
        return anchor - timedelta(days=7)
    months = {"month": 1, "quarter": 3, "half": 6}[period]
    total = anchor.year * 12 + anchor.month - 1 - months
    year, month = total // 12, total % 12 + 1
    return date(year, month, min(anchor.day, calendar.monthrange(year, month)[1]))


def period_points(days: list[tuple[str, dict]], period: str) -> list[tuple[str, dict]]:
    if not days:
        return []
    if period == "day":
        return days[-2:]
    cutoff = period_start(date.fromisoformat(days[-1][0]), period).isoformat()
    baseline = next((i for i in range(len(days) - 1, -1, -1) if days[i][0] <= cutoff), None)
    return days[baseline:] if baseline is not None else days


def pct_change(first: int, last: int) -> float:
    if not first:
        return 0.0
    return round(((last - first) / first) * 100, 1)


def build_company_market_series(ticker: str, days: list[tuple[str, dict]], period: str):
    points = period_points(days, period)
    values = []
    closes = []
    market_caps = []
    for point_date, snap in points:
        row = snap.get(ticker)
        if not row:
            continue
        close = int(row.get("close_price") or 0)
        trading_value = row.get("trading_value")
        market_cap = int(row.get("market_cap") or 0)
        if close:
            closes.append(close)
        if market_cap:
            market_caps.append(market_cap)
        if trading_value is not None:
            values.append({
                "date": point_date,
                "value": round(int(trading_value) / KRW_EOK, 1),
            })
    enough_history = len(points) >= 2 and (period == "day" or points[0][0] <= period_start(date.fromisoformat(days[-1][0]), period).isoformat())
    complete = enough_history and len(closes) == len(points)
    return {
        "tradingValueIndex": values,
        "returnPct": pct_change(closes[0], closes[-1]) if complete else None,
        "marketSource": "KRX",
        "coverage": {"complete": complete, "from": points[0][0] if points else None, "to": points[-1][0] if points else None, "observations": len(closes)},
        "currentPrice": (points[-1][1].get(ticker) or {}).get("close_price") if points else None,
        "marketCap": (points[-1][1].get(ticker) or {}).get("market_cap") if points else None,
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
    history_path = DATA_DIR / "price-history.json"
    history = read_json("price-history.json") if history_path.exists() else {}
    tickers = {c["ticker"] for c in companies if c.get("ticker") and c.get("region") == "domestic"}
    days = trading_days(krx_snapshot, metrics, history=history, tickers=tickers, checkpoint=lambda data: write_json("price-history.json", data))
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
                metric[period].update({key: market[key] for key in ("tradingValueIndex", "returnPct", "currentPrice", "marketSource", "coverage")})
                if market["tradingValueIndex"]:
                    updated_metric_rows += 1
                if market["marketCap"] and company["id"] in financials_by_id:
                    financials_by_id[company["id"]]["marketCap"] = round(market["marketCap"] / KRW_EOK)
                    financials_by_id[company["id"]]["marketCapAsOf"] = as_of
                    updated_market_caps += 1

    metrics["generatedAt"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    metrics["status"] = "live-cache"
    metrics["note"] = "검색량은 네이버 검색어트렌드 상대지수, 거래대금은 KRX 일별 거래대금(억원), 수익률은 기간 첫 종가 대비 마지막 종가 등락률입니다."

    write_json("market-metrics.json", metrics)
    write_json("price-history.json", history)
    write_json("financials.json", financials)
    print(f"[value-chain-market] updated {updated_metric_rows} metric rows, {updated_market_caps} market caps, as of {as_of}")


if __name__ == "__main__":
    main()
