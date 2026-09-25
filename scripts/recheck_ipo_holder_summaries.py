"""Recheck saved IPO receipts against the summary-first rule without changing manual values."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from scripts.config import ROOT_DIR
from scripts.sources.dart_api import download_document_text, holder_snapshot, merge_holder_snapshot
from scripts.utils.redaction import redact_sensitive_text
from scripts.ipo_evidence import canonical_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--result-corp', action='append', default=[], help='Reparse a saved result receipt for this corporation')
    args = parser.parse_args()
    path = ROOT_DIR / 'data' / 'ipo_schedule.json'
    schedule = json.loads(path.read_text(encoding='utf-8'))
    management = json.loads((ROOT_DIR / 'data' / 'stock_management.json').read_text(encoding='utf-8'))
    by_code = {r.get('stock_code'): r for r in management if r.get('stock_code')}
    changed, failures = [], []
    for item in schedule.get('items', []) + schedule.get('past_items', []):
        item['name'] = canonical_name(item.get('name'), item.get('stock_code'), item.get('corp_code'))
        initial = by_code.get(item.get('stock_code'), {}).get('initial_shares')
        if initial and not item.get('initial_shares'):
            item['initial_shares'] = initial
        if item.get('corp_code') in args.result_corp and item.get('report_rcp'):
            from scripts.sources.ipo_schedule import parse_result_report, RESULT_PARSE_VERSION
            from scripts.audit_ipo_quality import merge_tiers
            try:
                result = parse_result_report(download_document_text(item['report_rcp']))
                if result.get('commit_alloc'):
                    for tier in result['commit_alloc']:
                        tier['rcept_no'] = item['report_rcp']
                    merge_tiers(item, 'commit_alloc', result['commit_alloc'], item['report_rcp'])
                    item['result_parse_version'] = RESULT_PARSE_VERSION
                    from scripts.ipo_quality import PERIODS, tier_quantity
                    parsed = {r['period']: r for r in result['commit_alloc']}
                    valid = all(tier_quantity(parsed.get(p)) is not None for p in PERIODS)
                    item['result_source_check'] = {'status': 'verified' if valid else 'parse_incomplete', 'rcept_no': item['report_rcp'],
                        'checked_at': datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()}
            except Exception as exc:
                failures.append({'name': item['name'], 'error': redact_sensitive_text(exc)})
        previous = item.get('holder_lockup') or {}
        receipt = previous.get('rcept_no')
        if (previous.get('status') != 'review' and previous.get('basis') != 'float_summary') or not receipt or not str(receipt).isdigit():
            continue
        try:
            cached = args.cache_dir / f'{receipt}.xml' if args.cache_dir else None
            doc = cached.read_text(encoding='utf-8') if cached and cached.exists() else download_document_text(receipt)
            snapshot = holder_snapshot(doc, receipt)
            snapshot['quantity_unit'] = 'DR' if item.get('security_type') == 'depositary_receipt' else '주'
            item['holder_lockup'] = merge_holder_snapshot(previous, snapshot)
            changed.append({'name': item['name'], 'status': snapshot['status'], 'basis': snapshot.get('basis'),
                            'reason': snapshot.get('reason', ''), 'rcept_no': receipt})
            print(json.dumps(changed[-1], ensure_ascii=False), flush=True)
        except Exception as exc:
            failures.append({'name': item['name'], 'error': redact_sensitive_text(exc)})
            print(json.dumps(failures[-1], ensure_ascii=False), flush=True)
    if args.write:
        path.write_text(json.dumps(schedule, ensure_ascii=False, indent=2), encoding='utf-8')
        report = {'checked_at': datetime.now(ZoneInfo('Asia/Seoul')).isoformat(), 'results': changed, 'failures': failures}
        (ROOT_DIR / 'data' / 'ipo_summary_recheck.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Rechecked {len(changed)}; failures {len(failures)}', flush=True)


if __name__ == '__main__':
    main()
