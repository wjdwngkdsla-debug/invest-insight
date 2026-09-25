"""Apply verified, operator-reviewed holder schedules without replacing actual returns."""
import re

from scripts.ipo_evidence import review_evidence
from scripts.ipo_quality import quantity
from scripts.utils.dates import calc_release_date


def period_key(period):
    match = re.fullmatch(r'(\d+)(년|개월)', str(period))
    return f'{int(match[1]) * (12 if match[2] == "년" else 1)}M' if match else period


def sync_reviewed_holder_events(rows, schedule):
    from scripts.build import CATEGORY_FLOAT, build_event_id, pct

    evidence = review_evidence().get('holders', {})
    for item in schedule.get('items', []) + schedule.get('past_items', []):
        snapshot = item.get('holder_lockup') or {}
        if (snapshot.get('status') != 'verified' or not snapshot.get('rcept_no')
                or snapshot.get('rcept_no') != evidence.get(item.get('corp_code'))):
            continue
        code, listing = item.get('stock_code'), item.get('listing_date')
        shares = quantity(item.get('initial_shares'))
        if not code or not listing or not shares:
            continue
        existing = [r for r in rows if r.get('code') == code and r.get('category') == CATEGORY_FLOAT]
        template = next((r for r in rows if r.get('code') == code), {})
        for release in snapshot.get('rows') or []:
            period, qty = release['period'], release['qty']
            date, display, tradable = calc_release_date(listing, period)
            matches = [r for r in existing if period_key(r.get('period')) == period_key(period)]
            if len(matches) > 1:
                continue  # Split actual-return events are not one planned event.
            if matches:
                row = matches[0]
            else:
                row = {k: template.get(k, '') for k in ('market', 'close_price', 'current_shares', 'shares_date')}
                row.update(event_id=build_event_id(code, CATEGORY_FLOAT, period, tradable),
                           code=code, category=CATEGORY_FLOAT, type='보호예수', period=period,
                           manual_lock='N', sheet_visible='Y')
                rows.append(row)
                existing.append(row)
            row.update(name=item['name'], listing_date=listing, shares=shares,
                       planned_qty=qty, planned_pct=pct(qty, shares), planned_date=date,
                       planned_date_display=display, planned_tradable_date=tradable,
                       dart_rcp=snapshot['rcept_no'],
                       dart_source='투자설명서 유통가능 요약표' if snapshot.get('basis') == 'float_summary' and not snapshot.get('summary_reconciliation') else '투자설명서 주주별 매각제한 내역',
                       parse_note=(snapshot.get('summary_reconciliation') or {}).get('reason', ''),
                       quantity_unit=snapshot.get('quantity_unit', '주'))
    return rows
