import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.ipo_evidence import apply_approved_allocations, canonical_name, demand_waiting, reviewed_document, review_evidence, reconcile_reported_capital
from scripts.ipo_holder_events import sync_reviewed_holder_events
from scripts.ipo_quality import capital_gaps, PERIODS
from scripts.sources.dart_api import holder_snapshot


class ReviewedDartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = json.loads((Path(__file__).parent / 'fixtures/ipo_review_tables.json').read_text(encoding='utf-8'))

    def snapshot(self, receipt):
        return holder_snapshot(self.tables[receipt], receipt)

    def test_actual_partial_summaries_do_not_require_one_hundred_percent(self):
        for receipt, last in [('20260803000167', 10147052), ('20250716000294', 6955139)]:
            with self.subTest(receipt=receipt):
                snap = self.snapshot(receipt)
                self.assertEqual(snap['status'], 'verified')
                self.assertEqual(snap['coverage'], 'disclosed_periods_only')
                self.assertEqual(snap['cumulative_rows'][-1]['cumulative_float'], last)

    def test_increment_and_cumulative_headers_choose_cumulative(self):
        for receipt, first, last in [('20250422000541', 1452650, 5811000), ('20241022000107', 2350755, 1766442)]:
            snap = self.snapshot(receipt)
            self.assertEqual(snap['status'], 'verified')
            self.assertEqual(snap['rows'][0]['qty'], first)
            self.assertEqual(snap['rows'][-1]['qty'], last)

    def test_dilution_scenario_is_not_mixed_into_base_case(self):
        snap = self.snapshot('20241105000121')
        self.assertEqual(snap['status'], 'verified')
        self.assertEqual(snap['rows'], [{'period': '3개월', 'qty': 90000}, {'period': '6개월', 'qty': 8564000}])

    def test_explicit_date_between_relative_periods(self):
        snap = self.snapshot('20241015000376')
        self.assertEqual(snap['status'], 'verified')
        self.assertEqual(snap['rows'][0], {'period': '2024-11-01', 'qty': 388245})
        self.assertEqual(snap['rows'][1], {'period': '1개월', 'qty': 9226173})
        self.assertIn({'period': '18개월', 'qty': 1867184}, snap['rows'])

    def test_quantity_unit_suffix_does_not_drop_table(self):
        for receipt in ('20250114000178', '20241106000088'):
            self.assertEqual(self.snapshot(receipt)['status'], 'verified')

    def test_dotmil_split_and_shifted_cells_reconcile_exactly(self):
        snap = self.snapshot('20241101000293')
        self.assertEqual(snap['status'], 'verified')
        self.assertEqual(snap['total'], 5990478)
        self.assertEqual({r['period']: r['qty'] for r in snap['rows']},
                         {'1개월': 2154196, '3개월': 36000, '6개월': 668602, '1년': 884480, '2년': 2247200})
        broken = self.tables['20241101000293'].replace('5,990,478', '5,990,479')
        self.assertEqual(holder_snapshot(broken, 'receipt')['status'], 'review')

    def test_source_arithmetic_error_remains_review(self):
        snap = self.snapshot('20260220001638')
        self.assertEqual(snap['status'], 'review')
        self.assertIn('수량·비율', snap['reason'])

    def test_reviewed_document_does_not_override_later_correction(self):
        self.assertEqual(reviewed_document('20260220001649'), '20260220001638')
        self.assertEqual(reviewed_document('20260221000100'), '20260221000100')

    def test_waiting_expires_or_ends_on_new_disclosure(self):
        item = {'corp_code': '01028933', 'last_rcept_no': '20260914000034'}
        self.assertTrue(demand_waiting(item, '2026-09-25'))
        self.assertFalse(demand_waiting(item, '2026-10-01'))
        self.assertFalse(demand_waiting({**item, 'last_rcept_no': '20260926000001'}, '2026-09-26'))
        self.assertFalse(demand_waiting({**item, 'demand_ratio': 100}, '2026-09-25'))

    def test_rename_uses_identity_not_similar_name(self):
        self.assertEqual(canonical_name('위너스', '479960'), '위너스일렉')
        self.assertEqual(canonical_name('위너스', '000001'), '위너스')

    def test_approved_manual_fix_preserves_later_manual_edits(self):
        evidence = review_evidence()['approved_allocation_corrections']['01432598']
        item = {'corp_code': '01432598', 'report_rcp': evidence['receipt'],
                'commit_alloc': [{'period': p, 'qty': q} for p, q in evidence['previous'].items()],
                'manual_commit_alloc': {'미확약': {'qty': evidence['previous']['미확약'], 'locked': True}}}
        schedule = {'items': [item]}
        apply_approved_allocations(schedule)
        self.assertEqual(sum(r['qty'] for r in item['commit_alloc']), 3000000)
        self.assertEqual(item['manual_commit_alloc']['미확약']['qty'], 2957233)
        item['manual_commit_alloc']['미확약']['qty'] = 42
        apply_approved_allocations(schedule)
        self.assertEqual(item['manual_commit_alloc']['미확약']['qty'], 42)

    def test_capital_checks_do_not_double_count_public_allocation(self):
        item = {'initial_shares': 1000, 'offer_shares': 500,
                'holder_lockup': {'status': 'verified', 'coverage': 'full', 'total': 700,
                                 'cumulative_rows': [{'cumulative_float': 300}, {'cumulative_float': 1000}]},
                'commit_alloc': [{'period': p, 'qty': 100 if p in ('미확약', '1개월') else 0} for p in PERIODS]}
        self.assertEqual(capital_gaps(item), [])
        item['commit_alloc'][0]['qty'] = 900
        self.assertIn('기관 총배정이 공모주식수 초과', capital_gaps(item))

    def test_planned_update_keeps_actual_and_manual_values_and_is_idempotent(self):
        snap = self.snapshot('20241022000107')
        item = {'corp_code': '01480708', 'stock_code': '376270', 'name': 'HEM', 'listing_date': '2024-11-05',
                'initial_shares': 6962039, 'holder_lockup': snap}
        row = {'code': '376270', 'category': '구주·보호예수', 'period': '12개월', 'planned_qty': 863548,
               'api_return_qty': 863548, 'manual_qty': 123, 'manual_lock': 'Y', 'event_id': 'existing'}
        rows = sync_reviewed_holder_events([row], {'items': [item]})
        self.assertEqual(row['planned_qty'], 749254)
        self.assertEqual(row['api_return_qty'], 863548)
        self.assertEqual(row['manual_qty'], 123)
        self.assertEqual(row['event_id'], 'existing')
        before = copy.deepcopy(rows)
        sync_reviewed_holder_events(rows, {'items': [item]})
        self.assertEqual(rows, before)

    def test_result_adjustment_reconciles_capital_without_destroying_original(self):
        snap = self.snapshot('20250422000541')
        item = {'corp_code': '01594791', 'initial_shares': 12547732,
                'report_rcp': '20250430000650', 'holder_lockup': snap}
        reconcile_reported_capital(item)
        updated = item['holder_lockup']
        self.assertEqual(updated['cumulative_rows'][-1]['cumulative_float'], 12547732)
        self.assertEqual(updated['reported_cumulative_rows'][-1]['cumulative_float'], 12548950)
        self.assertEqual(updated['rows'][1]['qty'], 1142322)
        before = copy.deepcopy(updated)
        reconcile_reported_capital(item)
        self.assertEqual(item['holder_lockup'], before)
        self.assertEqual(capital_gaps(item), [])
        changed_report = {**item, 'report_rcp': '20250501000001'}
        self.assertIn('공시 변경: 의무인수 조정 재검증 필요', capital_gaps(changed_report))
        later = {**item, 'report_rcp': '20250501000001', 'holder_lockup': snap}
        reconcile_reported_capital(later)
        self.assertNotIn('capital_adjustment', later['holder_lockup'])

    def test_additional_underwriter_tranche_adds_only_documented_period(self):
        item = {'corp_code': '01787355', 'initial_shares': 11533591, 'report_rcp': '20251211000109',
                'holder_lockup': {'status': 'verified', 'rcept_no': '20251205000544', 'coverage': 'full',
                    'cumulative_rows': [{'period': '상장일', 'cumulative_float': 3732925},
                        {'period': '3개월', 'cumulative_float': 7190731}, {'period': '1년', 'cumulative_float': 7560482},
                        {'period': '3년', 'cumulative_float': 11516391}]}}
        reconcile_reported_capital(item)
        snap = item['holder_lockup']
        self.assertIn({'period': '6개월', 'qty': 17200}, snap['rows'])
        self.assertEqual(snap['cumulative_rows'][-1]['cumulative_float'], 11533591)
        self.assertEqual(snap['reported_cumulative_rows'][-1]['cumulative_float'], 11516391)


if __name__ == '__main__':
    unittest.main()
