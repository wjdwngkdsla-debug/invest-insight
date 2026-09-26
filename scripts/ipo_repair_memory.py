"""Bounded failure memory and offline probes; probes never publish financial values."""
import copy
import hashlib
import json
import re
from datetime import date, timedelta

from scripts.config import ROOT_DIR

MAX_CASES = 80
MAX_EXCERPT = 48000


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def parser_revision():
    paths = ('scripts/sources/dart_api.py', 'scripts/sources/ipo_schedule.py',
             'scripts/ipo_quality.py', 'scripts/ipo_evidence.py',
             'scripts/audit_ipo_quality.py', 'scripts/ipo_repair_memory.py',
             'data/ipo_review_evidence.json')
    return digest([((ROOT_DIR / p).read_text(encoding='utf-8')) for p in paths])


def source_revision(item):
    return digest({
        'receipts': [item.get('last_rcept_no'), item.get('quality_offering_receipt'), item.get('report_rcp'),
                     (item.get('holder_lockup') or {}).get('rcept_no')],
        'inputs': {k: item.get(k) for k in ('initial_shares', 'listing_date', 'forecast_end',
                   'sub_end', 'manual_fields', 'manual_commit_apply', 'manual_commit_alloc', 'holder_overrides')},
    })


def retry_due(item, today, revision):
    state = item.get('quality_repair_state') or {}
    changed = state and (state.get('parser_revision') != revision
                         or state.get('source_revision') != source_revision(item))
    if changed:
        return True
    if item.get('quality_attempted_at') == today:
        return False
    return not state.get('next_retry') or state['next_retry'] <= today


def remember_attempt(item, today, revision, outcome, reasons):
    old = item.get('quality_repair_state') or {}
    source = source_revision(item)
    signature = digest([source, revision, outcome, sorted(reasons)])
    attempts = old.get('consecutive_attempts', 0) + 1 if old.get('signature') == signature else 1
    delay = 1 if outcome in ('verified', 'source_error') else min(7, 2 ** min(attempts - 1, 3))
    history = (old.get('history') or []) + [{'at': today, 'outcome': outcome, 'reasons': reasons[:12]}]
    item['quality_repair_state'] = {
        'parser_revision': revision, 'source_revision': source, 'signature': signature,
        'consecutive_attempts': attempts, 'outcome': outcome, 'last_attempt': today,
        'next_retry': (date.fromisoformat(today) + timedelta(days=delay)).isoformat(),
        'history': history[-5:],
    }


def capture_case(memory, item, receipt, kind, reason, document, today, revision, table_index=None):
    """Store only bounded public filing tables, not full documents or API responses."""
    tables = re.findall(r'<TABLE[\s\S]*?</TABLE>', document, flags=re.I)
    if isinstance(table_index, int) and 0 < table_index <= len(tables):
        matches = [tables[table_index - 1]]
    else:
        matches = [t for t in tables if any(k in t for k in ('유통가능', '매각제한', '확약기간', '의무보유'))]
    excerpt = '\n'.join(matches[:4])
    truncated = len(matches) > 4 or len(excerpt) > MAX_EXCERPT
    excerpt = excerpt[:MAX_EXCERPT]
    key = digest([item.get('corp_code'), item.get('offering_attempt', 1), receipt, kind, excerpt])
    cases = memory.setdefault('cases', {})
    previous = cases.get(key, {})
    cases[key] = {**previous, 'corp_code': item.get('corp_code'), 'name': item.get('name'),
                  'receipt': receipt, 'kind': kind, 'reason': reason,
                  'first_seen': previous.get('first_seen', today), 'last_seen': today,
                  'observations': previous.get('observations', 0) + 1,
                  'status': 'unresolved', 'captured_parser': revision,
                  'excerpt': excerpt, 'truncated': truncated}
    while len(cases) > MAX_CASES:
        oldest = min(cases, key=lambda k: (cases[k].get('status') != 'resolved', cases[k]['last_seen'], k))
        del cases[oldest]
        memory['evicted_cases'] = memory.get('evicted_cases', 0) + 1
    return key


def replay_cases(memory, revision):
    from scripts.sources.dart_api import holder_snapshot
    from scripts.sources.ipo_schedule import _parse_demand_tables, parse_result_report
    from scripts.ipo_quality import PERIODS, tier_quantity

    for case in memory.get('cases', {}).values():
        if case.get('replayed_parser') == revision or case.get('status') == 'resolved':
            continue
        case['replayed_parser'] = revision
        if not case.get('excerpt') or case.get('truncated'):
            case['probe'] = 'full_document_required'
            continue
        try:
            if case['kind'] == 'holders':
                passed = holder_snapshot(case['excerpt'], case['receipt']).get('status') == 'verified'
            else:
                rows = (_parse_demand_tables(case['excerpt'])[1] if case['kind'] == 'applications'
                        else parse_result_report(case['excerpt']).get('commit_alloc', []))
                tiers = {r['period']: r for r in rows}
                passed = all(tier_quantity(tiers.get(p)) is not None for p in PERIODS)
            case['probe'] = 'full_document_recheck' if passed else 'still_unresolved'
        except (ValueError, TypeError, KeyError, IndexError):
            case['probe'] = 'still_unresolved'


def resolve_cases(memory, item, today):
    """Only a complete, fresh source verification can close its matching cases."""
    receipts = {'holders': (item.get('holder_lockup') or {}).get('rcept_no'),
                'applications': item.get('quality_offering_receipt'), 'allocations': item.get('report_rcp')}
    for case in memory.get('cases', {}).values():
        if case['corp_code'] == item.get('corp_code') and case['receipt'] == receipts.get(case['kind']):
            case.update(status='resolved', resolved_at=today, resolution='full_document_verified')


def protect_candidate(previous, candidate, today, has_holders=False):
    from scripts.ipo_quality import quality_gaps, tier_quantity
    old = copy.deepcopy(previous)
    old.pop('quality_refresh_error', None)
    before = set(quality_gaps(old, has_holders, today=today))
    after = set(quality_gaps(candidate, has_holders, today=today))
    regressions = after - before
    for field in ('result_source_check', 'application_source_check'):
        if ((candidate.get(field) or {}).get('status') == 'parse_incomplete'
                and (previous.get(field) or {}).get('status') != 'parse_incomplete'):
            regressions.add(f'{field}: 새 원문 파싱 미완료')
    # Even when an old source was incomplete, never silently discard known tiers.
    for field in ('commit_apply', 'commit_alloc'):
        current = {r['period']: r for r in candidate.get(field) or []}
        for row in previous.get(field) or []:
            if tier_quantity(row) is not None and tier_quantity(current.get(row['period'])) is None:
                regressions.add(f'{field}: {row["period"]} 기존 정상값 누락')
    return sorted(regressions)
