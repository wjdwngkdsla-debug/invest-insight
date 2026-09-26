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
from scripts.ipo_repair_memory import (parser_revision, retry_due, remember_attempt,
    capture_case, replay_cases, resolve_cases, protect_candidate)


def merge_tiers(item, field, rows, receipt):
    previous = {r["period"]: r for r in item.get(field) or []}
    manual = item.get("manual_" + field) or {}
    merged = copy.deepcopy(previous)
    for row in rows:
        if tier_quantity(row) is None:
            continue
        old = previous.get(row["period"], {})
        fixed = manual.get(row["period"]) or {}
        if fixed.get("locked"):
            row = {**row, **fixed, "source": "manual_fixed"}
        elif old.get("locked") or old.get("source") == "manual_fixed":
            row = old
        else:
            row = {**row, "rcept_no": receipt}
        merged[row['period']] = copy.deepcopy(row)
    for period, fixed in manual.items():
        if fixed.get('locked') and tier_quantity(fixed) is not None:
            merged[period] = {**merged.get(period, {}), **fixed, 'period': period, 'source': 'manual_fixed'}
    item[field] = list(merged.values())


def refresh_result(item, reports, today, artifacts=None):
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
    doc = download_document_text(receipt)
    parsed = parse_result_report(doc)
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
    if artifacts is not None:
        artifacts.append({'receipt': receipt, 'kind': 'allocations', 'document': doc,
                          'reason': '' if complete else '기관 배정표 또는 청약경쟁률 파싱 미완료'})


def retry_targets(items, today, selected=(), revision=None, holder_codes=()):
    if selected:
        return [i for i in items if i.get("corp_code") in selected]
    cutoff = (datetime.fromisoformat(today) - timedelta(days=90)).date().isoformat()
    revision = revision or parser_revision()
    targets = [i for i in items if (i.get("listing_date") or today) >= cutoff
               or i.get("quality_refresh_error") or i.get("holder_source_error") or (i.get("holder_lockup") or {}).get("status") == "review"
               or (i.get("result_source_check") or {}).get("status") == "parse_incomplete"
               or quality_gaps(i, i.get('stock_code') in holder_codes, today=today)]
    targets = [i for i in targets if retry_due(i, today, revision)]
    return sorted(targets, key=lambda i: (not bool(quality_gaps(i, i.get('stock_code') in holder_codes, today=today)),
                  i.get("quality_attempted_at", ""), i.get("listing_date") or today, i.get("corp_code", "")))


def repair_item(item, today, artifacts=None):
    listing = item.get("listing_date") or today
    start = (datetime.fromisoformat(listing) - timedelta(days=240)).strftime("%Y%m%d")
    end = min(today, (datetime.fromisoformat(listing) + timedelta(days=30)).date().isoformat()).replace("-", "")
    reports = get_reports(item["corp_code"], start, end)
    selected = select_latest_investment_report(reports)
    if not selected:
        raise ValueError("IPO 기간 내 투자설명서/증권신고서 없음")
    receipt = selected["rcept_no"]
    item['quality_offering_receipt'] = receipt
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
    tiers = {r['period']: r for r in applications}
    application_due = bool(item.get('demand_ratio') or item.get('report_rcp')
                           or (item.get('forecast_end') and item['forecast_end'] < today))
    from scripts.ipo_evidence import demand_waiting
    if application_due and not demand_waiting(item, today):
        complete = all(tier_quantity(tiers.get(p)) is not None for p in PERIODS)
        item['application_source_check'] = {'status': 'verified' if complete else 'parse_incomplete',
                                          'checked_at': today, 'rcept_no': receipt}
    if artifacts is not None:
        snapshot = item['holder_lockup']
        artifacts.append({'receipt': receipt, 'kind': 'holders', 'document': doc,
                          'table_index': snapshot.get('table_index'),
                          'reason': snapshot.get('reason', '') if snapshot.get('status') != 'verified' else ''})
        if (item.get('application_source_check') or {}).get('status') == 'parse_incomplete':
            artifacts.append({'receipt': receipt, 'kind': 'applications', 'document': doc,
                              'reason': '기관 신청표 파싱 미완료'})
    refresh_result(item, reports, today, artifacts)
    item["listing_date_check"] = reconcile_listing_date(item, dart_listing_candidates(_clean_text(doc), receipt))
    item["quality_checked_at"] = today
    item.pop("quality_refresh_error", None)


def attempt_repair(item, today, revision, memory, has_holders=False):
    artifacts = []
    candidate = copy.deepcopy(item)
    item['quality_attempted_at'] = today
    try:
        repair_item(candidate, today, artifacts)
        from scripts.ipo_evidence import apply_approved_allocations, reconcile_reported_capital
        apply_approved_allocations({'items': [candidate]})
        reconcile_reported_capital(candidate)
        rejected = protect_candidate(item, candidate, today, has_holders)
        if rejected:
            item['quality_refresh_error'] = {'checked_at': today, 'message': '자동 반영 보류: ' + '; '.join(rejected)}
            outcome, reasons = 'rejected', rejected
        else:
            candidate['quality_attempted_at'] = today
            item.clear()
            item.update(candidate)
            reasons = quality_gaps(item, has_holders, today=today)
            outcome = 'unresolved' if reasons else 'verified'
            if not reasons:
                resolve_cases(memory, item, today)
        for artifact in artifacts:
            if artifact['reason'] or outcome in ('rejected', 'unresolved'):
                artifact = {**artifact, 'reason': artifact['reason'] or '; '.join(reasons)}
                capture_case(memory, item, today=today, revision=revision, **artifact)
    except Exception as exc:
        error = redact_sensitive_text(exc)
        item['quality_refresh_error'] = {'checked_at': today, 'message': error}
        outcome, reasons = 'source_error', [error]
        for artifact in artifacts:
            if artifact['reason']:
                capture_case(memory, item, today=today, revision=revision, **artifact)
    remember_attempt(item, today, revision, outcome, reasons)
    return outcome, reasons


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
    with (ROOT_DIR / "data" / "lockup_admin.csv").open(encoding="utf-8-sig", newline="") as f:
        holder_codes = {r["code"] for r in csv.DictReader(f) if r.get("category") == "구주·보호예수"}
    memory_path = ROOT_DIR / 'data' / 'ipo_parser_cases.json'
    memory = json.loads(memory_path.read_text(encoding='utf-8')) if memory_path.exists() else {'cases': {}}
    revision = parser_revision()
    replay_cases(memory, revision)
    if args.refresh:
        targets = retry_targets(eligible, today, args.corp_code, revision, holder_codes)
        for item in targets[:args.limit]:
            outcome, reasons = attempt_repair(item, today, revision, memory, item.get('stock_code') in holder_codes)
            if outcome == 'verified':
                refreshed.append(item["name"])
            if outcome == 'source_error':
                failures.append({'corp_code': item.get('corp_code'), 'name': item['name'], 'error': '; '.join(reasons)})
            print(item['name'], outcome, 'next retry:', item['quality_repair_state']['next_retry'])
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
    report['repair_memory'] = {'cases': len(memory['cases']), 'evicted_cases': memory.get('evicted_cases', 0),
        'recheck_candidates': sum(c.get('probe') == 'full_document_recheck' and c.get('status') != 'resolved' for c in memory['cases'].values()),
        'retries': [{'corp_code': i.get('corp_code'), 'name': i['name'], **i['quality_repair_state']}
                    for i in eligible if i.get('quality_repair_state')]}
    if args.write:
        path.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding="utf-8")
        (ROOT_DIR / "data" / "ipo_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        memory_path.write_text(json.dumps(memory, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"[IPO QA] {len(eligible)} checked; {len(issues)} need review; {len(failures)} source failures")
    if failures:
        print(json.dumps(failures, ensure_ascii=False))


if __name__ == "__main__":
    main()
