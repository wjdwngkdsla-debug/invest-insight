"""Receipt-scoped operator evidence; never applies to a newer correction."""
import json
import copy
from functools import lru_cache
from scripts.config import ROOT_DIR


@lru_cache(maxsize=1)
def review_evidence():
    path = ROOT_DIR / 'data' / 'ipo_review_evidence.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def reviewed_document(receipt):
    return review_evidence().get('complete_documents', {}).get(receipt, receipt)


def reconcile_reviewed_detail(summary, detail):
    """Resolve a known source-table conflict only against a fully reconciled detail table."""
    from scripts.utils.dates import calc_release_date
    receipt = summary.get('rcept_no')
    evidence = review_evidence().get('holder_detail_resolutions', {}).get(receipt)
    cumulative = summary.get('cumulative_rows') or []
    if (not evidence or summary.get('reason') != '유통가능 요약표 수량·비율 불일치'
            or detail.get('status') != 'verified' or detail.get('rcept_no') != receipt
            or len(cumulative) < 2 or cumulative[0]['cumulative_float'] != evidence['listing_float']
            or cumulative[-1]['cumulative_float'] != evidence['initial_shares']
            or detail.get('total') != evidence['restricted_total']
            or evidence['listing_float'] + evidence['restricted_total'] != evidence['initial_shares']):
        return None
    rows = detail.get('rows') or []
    quantities = {r['period']: r['qty'] for r in rows}
    if (len(quantities) != len(rows) or quantities != evidence['period_quantities']
            or sum(quantities.values()) != evidence['restricted_total']):
        return None
    rows = sorted(copy.deepcopy(rows), key=lambda r: calc_release_date('2000-01-01', r['period'])[0])
    running = evidence['listing_float']
    adjusted = [{'period': '상장일', 'cumulative_float': running,
                 'float_pct': round(running * 100 / evidence['initial_shares'], 2)}]
    for row in rows:
        running += row['qty']
        adjusted.append({'period': row['period'], 'cumulative_float': running,
                         'float_pct': round(running * 100 / evidence['initial_shares'], 2)})
    return {**summary, 'status': 'verified', 'reason': '', 'rows': rows,
            'total': evidence['restricted_total'], 'coverage': 'full', 'quantity_unit': '주',
            'cumulative_rows': adjusted, 'reported_cumulative_rows': copy.deepcopy(cumulative),
            'summary_kind': 'detail_reconciled', 'summary_reconciliation': {
                **evidence, 'receipt': receipt, 'detail_table_index': detail.get('table_index')}}


def canonical_name(name, code='', corp_code=''):
    for stock_code, entry in review_evidence().get('company_names', {}).items():
        if str(code).zfill(6) == stock_code or (corp_code and normalize_corp_code(corp_code) == entry.get('corp_code')):
            return entry['name']
    return name


def normalize_corp_code(value):
    text = str(value or '').strip()
    return text.zfill(8) if text.isascii() and text.isdigit() and len(text) <= 8 else text


def repair_short_corp_duplicates(schedule):
    items = schedule.get('items', []) + schedule.get('past_items', [])
    canonical = {(i.get('corp_code'), i.get('offering_attempt', 1)): i for i in items
                 if len(str(i.get('corp_code', ''))) == 8}
    removed = set()
    for item in items:
        raw = item.get('corp_code')
        corp = normalize_corp_code(raw)
        target = canonical.get((corp, item.get('offering_attempt', 1)))
        if raw != corp and target is not None and target is not item:
            # Preserve explicit operator disagreements for review, not silent merging.
            fields = set(item.get('manual_fields') or [])
            fields.update(k for k in ('manual_commit_apply', 'manual_commit_alloc', 'holder_overrides') if item.get(k))
            if any(target.get(k) not in (None, '', item.get(k)) for k in fields):
                continue
            schedule.setdefault('identity_repairs', []).append({'old_corp_code': raw, 'corp_code': corp,
                'reason': 'DART 고유번호 선행 0 복원 및 기존 종목 연결', 'previous_record': copy.deepcopy(item)})
            for field in fields | set(item.get('provisional_fields') or []):
                if target.get(field) in (None, ''):
                    target[field] = copy.deepcopy(item.get(field))
            target['manual_fields'] = sorted(set(target.get('manual_fields') or []) | set(item.get('manual_fields') or []))
            removed.add(id(item))
        elif raw != corp:
            item['corp_code'] = corp
        item['name'] = canonical_name(item.get('name'), item.get('stock_code'), corp)
    for collection in ('items', 'past_items'):
        schedule[collection] = [i for i in schedule.get(collection, []) if id(i) not in removed]
    return schedule


def demand_waiting(item, today):
    evidence = review_evidence()
    entry = evidence.get('disclosure_waiting', {}).get(item.get('corp_code'), {})
    return bool(entry and evidence['checked_at'] <= today < entry['until']
                and item.get('last_rcept_no') == entry['receipt']
                and not item.get('demand_ratio') and not item.get('report_rcp'))


def apply_approved_allocations(schedule):
    """Repair only approved old values, never a different manual edit or new receipt."""
    corrections = review_evidence().get('approved_allocation_corrections', {})
    for item in schedule.get('items', []) + schedule.get('past_items', []):
        correction = corrections.get(item.get('corp_code'))
        if not correction or item.get('report_rcp') != correction['receipt']:
            continue
        total = correction['reported_total']
        if sum(correction['corrected'].values()) != total:
            raise ValueError('Approved allocation total does not reconcile')
        manual = item.get('manual_commit_alloc') or {}
        for tier in item.get('commit_alloc') or []:
            period = tier.get('period')
            if period not in correction['previous']:
                continue
            previous, corrected = correction['previous'][period], correction['corrected'][period]
            override = manual.get(period)
            if override and int(override.get('qty', -1)) not in (previous, corrected):
                continue
            if int(tier.get('qty', -1)) not in (previous, corrected):
                continue
            if override:
                override['qty'] = corrected
            tier.update(qty=corrected, pct=round(corrected * 100 / total, 2),
                        source='manual_fixed' if override and override.get('locked') else 'dart_table',
                        rcept_no=correction['receipt'], reported_total=total)


def reconcile_reported_capital(item):
    """Apply a documented post-offering adjustment only when every source ID agrees."""
    from scripts.utils.dates import calc_release_date
    adjustment = review_evidence().get('capital_adjustments', {}).get(item.get('corp_code'))
    snap = item.get('holder_lockup') or {}
    if not adjustment or snap.get('status') != 'verified' or snap.get('capital_adjustment'):
        return
    cumulative = snap.get('cumulative_rows') or []
    if (snap.get('rcept_no') != adjustment['summary_receipt']
            or item.get('report_rcp') != adjustment['result_receipt']
            or str(item.get('initial_shares')) != str(adjustment['initial_shares'])
            or not cumulative or cumulative[-1]['cumulative_float'] != adjustment['reported_total']
            or adjustment['reported_total'] + adjustment['delta'] != adjustment['initial_shares']):
        return
    dates = lambda p: '2000-01-01' if p == '상장일' else calc_release_date('2000-01-01', p)[0]
    affected = [r for r in cumulative if dates(r['period']) >= dates(adjustment['period'])]
    if not affected:
        return
    updated = copy.deepcopy(snap)
    updated['reported_cumulative_rows'] = copy.deepcopy(cumulative)
    if not any(dates(r['period']) == dates(adjustment['period']) for r in affected):
        prior = [r for r in cumulative if dates(r['period']) < dates(adjustment['period'])]
        if not prior or adjustment['delta'] <= 0:
            return
        updated['cumulative_rows'].append({'period': adjustment['period'],
            'cumulative_float': prior[-1]['cumulative_float'], 'quantity_unit': snap.get('quantity_unit', '주'),
            'row_text': adjustment['reason'], 'source_receipt': adjustment['result_receipt']})
        updated['cumulative_rows'].sort(key=lambda r: dates(r['period']))
    for row in updated['cumulative_rows']:
        if dates(row['period']) >= dates(adjustment['period']):
            row['cumulative_float'] += adjustment['delta']
        row['float_pct'] = round(row['cumulative_float'] * 100 / adjustment['initial_shares'], 2)
    releases = []
    for before, after in zip(updated['cumulative_rows'], updated['cumulative_rows'][1:]):
        delta = after['cumulative_float'] - before['cumulative_float']
        if delta < 0:
            return
        if delta:
            releases.append({'period': after['period'], 'qty': delta})
    updated.update(rows=releases, total=sum(r['qty'] for r in releases), capital_adjustment=adjustment)
    item['holder_lockup'] = updated
