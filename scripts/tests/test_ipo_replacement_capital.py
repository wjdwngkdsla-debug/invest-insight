import copy
import unittest
from unittest.mock import patch

from scripts.ipo_evidence import reconcile_reported_capital
from scripts.ipo_holder_events import sync_reviewed_holder_events
from scripts.ipo_quality import capital_gaps
from scripts.sources.ipo_schedule import parse_result_capital


RECEIPT = '20260818000023'
RESULT = '''<P>VIII. 실권주 처리내역</P>
<P>주1) 지분율은 공모후 총발행주식수 5,487,150주 기준입니다.</P>
<P>주2) 상장주선인은 40,000주를 자기의 계산으로 취득하였고,
잔액인수분이 의무인수분과 동일하여 의무인수에 의한 신주(사모)는 발행하지 않습니다.</P>'''


def haechitech():
    cumulative = [('상장일', 2119460), ('1개월', 2666477), ('3개월', 2696477),
                  ('6개월', 2785150), ('1년', 3068150), ('3년', 5527150)]
    return {'corp_code': '01947443', 'stock_code': '0155E0', 'name': '해치텍',
            'listing_date': '2026-08-25', 'initial_shares': 5487150,
            'report_rcp': RECEIPT, 'result_capital': parse_result_capital(RESULT, RECEIPT),
            'holder_lockup': {'status': 'verified', 'coverage': 'full', 'basis': 'float_summary',
                'rcept_no': '20260810000669', 'total': 3407690,
                'cumulative_rows': [{'period': p, 'cumulative_float': q} for p, q in cumulative]}}


class ReplacementCapitalTests(unittest.TestCase):
    def test_parser_requires_explicit_final_result_not_a_numeric_gap(self):
        parsed = parse_result_capital(RESULT, RECEIPT)
        self.assertEqual(parsed['issued_total'], 5487150)
        self.assertEqual(parsed['replacement_qty'], 40000)
        self.assertEqual(parsed['status'], 'verified')
        self.assertEqual(parse_result_capital('공모후 총발행주식수 5,487,150주'), {})
        for bad in (RESULT.replace('40,000주', '0주'),
                    RESULT.replace('40,000주', '수량 미정'),
                    RESULT + '<P>공모후 총발행주식수 5,527,150주</P>'):
            self.assertEqual(parse_result_capital(bad)['status'], 'review')

    def test_replacement_lowers_float_without_deleting_lockups(self):
        item = haechitech()
        reconcile_reported_capital(item)
        snap = item['holder_lockup']
        self.assertEqual(snap['cumulative_rows'][0]['cumulative_float'], 2079460)
        self.assertEqual(snap['cumulative_rows'][-1]['cumulative_float'], 5487150)
        self.assertEqual(snap['total'], 3407690)
        self.assertIn({'period': '3개월', 'qty': 30000}, snap['rows'])
        self.assertIn({'period': '6개월', 'qty': 88673}, snap['rows'])
        self.assertEqual(snap['reported_cumulative_rows'][-1]['cumulative_float'], 5527150)
        self.assertEqual(capital_gaps(item), [])
        before = copy.deepcopy(item)
        reconcile_reported_capital(item)
        self.assertEqual(item, before)

    def test_missing_or_changed_evidence_never_applies(self):
        for field, value in [('rcept_no', '20260819000001'), ('issued_total', 5527150),
                             ('replacement_qty', 30000), ('status', 'review'),
                             ('no_additional_private_issue', False)]:
            item = haechitech()
            item['result_capital'][field] = value
            before = copy.deepcopy(item['holder_lockup'])
            reconcile_reported_capital(item)
            self.assertEqual(item['holder_lockup'], before)
            self.assertTrue(capital_gaps(item))
        item = haechitech()
        item['result_capital'] = {}
        reconcile_reported_capital(item)
        self.assertNotIn('capital_adjustment', item['holder_lockup'])

    def test_correction_reopens_review_and_actual_returns_are_preserved(self):
        item = haechitech()
        reconcile_reported_capital(item)
        row = {'code': '0155E0', 'category': '구주·보호예수', 'period': '3개월',
               'planned_qty': 30000, 'api_return_qty': 29000, 'manual_qty': 123,
               'manual_lock': 'Y', 'event_id': 'retained'}
        sync_reviewed_holder_events([row], {'items': [item]})
        self.assertIn('대체인수', row['parse_note'])
        self.assertEqual((row['api_return_qty'], row['manual_qty'], row['event_id']),
                         (29000, 123, 'retained'))
        item['report_rcp'] = '20260819000001'
        self.assertIn('공시 변경: 의무인수 조정 재검증 필요', capital_gaps(item))
        self.assertIn('공시 변경: 실제 발행수량 재검증 필요', capital_gaps(item))
        untouched = []
        sync_reviewed_holder_events(untouched, {'items': [item]})
        self.assertEqual(untouched, [])

    def test_site_uses_adjusted_baseline_without_mutating_manual_cache(self):
        from scripts import build
        item = haechitech()
        reconcile_reported_capital(item)
        row = {'code': '0155E0', 'name': '해치텍', 'shares': 5487150,
               'category': '구주·보호예수', 'period': '3개월', 'final_qty': 30000,
               'final_date': '2026-11-25', 'listing_date': '2026-08-25'}
        with patch.object(build, '_load_schedule_items', return_value=[item]):
            stock = build.rows_to_site_data([row], '2026-09-23')['stocks'][0]
        self.assertEqual(stock['listing_float_shares'], 2079460)
        self.assertFalse(stock['listing_float_excludes_ipo_commitment'])


if __name__ == '__main__':
    unittest.main()
