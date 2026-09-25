"""Bounded DART repair and a local audit; never writes to Google Sheets directly.

python -m scripts.audit_ipo_quality --refresh --corp-code 01137860 --write
python -m scripts.audit_ipo_quality --write
"""
import argparse
import copy
import csv
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from scripts.config import ROOT_DIR
from scripts.ipo_quality import PERIODS, quality_gaps, quality_advisories, tier_quantity
from scripts.sources.dart_api import get_reports, select_latest_investment_report, download_document_text, holder_snapshot, merge_holder_snapshot, _clean_text
from scripts.sources.ipo_schedule import _parse_demand_tables, _is_confirmed_ipo, parse_offering_doc, parse_result_report
from scripts.sources.listing_dates import dart_listing_candidates, reconcile_listing_date
from scripts.utils.redaction import redact_sensitive_text


def merge_tiers(item, field, rows, receipt):
    previous = {r["period"]: r for r in item.get(field) or []}
    manual = item.get("manual_" + field) or {}
    merged = []
    for row in rows:
        old = previous.get(row["period"], {})
        fixed = manual.get(row["period"]) or {}
        if fixed.get("locked"):
            row = {**row, **fixed, "source": "manual_fixed"}
        elif old.get("locked") or old.get("source") == "manual_fixed":
            row = old
        else:
            row = {**row, "rcept_no": receipt}
        merged.append(row)
    item[field] = merged


def refresh_result(item, reports, today):
    if not item.get("sub_end") or item["sub_end"] > today:
        return
    results = [r for r in reports if "증권발행실적보고서" in r.get("report_nm", "")
               and r.get("rcept_dt", "") >= item["sub_end"].replace("-", "")]
    results.sort(key=lambda r: (r.get("rcept_dt", ""), r.get("rcept_no", "")), reverse=True)
    if not results:
        item["result_source_check"] = {"status": "waiting" if not item.get("report_rcp") else "review",
                                        "checked_at": today}
        return
    receipt = results[0]["rcept_no"]
    parsed = parse_result_report(download_document_text(receipt))
    rows = parsed.get("commit_alloc") or []
    if rows:
        merge_tiers(item, "commit_alloc", rows, receipt)
    if parsed.get("sub_ratio") and "sub_ratio" not in (item.get("manual_fields") or []):
        item["sub_ratio"] = parsed["sub_ratio"]
    item["report_rcp"] = receipt
    item.pop("result_report_missing", None)
    tiers = {r["period"]: r for r in rows}
    complete = all(tier_quantity(tiers.get(p)) is not None for p in PERIODS) and parsed.get("sub_ratio")
    item["result_source_check"] = {"status": "verified" if complete else "parse_incomplete",
                                    "checked_at": today, "rcept_no": receipt}


def retry_targets(items, today, selected=()):
    if selected:
        return [i for i in items if i.get("corp_code") in selected]
    cutoff = (datetime.fromisoformat(today) - timedelta(days=90)).date().isoformat()
    targets = [i for i in items if (i.get("listing_date") or today) >= cutoff
               or i.get("quality_refresh_error") or i.get("holder_source_error") or (i.get("holder_lockup") or {}).get("status") == "review"
               or (i.get("result_source_check") or {}).get("status") == "parse_incomplete"
               or any(tier_quantity(t) is None for f in ("commit_apply", "commit_alloc") for t in i.get(f) or [])]
    targets = [i for i in targets if i.get("quality_attempted_at") != today]
    return sorted(targets, key=lambda i: (i.get("quality_attempted_at", ""), i.get("listing_date") or today, i.get("corp_code", "")))


def repair_item(item, today):
    listing = item.get("listing_date") or today
    start = (datetime.fromisoformat(listing) - timedelta(days=240)).strftime("%Y%m%d")
    end = min(today, (datetime.fromisoformat(listing) + timedelta(days=30)).date().isoformat()).replace("-", "")
    reports = get_reports(item["corp_code"], start, end)
    selected = select_latest_investment_report(reports)
    if not selected:
        raise ValueError("IPO 기간 내 투자설명서/증권신고서 없음")
    receipt = selected["rcept_no"]
    doc = download_document_text(receipt)
    kind = parse_offering_doc(doc, selected.get("report_nm", "")).get("security_type")
    if kind == "non_equity":
        item.update(security_type=kind, review_pending=True, review_reason="주식 IPO가 아닌 발행증권 제외")
        return
    if kind:
        item["security_type"] = kind
    item["holder_lockup"] = merge_holder_snapshot(item.get("holder_lockup"), holder_snapshot(doc, receipt))
    item["holder_lockup"]["quantity_unit"] = "DR" if kind == "depositary_receipt" else "주"
    item.pop("holder_source_error", None)
    _, applications = _parse_demand_tables(doc)
    if applications:
        merge_tiers(item, "commit_apply", applications, receipt)
        item.pop("commit_apply_missing", None)
    refresh_result(item, reports, today)
    item["listing_date_check"] = reconcile_listing_date(item, dart_listing_candidates(_clean_text(doc), receipt))
    item["quality_checked_at"] = today
    item.pop("quality_refresh_error", None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--corp-code", action="append", default=[])
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error("--limit must be 1..10")
    path = ROOT_DIR / "data" / "ipo_schedule.json"
    schedule = json.loads(path.read_text(encoding="utf-8"))
    items = schedule.get("items", []) + schedule.get("past_items", [])
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    today = now.date().isoformat()
    eligible = [i for i in items if not any(i.get(f) for f in ("withdrawn", "fixed_excluded", "management_hidden", "schedule_hidden")) and _is_confirmed_ipo(i)]
    failures, refreshed = [], []
    if args.refresh:
        targets = retry_targets(eligible, today, args.corp_code)
        for item in targets[:args.limit]:
            item["quality_attempted_at"] = today
            try:
                candidate = copy.deepcopy(item)
                repair_item(candidate, today)
                item.clear()
                item.update(candidate)
                refreshed.append(item["name"])
                print(item["name"], "holders:", (item.get("holder_lockup") or {}).get("status"), "applications:", sum(tier_quantity(t) or 0 for t in item.get("commit_apply") or []))
            except Exception as exc:
                error = redact_sensitive_text(exc)
                item["quality_refresh_error"] = {"checked_at": today, "message": error}
                failures.append({"corp_code": item.get("corp_code"), "name": item["name"], "error": error})
    with (ROOT_DIR / "data" / "lockup_admin.csv").open(encoding="utf-8-sig", newline="") as f:
        holder_codes = {r["code"] for r in csv.DictReader(f) if r.get("category") == "구주·보호예수"}
    issues = []
    from scripts.ipo_evidence import apply_approved_allocations, reconcile_reported_capital
    apply_approved_allocations(schedule)
    for item in eligible:
        reconcile_reported_capital(item)
        gaps = quality_gaps(item, item.get("stock_code") in holder_codes, today=today)
        if gaps:
            issues.append({"corp_code": item.get("corp_code"), "code": item.get("stock_code"), "name": item["name"], "gaps": gaps})
    advisories = [{"corp_code": i.get("corp_code"), "name": i["name"], "notes": quality_advisories(i)}
                  for i in eligible if quality_advisories(i)]
    report = {"checked_at": now.isoformat(), "refreshed": refreshed, "failures": failures, "issues": issues, "advisories": advisories}
    if args.write:
        path.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
        (ROOT_DIR / "data" / "ipo_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[IPO QA] {len(eligible)} checked; {len(issues)} need review; {len(failures)} source failures")
    if failures:
        print(json.dumps(failures, ensure_ascii=False))


if __name__ == "__main__":
    main()
